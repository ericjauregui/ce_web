from __future__ import annotations

import io
import hashlib
import json
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Any, Callable

from flask import Flask, abort, jsonify, render_template, request, send_file, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from domains.cart import (
    cart_items,
    cart_to_pdf_bytes,
    cart_total_items,
    get_cart_notes,
    normalize_item_note,
)
from domains.catalog import products_by_code
from domains.emailing import OrderEmailDeliveryError
from domains.emailing import build_order_csv
from domains.orders import (
    DatabaseConfigurationError,
    IdempotencyConflictError,
    OrderPersistenceError,
    OrderRepository,
    OrderValidationError,
)
from domains.homepage import load_latest_reels
from domains.location_options import (
    CHECKOUT_COUNTRY_KEY_BY_LABEL,
    CHECKOUT_COUNTRY_LABELS_BY_KEY,
    CHECKOUT_COUNTRY_OPTIONS,
    CHECKOUT_SUBDIVISION_OPTIONS_BY_COUNTRY_KEY,
    get_location_country_key_from_label,
)
from domains.phone_country_codes import (
    CHECKOUT_PHONE_COUNTRY_DISPLAY_BY_KEY,
    CHECKOUT_PHONE_COUNTRY_OPTIONS,
    DEFAULT_PHONE_COUNTRY_KEY,
    get_phone_country_key_from_display,
    get_phone_country_option,
)

LoadProducts = Callable[[], list[dict[str, Any]]]
GetCart = Callable[[], dict[str, int]]
SendOrderEmail = Callable[..., dict[str, Any]]
CanonicalBaseUrl = Callable[[], str]
MAX_VALIDATED_ORDER_QUANTITY = 999
MAX_ORDER_DOWNLOAD_AGE_SECONDS = 60 * 60 * 24 * 30
CHECKOUT_FIELD_LIMITS = {
    "name": 160,
    "company": 200,
    "phone": 64,
    "email": 254,
    "address_line_1": 250,
    "address_line_2": 250,
    "postal_code": 32,
    "city": 120,
    "state": 120,
    "country": 120,
    "notes": 2000,
}
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_checkout_phone(country_key: str, phone: str) -> str:
    normalized_phone = (phone or "").strip()
    if not normalized_phone:
        return ""

    _, _, normalized_country_code = get_phone_country_option(country_key)
    if normalized_phone.startswith("+"):
        return normalized_phone
    if normalized_phone.startswith("00"):
        return f"+{normalized_phone[2:]}"

    if not re.fullmatch(r"\+\d{1,5}", normalized_country_code):
        _, _, normalized_country_code = get_phone_country_option(DEFAULT_PHONE_COUNTRY_KEY)

    return f"{normalized_country_code} {normalized_phone}"


def resolve_checkout_phone_country_key(
    country_key: str,
    display_value: str,
    *,
    default_to_default: bool = False,
) -> str:
    normalized_key = (country_key or "").strip().lower()
    if normalized_key and normalized_key in CHECKOUT_PHONE_COUNTRY_DISPLAY_BY_KEY:
        return get_phone_country_option(normalized_key)[0]

    display_key = get_phone_country_key_from_display(display_value)
    if display_key:
        return display_key

    if default_to_default:
        return DEFAULT_PHONE_COUNTRY_KEY

    return ""


def resolve_checkout_country_key(country_key: str, country_label: str) -> str:
    normalized_key = (country_key or "").strip().lower()
    if normalized_key in CHECKOUT_COUNTRY_LABELS_BY_KEY:
        return normalized_key
    return get_location_country_key_from_label(country_label)


def register_cart_routes(
    app: Flask,
    *,
    base_dir: Path,
    load_products: LoadProducts,
    get_cart: GetCart,
    send_order_email: SendOrderEmail,
    canonical_base_url: CanonicalBaseUrl,
) -> None:
    checkout_google_maps_places_api_key = str(
        app.config.get("GOOGLE_MAPS_PLACES_API_KEY")
        or app.config.get("GOOGLE_MAPS_API_KEY")
        or os.getenv("GOOGLE_MAPS_PLACES_API_KEY")
        or os.getenv("GOOGLE_MAPS_API_KEY")
        or ""
    ).strip()
    repository_lock = threading.Lock()

    def _order_repository() -> OrderRepository:
        configured = app.extensions.get("order_repository")
        if isinstance(configured, OrderRepository):
            return configured

        with repository_lock:
            configured = app.extensions.get("order_repository")
            if isinstance(configured, OrderRepository):
                return configured
            database_url = str(app.config.get("DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
            repository = OrderRepository(database_url)
            app.extensions["order_repository"] = repository
            return repository

    def _cart_fingerprint(cart_data: dict[str, int], notes_by_code: dict[str, str]) -> str:
        serialized = json.dumps(
            {"cart": cart_data, "notes": notes_by_code},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    def _checkout_idempotency_key(cart_data: dict[str, int], notes_by_code: dict[str, str]) -> str:
        fingerprint = _cart_fingerprint(cart_data, notes_by_code)
        prior_key_was_submitted = (
            bool(cart_data)
            and session.get("checkout_idempotency_key") == session.get("last_order_idempotency_key")
        )
        if session.get("checkout_cart_fingerprint") != fingerprint or prior_key_was_submitted:
            session["checkout_idempotency_key"] = secrets.token_urlsafe(32)
            session["checkout_cart_fingerprint"] = fingerprint
        key = str(session.get("checkout_idempotency_key") or "")
        if not key:
            key = secrets.token_urlsafe(32)
            session["checkout_idempotency_key"] = key
            session["checkout_cart_fingerprint"] = fingerprint
        return key

    def _download_serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(app.secret_key, salt="order-download-v1")

    def _signed_download_token(order: Any) -> str:
        return _download_serializer().dumps(
            {"order_id": order.id, "access_token": order.access_token}
        )

    def _load_download_order(token: str) -> Any:
        max_age = int(app.config.get("ORDER_DOWNLOAD_MAX_AGE_SECONDS", MAX_ORDER_DOWNLOAD_AGE_SECONDS))
        try:
            payload = _download_serializer().loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            abort(404)
        if not isinstance(payload, dict):
            abort(404)
        raw_access_token = str(payload.get("access_token") or "")
        order_id = str(payload.get("order_id") or "")
        if not raw_access_token or not order_id:
            abort(404)
        if session.get("last_order_token") != token or session.get("last_order_id") != order_id:
            abort(404)
        try:
            order = _order_repository().get_order_by_access_token(raw_access_token)
        except (DatabaseConfigurationError, OrderPersistenceError):
            abort(503)
        if order is None or not secrets.compare_digest(str(order.id), order_id):
            abort(404)
        return order

    def _saved_order_rows(order: Any) -> list[dict[str, Any]]:
        return [item.as_order_row() for item in order.items]

    def _render_saved_order(order: Any, *, email_sent: bool | None, fallback_used: bool = False):
        session["last_order_id"] = order.id
        session["last_order_token"] = _signed_download_token(order)
        for legacy_key in (
            "last_order_csv",
            "last_order_rows",
            "last_order_csv_filename",
            "last_order_customer",
        ):
            session.pop(legacy_key, None)
        return render_template(
            "order_submitted.html",
            token=session["last_order_token"],
            email_sent=email_sent,
            fallback_used=fallback_used,
            client_email=str(order.customer.get("email") or ""),
            order_id=order.order_number,
            order_rows=_saved_order_rows(order),
        )

    def _build_order_customer(form_values: dict[str, str]) -> dict[str, str]:
        return {
            "name": form_values.get("name", ""),
            "company": form_values.get("company", ""),
            "phone": normalize_checkout_phone(
                form_values.get("phone_country_code", ""),
                form_values.get("phone", ""),
            ),
            "email": form_values.get("email", ""),
            "address_line_1": form_values.get("address_line_1", ""),
            "address_line_2": form_values.get("address_line_2", ""),
            "postal_code": form_values.get("postal_code", ""),
            "city": form_values.get("city", ""),
            "state": form_values.get("state", ""),
            "country": form_values.get("country", ""),
            "country_key": form_values.get("country_key", ""),
            "notes": form_values.get("notes", ""),
        }

    def _validated_order_items(
        product_map: dict[str, dict[str, Any]],
        cart_data: dict[str, int],
        notes_by_code: dict[str, str],
    ) -> list[dict[str, Any]]:
        validated_items: list[dict[str, Any]] = []
        for code, raw_qty in cart_data.items():
            product = product_map.get(code)
            if not product:
                raise ValueError(f"Unknown product code in cart: {code}")

            try:
                quantity = int(raw_qty)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid quantity for product {code}") from exc

            if quantity <= 0 or quantity > MAX_VALIDATED_ORDER_QUANTITY:
                raise ValueError(f"Quantity out of range for product {code}")

            validated_items.append(
                {
                    "code": str(product.get("code") or code),
                    "name": str(product.get("name") or code),
                    "description": str(product.get("description") or ""),
                    "collection": str(product.get("collection") or ""),
                    "quantity": quantity,
                    "notes": notes_by_code.get(code, ""),
                    "image": str(product.get("image") or ""),
                }
            )

        if not validated_items:
            raise ValueError("Order cart is empty.")

        return validated_items

    @app.route("/cart")
    def cart():
        pmap = products_by_code(load_products())
        cart_data = get_cart()
        notes_by_code = get_cart_notes(session, cart_data)
        items = cart_items(pmap, cart_data, notes_by_code)
        reels_path = base_dir / "static" / "reels"
        latest_reels = load_latest_reels(reels_path)
        return render_template(
            "cart.html",
            items=items,
            total_items=cart_total_items(cart_data),
            latest_reels=latest_reels,
        )

    @app.route("/checkout", methods=["GET", "POST"])
    def checkout():
        pmap = products_by_code(load_products())
        cart_data = get_cart()
        notes_by_code = get_cart_notes(session, cart_data)
        items = cart_items(pmap, cart_data, notes_by_code)

        def render_checkout_page(
            *,
            status_code: int = 200,
            form_values: dict[str, str] | None = None,
            submission_error: str = "",
        ):
            values = {
                "name": "",
                "company": "",
                "phone": "",
                "phone_country_code": "",
                "phone_country": "",
                "email": "",
                "address_line_1": "",
                "address_line_2": "",
                "postal_code": "",
                "city": "",
                "state": "",
                "country_key": "",
                "country": "",
                "notes": "",
            }
            if form_values:
                values.update({key: value for key, value in form_values.items() if value is not None})

            resolved_phone_key = resolve_checkout_phone_country_key(
                values.get("phone_country_code", ""),
                values.get("phone_country", ""),
            )
            values["phone_country_code"] = resolved_phone_key
            if resolved_phone_key and not values.get("phone_country"):
                values["phone_country"] = CHECKOUT_PHONE_COUNTRY_DISPLAY_BY_KEY[resolved_phone_key]

            resolved_country_key = resolve_checkout_country_key(
                values.get("country_key", ""),
                values.get("country", ""),
            )
            if resolved_country_key:
                values["country_key"] = resolved_country_key
                if not values.get("country"):
                    values["country"] = CHECKOUT_COUNTRY_LABELS_BY_KEY[resolved_country_key]

            return render_template(
                "checkout.html",
                items=items,
                phone_country_options=CHECKOUT_PHONE_COUNTRY_OPTIONS,
                phone_country_display_by_key=CHECKOUT_PHONE_COUNTRY_DISPLAY_BY_KEY,
                country_options=CHECKOUT_COUNTRY_OPTIONS,
                country_key_by_label=CHECKOUT_COUNTRY_KEY_BY_LABEL,
                country_label_by_key=CHECKOUT_COUNTRY_LABELS_BY_KEY,
                subdivisions_by_country_key=CHECKOUT_SUBDIVISION_OPTIONS_BY_COUNTRY_KEY,
                form_values=values,
                submission_error=submission_error,
                idempotency_key=_checkout_idempotency_key(cart_data, notes_by_code),
                google_maps_places_api_key=checkout_google_maps_places_api_key,
            ), status_code

        if request.method == "GET":
            return render_checkout_page()

        submitted_key = (request.form.get("idempotency_key") or "").strip()
        expected_key = str(session.get("checkout_idempotency_key") or "")
        if not submitted_key or not expected_key or not secrets.compare_digest(submitted_key, expected_key):
            return render_checkout_page(
                status_code=400,
                submission_error="This order form expired. Please review your cart and submit it again.",
            )

        existing_retry_order = None
        # A browser retry can arrive after the first request committed and cleared
        # the cart. Load its durable snapshot and compare the submitted customer
        # details below before returning it.
        if not items and session.get("last_order_id") and session.get("last_order_idempotency_key") == submitted_key:
            try:
                existing_retry_order = _order_repository().get_order(str(session["last_order_id"]))
            except (DatabaseConfigurationError, OrderPersistenceError):
                return render_checkout_page(
                    status_code=503,
                    submission_error="We couldn't retrieve your saved order right now. Please try again shortly.",
                )

        name = (request.form.get("name") or "").strip()
        company = (request.form.get("company") or "").strip()
        phone_country_display = (request.form.get("phone_country") or "").strip()
        phone_country_key = resolve_checkout_phone_country_key(
            request.form.get("phone_country_code") or "",
            phone_country_display,
        )
        phone = normalize_checkout_phone(phone_country_key, request.form.get("phone") or "")
        client_email = (request.form.get("email") or "").strip()
        address_line_1 = (request.form.get("address_line_1") or "").strip()
        address_line_2 = (request.form.get("address_line_2") or "").strip()
        postal_code = (request.form.get("postal_code") or "").strip()
        city = (request.form.get("city") or "").strip()
        state = (request.form.get("state") or "").strip()
        country = (request.form.get("country") or "").strip()
        country_key = resolve_checkout_country_key(request.form.get("country_key") or "", country)
        if country_key:
            country = CHECKOUT_COUNTRY_LABELS_BY_KEY[country_key]

        form_values = {
            "name": name,
            "company": company,
            "phone": (request.form.get("phone") or "").strip(),
            "phone_country": phone_country_display,
            "phone_country_code": phone_country_key,
            "email": client_email,
            "address_line_1": address_line_1,
            "address_line_2": address_line_2,
            "postal_code": postal_code,
            "city": city,
            "state": state,
            "country": country,
            "country_key": country_key,
            "notes": (request.form.get("notes") or "").strip(),
        }

        invalid_length = any(
            len(str(form_values.get(field) or "")) > limit
            for field, limit in CHECKOUT_FIELD_LIMITS.items()
        )
        invalid_email = bool(client_email and not EMAIL_PATTERN.fullmatch(client_email))

        if existing_retry_order is not None:
            submitted_customer = _build_order_customer(form_values)
            stored_customer = dict(existing_retry_order.customer)
            customer_keys = tuple(CHECKOUT_FIELD_LIMITS) + ("country_key",)
            if any(
                str(submitted_customer.get(key) or "") != str(stored_customer.get(key) or "")
                for key in customer_keys
            ):
                return render_checkout_page(
                    status_code=409,
                    form_values=form_values,
                    submission_error="This order form was already used for different details. Please reload checkout and try again.",
                )
            delivery_state = (
                True
                if existing_retry_order.email_status == "sent"
                else False
                if existing_retry_order.email_status == "failed"
                else None
            )
            return _render_saved_order(existing_retry_order, email_sent=delivery_state)

        if (
            invalid_length
            or invalid_email
            or not (name and company and phone_country_key and phone and city and state and country and country_key)
            or len(items) == 0
        ):
            return render_checkout_page(
                status_code=400,
                form_values=form_values,
                submission_error=(
                    "Please enter a valid email address."
                    if invalid_email
                    else "Please check the required fields and their lengths."
                ),
            )

        try:
            validated_items = _validated_order_items(pmap, cart_data, notes_by_code)
        except ValueError:
            return render_checkout_page(
                status_code=400,
                form_values=form_values,
                submission_error="We couldn't validate the items in your order. Please review your cart and try again.",
            )

        customer = _build_order_customer(form_values)
        try:
            repository = _order_repository()
            created = repository.create_order(
                idempotency_key=submitted_key,
                customer=customer,
                items=validated_items,
                metadata={"source": "web_checkout"},
            )
        except IdempotencyConflictError:
            return render_checkout_page(
                status_code=409,
                form_values=form_values,
                submission_error="This order form was already used for different details. Please reload checkout and try again.",
            )
        except OrderValidationError:
            return render_checkout_page(
                status_code=400,
                form_values=form_values,
                submission_error="We couldn't validate this order. Please review the form and try again.",
            )
        except (DatabaseConfigurationError, OrderPersistenceError):
            return render_checkout_page(
                status_code=503,
                form_values=form_values,
                submission_error="We couldn't save your order right now. Please try again shortly.",
            )

        order = created.order
        session["last_order_id"] = order.id
        session["last_order_idempotency_key"] = submitted_key
        csv_text = build_order_csv(
            order.order_number,
            customer,
            validated_items,
            submitted_at=order.created_at,
        )
        csv_filename = f"ce_order_{order.order_number.lstrip('#')}.csv"
        if created.created:
            try:
                repository.store_order_csv(order.id, csv_text, csv_filename)
            except OrderPersistenceError:
                # The order itself is durable. A download can be rebuilt from the
                # stored snapshots if this secondary update briefly fails.
                pass

        if not created.created:
            session["cart"] = {}
            session["cart_notes"] = {}
            delivery_state = True if order.email_status == "sent" else False if order.email_status == "failed" else None
            return _render_saved_order(order, email_sent=delivery_state)

        email_sent = False
        fallback_used = False
        try:
            result = send_order_email(
                customer,
                validated_items,
                order_id=order.order_number,
                submitted_at=order.created_at,
            )
        except OrderEmailDeliveryError as exc:
            try:
                repository.record_email_delivery(order.id, "failed", error_message=str(exc))
            except OrderPersistenceError:
                pass
        except Exception:
            try:
                repository.record_email_delivery(order.id, "failed", error_message="email delivery failed")
            except OrderPersistenceError:
                pass
        else:
            email_sent = bool(result.get("ok"))
            fallback_used = bool(result.get("fallback_used"))
            try:
                repository.record_email_delivery(order.id, "sent" if email_sent else "failed")
            except OrderPersistenceError:
                pass

        session["cart"] = {}
        session["cart_notes"] = {}
        return _render_saved_order(
            order,
            email_sent=email_sent,
            fallback_used=fallback_used,
        )

    @app.route("/download/order/<token>.csv")
    def download_order_csv(token: str):
        order = _load_download_order(token)
        csv_text = order.csv_text or build_order_csv(
            order.order_number,
            order.customer,
            _saved_order_rows(order),
            submitted_at=order.created_at,
        )

        data = csv_text.encode("utf-8")
        filename = order.csv_filename
        if not isinstance(filename, str) or not filename:
            filename = f"ce_order_{order.order_number.lstrip('#')}.csv"
        return send_file(
            io.BytesIO(data),
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/download/order/<token>.pdf")
    def download_order_pdf(token: str):
        order = _load_download_order(token)
        rows = _saved_order_rows(order)
        if not rows:
            abort(404)
        pdf_bytes = cart_to_pdf_bytes(
            rows,
            base_dir / "static" / "product_images",
            customer=order.customer,
            order_id=order.order_number,
        )
        order_id = order.order_number.replace("#", "")
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=(
                f"ce_order_{order_id}.pdf"
                if order_id
                else "ce_order.pdf"
            ),
        )

    @app.route("/api/cart/count")
    def api_cart_count():
        cart_data = get_cart()
        return jsonify({"total_items": cart_total_items(cart_data), "distinct_items": len(cart_data)})

    @app.route("/api/cart/add", methods=["POST"])
    def api_cart_add():
        payload = request.get_json(force=True, silent=True) or {}
        code = payload.get("code")
        try:
            qty = int(payload.get("qty") or 1)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid_quantity"}), 400
        qty = max(1, min(999, qty))

        pmap = products_by_code(load_products())
        if code not in pmap:
            return jsonify({"ok": False, "error": "unknown_code"}), 400

        cart_data = get_cart()
        cart_data[code] = max(1, min(999, cart_data.get(code, 0) + qty))
        session["cart"] = cart_data
        return jsonify({"ok": True, "total_items": cart_total_items(cart_data), "distinct_items": len(cart_data)})

    @app.route("/api/cart/set", methods=["POST"])
    def api_cart_set():
        payload = request.get_json(force=True, silent=True) or {}
        code = payload.get("code")
        try:
            qty = int(payload.get("qty") or 0)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid_quantity"}), 400
        qty = max(0, min(999, qty))

        pmap = products_by_code(load_products())
        if code not in pmap:
            return jsonify({"ok": False, "error": "unknown_code"}), 400

        cart_data = get_cart()
        notes_by_code = get_cart_notes(session, cart_data)
        if qty == 0:
            cart_data.pop(code, None)
            notes_by_code.pop(code, None)
        else:
            cart_data[code] = qty
        session["cart"] = cart_data
        session["cart_notes"] = notes_by_code
        return jsonify({"ok": True, "total_items": cart_total_items(cart_data), "distinct_items": len(cart_data)})

    @app.route("/api/cart/remove", methods=["POST"])
    def api_cart_remove():
        payload = request.get_json(force=True, silent=True) or {}
        code = payload.get("code")
        code_str = code if isinstance(code, str) else ""
        cart_data = get_cart()
        notes_by_code = get_cart_notes(session, cart_data)
        cart_data.pop(code_str, None)
        notes_by_code.pop(code_str, None)
        session["cart"] = cart_data
        session["cart_notes"] = notes_by_code
        return jsonify({"ok": True, "total_items": cart_total_items(cart_data), "distinct_items": len(cart_data)})

    @app.route("/api/cart/clear", methods=["POST"])
    def api_cart_clear():
        session["cart"] = {}
        session["cart_notes"] = {}
        return jsonify({"ok": True, "total_items": 0, "distinct_items": 0})

    @app.route("/api/cart/note", methods=["POST"])
    def api_cart_note():
        payload = request.get_json(force=True, silent=True) or {}
        code = payload.get("code")
        code_str = code if isinstance(code, str) else ""

        pmap = products_by_code(load_products())
        if code_str not in pmap:
            return jsonify({"ok": False, "error": "unknown_code"}), 400

        cart_data = get_cart()
        if code_str not in cart_data:
            return jsonify({"ok": False, "error": "item_not_in_cart"}), 400

        note = normalize_item_note(payload.get("note"))
        notes_by_code = get_cart_notes(session, cart_data)
        if note:
            notes_by_code[code_str] = note
        else:
            notes_by_code.pop(code_str, None)

        session["cart_notes"] = notes_by_code
        return jsonify({"ok": True, "code": code_str, "note": notes_by_code.get(code_str, "")})
