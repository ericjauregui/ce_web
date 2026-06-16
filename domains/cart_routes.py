from __future__ import annotations

import io
import re
import secrets
from pathlib import Path
from typing import Any, Callable

from flask import Flask, abort, jsonify, render_template, request, send_file, session, url_for

from domains.cart import (
    cart_items,
    cart_to_pdf_bytes,
    cart_total_items,
    get_cart_notes,
    normalize_item_note,
    order_rows_from_items,
)
from domains.catalog import products_by_code
from domains.emailing import OrderEmailDeliveryError
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
    def _build_order_customer(form_values: dict[str, str]) -> dict[str, str]:
        return {
            "name": form_values.get("name", ""),
            "company": form_values.get("company", ""),
            "phone": normalize_checkout_phone(
                form_values.get("phone_country_code", ""),
                form_values.get("phone", ""),
            ),
            "email": form_values.get("email", ""),
            "city": form_values.get("city", ""),
            "state": form_values.get("state", ""),
            "country": form_values.get("country", ""),
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
        return render_template("cart.html", items=items, total_items=cart_total_items(cart_data))

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
            ), status_code

        if request.method == "GET":
            return render_checkout_page()

        name = (request.form.get("name") or "").strip()
        company = (request.form.get("company") or "").strip()
        phone_country_display = (request.form.get("phone_country") or "").strip()
        phone_country_key = resolve_checkout_phone_country_key(
            request.form.get("phone_country_code") or "",
            phone_country_display,
        )
        phone = normalize_checkout_phone(phone_country_key, request.form.get("phone") or "")
        client_email = (request.form.get("email") or "").strip()
        city = (request.form.get("city") or "").strip()
        state = (request.form.get("state") or "").strip()
        country = (request.form.get("country") or "").strip()
        country_key = resolve_checkout_country_key(request.form.get("country_key") or "", country)
        if country_key and not country:
            country = CHECKOUT_COUNTRY_LABELS_BY_KEY[country_key]

        form_values = {
            "name": name,
            "company": company,
            "phone": (request.form.get("phone") or "").strip(),
            "phone_country": phone_country_display,
            "phone_country_code": phone_country_key,
            "email": client_email,
            "city": city,
            "state": state,
            "country": country,
            "country_key": country_key,
            "notes": (request.form.get("notes") or "").strip(),
        }

        if not (name and company and phone_country_key and phone and city and state and country and country_key) or len(items) == 0:
            return render_checkout_page(
                status_code=400,
                form_values=form_values,
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
        order_rows = order_rows_from_items(items)

        def store_order_session(csv_text: str, order_id: str, csv_filename: str) -> str:
            token = secrets.token_urlsafe(24)
            session["last_order_csv"] = csv_text
            session["last_order_rows"] = order_rows
            session["last_order_token"] = token
            session["last_order_id"] = order_id
            session["last_order_csv_filename"] = csv_filename
            return token

        try:
            result = send_order_email(customer, validated_items)
        except OrderEmailDeliveryError as exc:
            token = store_order_session(exc.csv_text, exc.order_id, exc.csv_path.name)
            return render_template(
                "order_submitted.html",
                token=token,
                email_sent=False,
                fallback_used=False,
                client_email=client_email,
                order_id=exc.order_id,
                order_rows=order_rows,
            )
        except Exception:
            return render_checkout_page(
                status_code=500,
                form_values=form_values,
                submission_error="Order could not be submitted automatically. Please contact us directly.",
            )

        token = store_order_session(
            str(result.get("csv_text") or ""),
            str(result.get("order_id") or ""),
            str(result.get("csv_filename") or "order.csv"),
        )
        session["cart"] = {}
        session["cart_notes"] = {}
        return render_template(
            "order_submitted.html",
            token=token,
            email_sent=bool(result.get("ok")),
            fallback_used=bool(result.get("fallback_used")),
            client_email=client_email,
            order_id=str(result.get("order_id") or ""),
            order_rows=order_rows,
        )

    @app.route("/download/order/<token>.csv")
    def download_order_csv(token: str):
        from datetime import date

        if session.get("last_order_token") != token:
            abort(404)
        csv_text = session.get("last_order_csv")
        if not csv_text:
            abort(404)

        data = csv_text.encode("utf-8")
        filename = session.get("last_order_csv_filename")
        if not isinstance(filename, str) or not filename:
            order_id = str(session.get("last_order_id") or "").replace("#", "")
            filename = f"order_{order_id or date.today().strftime('%Y%m%d')}.csv"
        return send_file(
            io.BytesIO(data),
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/download/order/<token>.pdf")
    def download_order_pdf(token: str):
        from datetime import date

        if session.get("last_order_token") != token:
            abort(404)

        rows = session.get("last_order_rows")
        if not isinstance(rows, list) or not rows:
            abort(404)

        pdf_bytes = cart_to_pdf_bytes(rows, base_dir / "static" / "product_images")
        order_id = str(session.get("last_order_id") or "").replace("#", "")
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=(
                f"ce_order_{order_id}.pdf"
                if order_id
                else f"ce_order_{date.today().strftime('%m%d%y')}_{token[:4].lower()}.pdf"
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
        qty = int(payload.get("qty") or 1)
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
        qty = int(payload.get("qty") or 0)
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
