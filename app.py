from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, request, session, url_for

from domains.cart import (
    cart_total_items,
    get_cart as get_cart_from_session,
)
from domains.catalog import (
    load_collections_cfg as load_collections_cfg_from_path,
    load_products as load_products_from_path,
    load_social as load_social_from_path,
)
from domains.cart_routes import register_cart_routes
from domains.emailing import send_order_email
from domains.faqs import load_faqs as load_faqs_from_path
from domains.file_cache import get_path_version
from domains.site_routes import register_site_routes
from domains.seo import build_sitemap_urls as build_sitemap_urls_from_context
from domains.seo import canonical_base_url
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


def get_reels_path() -> Path:
    return REELS_PATH


def _canonical_base_url() -> str:
    return canonical_base_url(request.url_root)


def _slugify(value: str) -> str:
    return slugify(value)


def asset_url(filename: str) -> str:
    static_path = BASE_DIR / "static" / filename
    version = get_path_version(static_path)
    if version is None:
        return url_for("static", filename=filename)

    return url_for("static", filename=filename, v=version)


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
    cart = get_cart()
    return {
        "asset_url": asset_url,
        "cart_item_count": cart_total_items(cart),
        "current_year": date.today().year,
        "plausible_domain": os.getenv("PLAUSIBLE_DOMAIN", "").strip(),
        "site_base_url": os.getenv("SITE_BASE_URL", "").strip(),
        "social": load_social(),
        "site_name": "California Earrings",
    }

register_site_routes(
    app,
    base_dir=BASE_DIR,
    get_reels_path=get_reels_path,
    load_products=load_products,
    load_collections_cfg=load_collections_cfg,
    load_team=load_team,
    load_faqs=load_faqs,
    get_cart=get_cart,
    get_team_member_by_slug=get_team_member_by_slug,
    build_sitemap_urls=build_sitemap_urls,
    canonical_base_url=_canonical_base_url,
    slugify=_slugify,
)

register_cart_routes(
    app,
    base_dir=BASE_DIR,
    load_products=load_products,
    get_cart=get_cart,
    send_order_email=send_order_email,
    canonical_base_url=_canonical_base_url,
)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
