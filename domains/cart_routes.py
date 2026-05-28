from __future__ import annotations

import io
import re
import secrets
from pathlib import Path
from typing import Any, Callable

from flask import Flask, abort, jsonify, render_template, request, send_file, session, url_for

from domains.cart import (
    cart_items,
    cart_to_csv_bytes,
    cart_to_pdf_bytes,
    cart_total_items,
    get_cart_notes,
    normalize_item_note,
    order_rows_from_items,
)
from domains.catalog import products_by_code
from domains.location_options import (
    CHECKOUT_COUNTRY_KEY_BY_LABEL,
    CHECKOUT_COUNTRY_LABELS_BY_KEY,
    CHECKOUT_COUNTRY_OPTIONS,
    CHECKOUT_SUBDIVISION_OPTIONS_BY_COUNTRY_KEY,
    DEFAULT_LOCATION_COUNTRY_KEY,
    get_location_country_key_from_label,
    get_location_country_option,
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
SendOrderEmail = Callable[..., bool]
CanonicalBaseUrl = Callable[[], str]


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
    def _build_order_email(
        name: str,
        company: str,
        phone: str,
        client_email: str,
        city: str,
        state: str,
        country: str,
        total_items: int,
        total_quantity: int,
    ) -> tuple[str, str, str]:
        subject = "Thank you for your Order | California Earrings"
        contact_lines = [
            f"Contact: {name}",
            f"Company: {company}",
            f"Phone: {phone}",
            f"Email: {client_email or 'Not provided'}",
            f"Location: {city}, {state}, {country}",
        ]
        contact_block = "\n".join(contact_lines)
        body = f"""Hi {company},

Thank you for submtiting your inquiry. We'll get back to you shortly with the full invoice.

{contact_block}

Total items: {total_items}
Total quantity: {total_quantity}

Best,

California Earrings
ce_logo_full.png
"""
        logo_url = f"{canonical_base_url()}{url_for('static', filename='assets/ce_logo_full.png')}"
        html_contact_lines = "".join(f"<li>{line}</li>" for line in contact_lines)
        html_body = f"""<p>Hi {company},</p>
    <p>Thank you for submtiting your inquiry. We'll get back to you shortly with the full invoice.</p>
    <ul>{html_contact_lines}</ul>
    <p>Total items: {total_items}<br>
    Total quantity: {total_quantity}</p>
    <p>Best,</p>
    <p>California Earrings<br><br>
    <img src=\"{logo_url}\" alt=\"California Earrings\" style=\"max-width: 220px; height: auto;\"></p>
    """
        return subject, body, html_body

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
        ):
            default_country_key, default_country_label = get_location_country_option(DEFAULT_LOCATION_COUNTRY_KEY)
            default_phone_country_key, _, _ = get_phone_country_option(DEFAULT_PHONE_COUNTRY_KEY)
            values = {
                "name": "",
                "company": "",
                "phone": "",
                "phone_country_code": default_phone_country_key,
                "phone_country": CHECKOUT_PHONE_COUNTRY_DISPLAY_BY_KEY[default_phone_country_key],
                "email": "",
                "city": "",
                "state": "",
                "country_key": default_country_key,
                "country": default_country_label,
                "notes": "",
            }
            if form_values:
                values.update({key: value for key, value in form_values.items() if value is not None})

            resolved_phone_key = resolve_checkout_phone_country_key(
                values.get("phone_country_code", ""),
                values.get("phone_country", ""),
                default_to_default=not values.get("phone_country") and not values.get("phone_country_code"),
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

        order_rows = order_rows_from_items(items)
        csv_bytes = cart_to_csv_bytes(order_rows)

        token = secrets.token_urlsafe(24)
        session["last_order_csv"] = csv_bytes.decode("utf-8")
        session["last_order_rows"] = order_rows
        session["last_order_token"] = token

        total_items = len(items)
        total_quantity = cart_total_items(cart_data)
        subject, body, html_body = _build_order_email(
            name,
            company,
            phone,
            client_email,
            city,
            state,
            country,
            total_items,
            total_quantity,
        )
        filename = f"order_{company.lower().replace(' ', '_')}_{token[:8]}.csv"

        sent = False
        try:
            sent = send_order_email(
                subject,
                body,
                csv_bytes,
                filename,
                client_email=client_email,
                html_body=html_body,
            )
        except Exception:
            sent = False

        session["cart"] = {}
        session["cart_notes"] = {}
        return render_template(
            "order_submitted.html",
            token=token,
            email_sent=sent,
            client_email=client_email,
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
        return send_file(
            io.BytesIO(data),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"ce_order_{date.today().strftime('%m%d%y')}_{token[:4].lower()}.csv",
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
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"ce_order_{date.today().strftime('%m%d%y')}_{token[:4].lower()}.pdf",
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
