from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import smtplib
from flask import Flask, abort, jsonify, render_template, request, send_file, session

app = Flask(__name__)

# On Render: set SECRET_KEY to a long random string
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

BASE_DIR = Path(__file__).parent
CATALOG_PATH = BASE_DIR / "catalog" / "products.json"
COLLECTIONS_PATH = BASE_DIR / "catalog" / "collections.json"
SOCIAL_PATH = BASE_DIR / "catalog" / "social.json"
TEAM_PATH = BASE_DIR / "catalog" / "team.json"


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "item"


def _code_num(code: str) -> int | None:
    m = re.match(r"^\s*(\d+)", code or "")
    return int(m.group(1)) if m else None


def _compute_slug(code: str, name: str) -> str:
    c = (code or "").strip()
    n = (name or "").strip()
    if not n or n.lower() == c.lower():
        return _slugify(c)
    return _slugify(f"{c} {n}")


def _compute_seo_title(code: str, name: str) -> str:
    c = (code or "").strip()
    n = (name or "").strip()
    if not n or n.lower() == c.lower():
        return f"{c} | Wholesale 14K Gold Earrings"
    return f"{c} {n} | Wholesale 14K Gold Earrings"


def normalize_product(p: dict[str, Any]) -> dict[str, Any]:
    code = (p.get("code") or "").strip()
    name = (p.get("name") or "").strip() or code
    description = (p.get("description") or "").strip()
    collection = (p.get("collection") or "other").strip() or "other"
    image = (p.get("image") or "").strip()
    tags = p.get("tags") or []
    if not isinstance(tags, list):
        tags = []

    slug = _compute_slug(code, name)
    seo_title = _compute_seo_title(code, name)
    seo_desc = description  # default: use description (no code repetition)

    # tolerate extra keys if present, but we now generate derived ones
    out = dict(p)
    out.update(
        {
            "id": code.lower(),
            "code": code,
            "name": name,
            "description": description,
            "collection": collection,
            "image": image,
            "tags": tags,
            "slug": slug,
            "seo": {"title": seo_title, "description": seo_desc},
        }
    )
    return out


def load_products() -> list[dict[str, Any]]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [normalize_product(p) for p in (raw or [])]


def products_by_code(products: list[dict[str, Any]]) -> dict:
    return {p.get("code"): p for p in products if p.get("code")}


def load_social() -> dict[str, Any]:
    if SOCIAL_PATH.exists():
        with open(SOCIAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tiktok": {"profile_url": "", "videos": []}, "instagram": {"profile_url": "", "reels_url": ""}}


def load_team() -> dict[str, Any]:
    if TEAM_PATH.exists():
        with open(TEAM_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"headline": "Meet the team", "subheadline": "", "members": []}


def load_collections_cfg() -> dict[str, Any]:
    if COLLECTIONS_PATH.exists():
        with open(COLLECTIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"order": [], "labels": {}}


def filter_products(products: list[dict[str, Any]], q: str) -> list[dict[str, Any]]:
    q = (q or "").strip().lower()
    if not q:
        return products

    out: list[dict[str, Any]] = []
    for p in products:
        hay = " ".join(
            [
                str(p.get("code", "")),
                str(p.get("name", "")),
                str(p.get("collection", "")),
                str(p.get("description", "")),
                " ".join(p.get("tags", []) or []),
            ]
        ).lower()
        if q in hay:
            out.append(p)
    return out


@dataclass
class Section:
    key: str
    title: str
    items: list[dict[str, Any]]


def build_sections(products: list[dict[str, Any]], cfg: dict[str, Any]) -> list[Section]:
    order: list[str] = cfg.get("order") or []
    labels: dict[str, str] = cfg.get("labels") or {}

    by_collection: dict[str, list[dict[str, Any]]] = {}
    for p in products:
        by_collection.setdefault(p.get("collection", "other"), []).append(p)

    sections: list[Section] = []
    for key in order:
        items = by_collection.get(key, [])
        if items:
            sections.append(Section(key=key, title=labels.get(key, key.replace("-", " ").title()), items=items))

    for key, items in by_collection.items():
        if key in set(order):
            continue
        sections.append(Section(key=key, title=labels.get(key, key.replace("-", " ").title()), items=items))

    return sections


def get_cart() -> dict[str, int]:
    cart = session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
    clean: dict[str, int] = {}
    for code, qty in cart.items():
        try:
            q = int(qty)
        except Exception:
            q = 0
        if q > 0:
            clean[code] = max(1, min(999, q))
    session["cart"] = clean
    return clean


def cart_total_items(cart: dict[str, int]) -> int:
    return int(sum(cart.values()))


def cart_items(pmap: dict[str, dict[str, Any]], cart: dict[str, int]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code, qty in cart.items():
        p = pmap.get(code)
        if p:
            items.append({"product": p, "qty": qty})
    return items


def cart_to_csv_bytes(meta: dict[str, str], items: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", meta.get("name", "")])
    w.writerow(["company", meta.get("company", "")])
    w.writerow(["phone", meta.get("phone", "")])
    w.writerow(["notes", meta.get("notes", "")])
    w.writerow([])
    w.writerow(["code", "name", "qty", "collection", "material", "stone", "size_mm"])
    for row in items:
        p = row["product"]
        w.writerow(
            [
                p.get("code", ""),
                p.get("name", ""),
                row["qty"],
                p.get("collection", ""),
                p.get("material", ""),
                p.get("stone", ""),
                p.get("size_mm", ""),
            ]
        )
    return buf.getvalue().encode("utf-8")


def send_order_email(subject: str, body: str, csv_bytes: bytes, filename: str) -> bool:
    """Email the CSV to your team if SMTP_* + EMAIL_TO are configured."""
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    email_to = os.getenv("EMAIL_TO", "").strip()
    email_from = os.getenv("EMAIL_FROM", smtp_user).strip()

    if not (smtp_host and smtp_user and smtp_pass and email_to and email_from):
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.set_content(body)
    msg.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=filename)

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)

    return True


@app.context_processor
def inject_site_config():
    return {
        "plausible_domain": os.getenv("PLAUSIBLE_DOMAIN", "").strip(),
        "site_base_url": os.getenv("SITE_BASE_URL", "").strip(),
        "social": load_social(),
        "team": load_team(),
        "site_name": "California Earrings",
    }


@app.route("/")
def index():
    products = load_products()
    q = request.args.get("q", "")
    products = filter_products(products, q)

    cfg = load_collections_cfg()
    sections = build_sections(products, cfg)

    return render_template("index.html", sections=sections, q=q)


@app.route("/product/<slug>")
def product_detail(slug: str):
    products = load_products()
    product = next((p for p in products if p.get("slug") == slug), None)
    if not product:
        abort(404)
    return render_template("product.html", product=product)


@app.route("/cart")
def cart():
    pmap = products_by_code(load_products())
    cart = get_cart()
    items = cart_items(pmap, cart)
    return render_template("cart.html", items=items, total_items=cart_total_items(cart))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    pmap = products_by_code(load_products())
    cart = get_cart()
    items = cart_items(pmap, cart)

    if request.method == "GET":
        return render_template("checkout.html", items=items)

    name = (request.form.get("name") or "").strip()
    company = (request.form.get("company") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if not (name and company and phone) or len(items) == 0:
        return render_template("checkout.html", items=items), 400

    meta = {"name": name, "company": company, "phone": phone, "notes": notes}
    csv_bytes = cart_to_csv_bytes(meta, items)

    token = secrets.token_urlsafe(24)
    session["last_order_csv"] = csv_bytes.decode("utf-8")
    session["last_order_token"] = token

    subject = f"California Earrings inquiry — {company} ({name})"
    body = f"""Inquiry submitted.

Name: {name}
Company: {company}
Phone: {phone}
Notes: {notes}

Distinct items: {len(items)}
Total qty: {cart_total_items(cart)}
"""
    filename = f"order_{company.lower().replace(' ', '_')}_{token[:8]}.csv"

    sent = False
    try:
        sent = send_order_email(subject, body, csv_bytes, filename)
    except Exception:
        sent = False

    # clear cart after submit
    session["cart"] = {}
    return render_template("order_submitted.html", token=token, email_sent=sent)


@app.route("/download/order/<token>.csv")
def download_order_csv(token: str):
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
        download_name=f"inquiry_{token[:8]}.csv",
    )


# --- cart api ---
@app.route("/api/cart/count")
def api_cart_count():
    cart = get_cart()
    return jsonify({"total_items": cart_total_items(cart), "distinct_items": len(cart)})


@app.route("/api/cart/add", methods=["POST"])
def api_cart_add():
    payload = request.get_json(force=True, silent=True) or {}
    code = payload.get("code")
    qty = int(payload.get("qty") or 1)
    qty = max(1, min(999, qty))

    pmap = products_by_code(load_products())
    if code not in pmap:
        return jsonify({"ok": False, "error": "unknown_code"}), 400

    cart = get_cart()
    cart[code] = max(1, min(999, cart.get(code, 0) + qty))
    session["cart"] = cart
    return jsonify({"ok": True, "total_items": cart_total_items(cart), "distinct_items": len(cart)})


@app.route("/api/cart/set", methods=["POST"])
def api_cart_set():
    payload = request.get_json(force=True, silent=True) or {}
    code = payload.get("code")
    qty = int(payload.get("qty") or 0)
    qty = max(0, min(999, qty))

    pmap = products_by_code(load_products())
    if code not in pmap:
        return jsonify({"ok": False, "error": "unknown_code"}), 400

    cart = get_cart()
    if qty == 0:
        cart.pop(code, None)
    else:
        cart[code] = qty
    session["cart"] = cart
    return jsonify({"ok": True, "total_items": cart_total_items(cart), "distinct_items": len(cart)})


@app.route("/api/cart/remove", methods=["POST"])
def api_cart_remove():
    payload = request.get_json(force=True, silent=True) or {}
    code = payload.get("code")
    cart = get_cart()
    cart.pop(code, None)
    session["cart"] = cart
    return jsonify({"ok": True, "total_items": cart_total_items(cart), "distinct_items": len(cart)})


@app.route("/team")
def team_page():
    return render_template("team.html", team=load_team())


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    body = f"""User-agent: *
Allow: /
Sitemap: {base}/sitemap.xml
"""
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/sitemap.xml")
def sitemap():
    products = load_products()
    base_url = request.url_root.rstrip("/")
    return (
        render_template("sitemap.xml", products=products, base_url=base_url),
        200,
        {"Content-Type": "application/xml"},
    )


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host="0.0.0.0", port=port)
