from __future__ import annotations

import io
import os
import secrets
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for

from domains.cart import (
    cart_items,
    cart_to_pdf_bytes,
    cart_to_csv_bytes,
    cart_total_items,
    get_cart as get_cart_from_session,
    get_cart_notes,
    normalize_item_note,
    order_rows_from_items,
)
from domains.catalog import (
    build_sections,
    find_product_by_code,
    load_collections_cfg as load_collections_cfg_from_path,
    load_products as load_products_from_path,
    load_social as load_social_from_path,
    products_by_code,
)
from domains.emailing import send_order_email
from domains.faqs import load_faqs as load_faqs_from_path
from domains.homepage import build_homepage_context
from domains.reels import load_random_reels
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
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 30

load_dotenv()
app.secret_key = os.environ["SECRET_KEY"]

@app.after_request
def add_no_cache_for_html(response):
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response
if not app.secret_key:
    raise RuntimeError("SECRET_KEY env var not set")

BASE_DIR = Path(__file__).parent
CATALOG_PATH = BASE_DIR / "catalog" / "products.json"
COLLECTIONS_PATH = BASE_DIR / "catalog" / "collections.json"
SOCIAL_PATH = BASE_DIR / "catalog" / "social.json"
TEAM_PATH = BASE_DIR / "catalog" / "team.json"
FAQS_PATH = BASE_DIR / "catalog" / "faqs.json"
REELS_PATH = BASE_DIR / "static" / "reels"


def _canonical_base_url() -> str:
    return canonical_base_url(request.url_root)


def _iso_lastmod(*paths: Path) -> str | None:
    return iso_lastmod(*paths)


def _slugify(value: str) -> str:
    return slugify(value)


def asset_url(filename: str) -> str:
    static_path = BASE_DIR / "static" / filename
    if not static_path.exists() or not static_path.is_file():
        return url_for("static", filename=filename)

    return url_for("static", filename=filename, v=static_path.stat().st_mtime_ns)


def load_products() -> list[dict[str, Any]]:
    return load_products_from_path(CATALOG_PATH)


def load_social() -> dict[str, Any]:
    return load_social_from_path(SOCIAL_PATH)


def load_team() -> dict[str, Any]:
    return load_team_from_path(TEAM_PATH)


def load_faqs() -> list[dict[str, Any]]:
    return load_faqs_from_path(FAQS_PATH)


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
    product_codes = [
        str(product.get("code") or "").strip()
        for product in load_products()
        if str(product.get("code") or "").strip()
    ]
    return build_sitemap_urls_from_context(
        base_url,
        base_dir=BASE_DIR,
        catalog_path=CATALOG_PATH,
        collections_path=COLLECTIONS_PATH,
        faqs_path=FAQS_PATH,
        reels_path=REELS_PATH,
        team_path=TEAM_PATH,
        team_members=members,
        product_codes=product_codes,
    )


@app.context_processor
def inject_site_config():
    return {
        "asset_url": asset_url,
        "current_year": date.today().year,
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
    cfg = load_collections_cfg()
    context = build_homepage_context(products, q, cfg, REELS_PATH)
    return render_template("index.html", **context)


@app.route("/catalog/")
def catalog_start():
    products = load_products()
    cfg = load_collections_cfg()
    sections = build_sections(products, cfg)
    if not sections:
        return redirect(url_for("index"))
    return redirect(f"{url_for('index')}#section-{sections[0].key}")


@app.route("/product/<product_code>")
def product_detail(product_code: str):
    products = load_products()
    product = find_product_by_code(products, product_code)
    if not product:
        abort(404)

    canonical_code = str(product.get("code") or "").strip()
    if canonical_code and canonical_code != product_code:
        return redirect(url_for("product_detail", product_code=canonical_code), code=301)

    cart_data = get_cart()
    initial_qty = max(0, min(999, int(cart_data.get(canonical_code, 0))))

    cfg = load_collections_cfg()
    labels: dict[str, str] = cfg.get("labels") or {}
    collection_key = str(product.get("collection") or "other")
    collection_label = labels.get(
        collection_key, collection_key.replace("-", " ").title())

    return render_template(
        "product_detail.html",
        product=product,
        initial_qty=initial_qty,
        collection_label=collection_label,
    )


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
    client_email = (request.form.get("email") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if not (name and company and phone) or len(items) == 0:
        return render_template("checkout.html", items=items), 400

    order_rows = order_rows_from_items(items)
    csv_bytes = cart_to_csv_bytes(order_rows)

    token = secrets.token_urlsafe(24)
    session["last_order_csv"] = csv_bytes.decode("utf-8")
    session["last_order_rows"] = order_rows
    session["last_order_token"] = token

    total_items = len(items)
    total_quantity = cart_total_items(cart_data)

    subject = "Thank you for your Order | California Earrings"
    body = f"""Hi {company},

Thank you for submtiting your inquiry. We'll get back to you shortly with the full invoice.

Total items: {total_items}
Total quantity: {total_quantity}

Best,

California Earrings
ce_logo_full.png
"""
    logo_url = f"{_canonical_base_url()}{url_for('static', filename='assets/ce_logo_full.png')}"
    html_body = f"""<p>Hi {company},</p>
<p>Thank you for submtiting your inquiry. We'll get back to you shortly with the full invoice.</p>
<p>Total items: {total_items}<br>
Total quantity: {total_quantity}</p>
<p>Best,</p>
<p>California Earrings<br><br>
<img src=\"{logo_url}\" alt=\"California Earrings\" style=\"max-width: 220px; height: auto;\"></p>
"""
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

    pdf_bytes = cart_to_pdf_bytes(rows, BASE_DIR / "static" / "product_images")
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

    photo_url = None
    if member.get("photo"):
        photo_url = url_for("static", filename=f"team/{member['photo']}", _external=True)

    vcard_text = build_member_vcard(member, team, photo_url=photo_url)
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


@app.route("/faq")
def faq_redirect():
    return redirect(url_for("faqs_page"), code=301)


@app.route("/faqs")
def faqs_page():
    return render_template("faqs.html", faq_items=load_faqs())


@app.route("/reels")
def reels_page():
    reels = load_random_reels(REELS_PATH)
    return render_template("reels.html", reels=reels)


@app.route("/robots.txt")
def robots():
    base = _canonical_base_url()
    return (
        render_template("robots.txt", sitemap_url=f"{base}/sitemap.xml"),
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
    )


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
