from __future__ import annotations

import io
import os
import secrets
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for

from domains.cart import (
    cart_items,
    cart_to_csv_bytes,
    cart_total_items,
    get_cart as get_cart_from_session,
    get_cart_notes,
    normalize_item_note,
)
from domains.catalog import (
    build_sections,
    filter_products,
    load_collections_cfg as load_collections_cfg_from_path,
    load_products as load_products_from_path,
    load_social as load_social_from_path,
    products_by_code,
)
from domains.emailing import send_order_email
from domains.seo import build_sitemap_urls as build_sitemap_urls_from_context
from domains.seo import canonical_base_url, iso_lastmod
from domains.team import (
    build_member_vcard,
    build_team_members,
    get_team_member_by_slug as get_team_member_by_slug_in_team,
    load_team as load_team_from_path,
    slugify,
)

app = Flask(__name__)

load_dotenv()
app.secret_key = os.environ["SECRET_KEY"]

if not app.secret_key:
    raise RuntimeError("SECRET_KEY env var not set")

BASE_DIR = Path(__file__).parent
CATALOG_PATH = BASE_DIR / "catalog" / "products.json"
COLLECTIONS_PATH = BASE_DIR / "catalog" / "collections.json"
SOCIAL_PATH = BASE_DIR / "catalog" / "social.json"
TEAM_PATH = BASE_DIR / "catalog" / "team.json"


def _canonical_base_url() -> str:
    return canonical_base_url(request.url_root)


def _iso_lastmod(*paths: Path) -> str | None:
    return iso_lastmod(*paths)


def _slugify(value: str) -> str:
    return slugify(value)


def load_products() -> list[dict[str, Any]]:
    return load_products_from_path(CATALOG_PATH)


def load_social() -> dict[str, Any]:
    return load_social_from_path(SOCIAL_PATH)


def load_team() -> dict[str, Any]:
    return load_team_from_path(TEAM_PATH)


def load_collections_cfg() -> dict[str, Any]:
    return load_collections_cfg_from_path(COLLECTIONS_PATH)


def get_cart() -> dict[str, int]:
    return get_cart_from_session(session)


def get_team_member_by_slug(member_slug: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    team = load_team()
    members, member = get_team_member_by_slug_in_team(member_slug, team)
    return team, members, member


def build_sitemap_urls(base_url: str) -> list[dict[str, str | float | None]]:
    members = build_team_members(load_team())
    return build_sitemap_urls_from_context(
        base_url,
        base_dir=BASE_DIR,
        catalog_path=CATALOG_PATH,
        collections_path=COLLECTIONS_PATH,
        team_path=TEAM_PATH,
        team_members=members,
    )


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


@app.route("/catalog/")
def catalog_start():
    products = load_products()
    cfg = load_collections_cfg()
    sections = build_sections(products, cfg)
    if not sections:
        return redirect(url_for("index"))
    return redirect(f"{url_for('index')}#section-{sections[0].key}")


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
Total qty: {cart_total_items(cart_data)}
"""
    filename = f"order_{company.lower().replace(' ', '_')}_{token[:8]}.csv"

    sent = False
    try:
        sent = send_order_email(subject, body, csv_bytes, filename)
    except Exception:
        sent = False

    session["cart"] = {}
    session["cart_notes"] = {}
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


@app.route("/team")
def team_page():
    team = load_team()
    members = build_team_members(team)
    return render_template("team.html", team=team, members=members)


@app.route("/team/<member_slug>")
def team_member_page(member_slug: str):
    team, _, member = get_team_member_by_slug(member_slug)
    if not member:
        abort(404)
    return render_template("team_member.html", team=team, member=member)


@app.route("/team/<member_slug>/contact.vcf")
def team_member_vcard(member_slug: str):
    team, _, member = get_team_member_by_slug(member_slug)
    if not member:
        abort(404)

    vcard_text = build_member_vcard(member, team)
    filename = f"{_slugify(member.get('name', 'contact'))}.vcf"
    return send_file(
        io.BytesIO(vcard_text.encode("utf-8")),
        mimetype="text/vcard; charset=utf-8",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/robots.txt")
def robots():
    base = _canonical_base_url()
    body = f"""User-agent: *
Allow: /
Disallow: /api/
Disallow: /cart
Disallow: /checkout
Disallow: /download/
Sitemap: {base}/sitemap.xml
"""
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/sitemaps.xml")
@app.route("/sitemap.xml")
def sitemap():
    base_url = _canonical_base_url()
    urls = build_sitemap_urls(base_url)
    return (
        render_template("sitemap.xml", urls=urls),
        200,
        {"Content-Type": "application/xml"},
    )


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
