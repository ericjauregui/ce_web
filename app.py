from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, g, request, session, url_for

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
from domains.cache_control import PUBLIC_ENDPOINT_POLICIES, install_cache_control
from domains.connect import load_connect_event as load_connect_event_from_path
from domains.rate_limiting import install_rate_limiting
from domains.emailing import send_order_email
from domains.faqs import load_faqs as load_faqs_from_path
from domains.file_cache import get_path_version
from domains.image_assets import PRODUCT_IMAGE_SIZES
from domains.image_asset_cache import ImageAssetCache
from domains.site_routes import register_site_routes
from domains.site_analytics import install_analytics_session_cookie
from domains.seo import build_sitemap_urls as build_sitemap_urls_from_context
from domains.seo import canonical_base_url
from domains.team import (
    build_member_vcard,
    build_team_members,
    ensure_team_qr_assets,
    get_team_member_by_slug as get_team_member_by_slug_in_team,
    load_team as load_team_from_path,
    slugify,
)
from domains.trade_shows import load_trade_show as load_trade_show_from_path

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 365
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_REFRESH_EACH_REQUEST"] = False
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024

load_dotenv()
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("RENDER", "").strip().lower() == "true"
    or os.getenv("SESSION_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}
)
app.secret_key = os.environ["SECRET_KEY"]


install_cache_control(app)
install_analytics_session_cookie(app)


if not app.secret_key:
    raise RuntimeError("SECRET_KEY env var not set")

BASE_DIR = Path(__file__).parent
CATALOG_PATH = BASE_DIR / "catalog" / "products.json"
COLLECTIONS_PATH = BASE_DIR / "catalog" / "collections.json"
SOCIAL_PATH = BASE_DIR / "catalog" / "social.json"
TEAM_PATH = BASE_DIR / "catalog" / "team.json"
FAQS_PATH = BASE_DIR / "catalog" / "faqs.json"
TRADE_SHOWS_PATH = BASE_DIR / "catalog" / "trade_shows.json"
REELS_PATH = BASE_DIR / "static" / "reels"


def get_reels_path() -> Path:
    return REELS_PATH


def _canonical_base_url() -> str:
    return canonical_base_url(request.url_root)


def _slugify(value: str) -> str:
    return slugify(value)


def asset_url(filename: str) -> str:
    if filename == "vendor/bootstrap/bootstrap.min.css":
        from domains.stylesheets import bootstrap_stylesheet
        filename = bootstrap_stylesheet(BASE_DIR)
    static_path = BASE_DIR / "static" / filename
    version = get_path_version(static_path)
    if version is None:
        return url_for("static", filename=filename)

    return url_for("static", filename=filename, v=version)


def load_products() -> list[dict[str, Any]]:
    return load_products_from_path(CATALOG_PATH)


_image_assets = ImageAssetCache(BASE_DIR / "static")


def _image_selection(filename: str, *, hero: bool = False):
    if not hasattr(g, "image_asset_snapshot"):
        g.image_asset_snapshot = _image_assets.snapshot()
        g.image_asset_selections = {}
        g.image_static_base = url_for("static", filename="")
    key = filename, hero
    if key not in g.image_asset_selections:
        g.image_asset_selections[key] = _image_assets.get(filename, g.image_asset_snapshot, hero=hero)
    return g.image_asset_selections[key]


@lru_cache(maxsize=4096)
def _image_url(filename: str, version: str | None, static_base: str) -> str:
    # static_base partitions the cache by the current mount prefix/static host.
    # Let Flask escape URLs; do not concatenate filenames or cache customer HTML.
    return url_for("static", filename=filename, **({"v": version} if version else {}))


@lru_cache(maxsize=1024)
def _image_srcset(candidates: tuple, static_base: str) -> str:
    return ", ".join(f"{_image_url(path, version, static_base)} {width}w"
                     for path, width, version in candidates)


def hero_image_url(filename: str) -> str:
    image = _image_selection(filename, hero=True)
    return _image_url(image.path, image.version, g.image_static_base)


def optimized_image_url(filename: str) -> str:
    image = _image_selection(filename)
    return _image_url(image.path, image.version, g.image_static_base)


def product_image_attributes(filename: str, usage: str = "catalog") -> dict[str, str]:
    image = _image_selection(filename)
    if not image.candidates:
        return {}
    return {"srcset": _image_srcset(image.candidates, g.image_static_base),
            "sizes": PRODUCT_IMAGE_SIZES[usage]}


def load_social() -> dict[str, Any]:
    return load_social_from_path(SOCIAL_PATH)


def load_team() -> dict[str, Any]:
    return load_team_from_path(TEAM_PATH)


def load_faqs() -> list[dict[str, Any]]:
    return load_faqs_from_path(FAQS_PATH)


def load_collections_cfg() -> dict[str, Any]:
    return load_collections_cfg_from_path(COLLECTIONS_PATH)


def load_trade_show() -> dict[str, Any]:
    return load_trade_show_from_path(TRADE_SHOWS_PATH, load_products(), BASE_DIR / "static")


def load_connect_event() -> dict[str, str]:
    return load_connect_event_from_path(TRADE_SHOWS_PATH)


def warm_runtime_caches() -> None:
    # Warm catalog and search caches once per process so initial customer
    # requests avoid cold-path indexing work.
    try:
        products = load_products()
        # Build image metadata and relative URLs before Gunicorn accepts traffic.
        # No session/cart access or database queries occur in this context.
        with app.test_request_context("/"):
            for product in products:
                filename = "product_images/" + product["image"]
                optimized_image_url(filename)
                product_image_attributes(filename)
            for filename in ("assets/hero_bg.png", "assets/hero_bg_mobile_compact.png", "assets/hero_bg_wide.png"):
                hero_image_url(filename)
    except Exception:
        # Do not fail app startup if warmup misses; normal request path will recover.
        pass


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
        trade_shows_path=TRADE_SHOWS_PATH,
    )


@app.context_processor
def inject_site_config():
    # Public metadata endpoints do not render cart state. Avoid opening the
    # customer session so their responses remain cookie-free and edge-cacheable.
    cart = {} if request.endpoint in PUBLIC_ENDPOINT_POLICIES else get_cart()
    return {
        "asset_url": asset_url,
        "optimized_image_url": optimized_image_url,
        "hero_image_url": hero_image_url,
        "product_image_attributes": product_image_attributes,
        "cart_distinct_item_count": len(cart),
        "cart_item_count": cart_total_items(cart),
        "current_year": date.today().year,
        "cloudflare_web_analytics_token": os.getenv("CLOUDFLARE_WEB_ANALYTICS_TOKEN", "30e9fc0a5f4f49379c768839796e2af1").strip(),
        "site_base_url": os.getenv("SITE_BASE_URL", "").strip(),
        "social": load_social(),
        "site_name": "California Earrings",
    }

register_site_routes(
    app,
    base_dir=BASE_DIR,
    get_reels_path=get_reels_path,
    get_trade_shows_path=lambda: TRADE_SHOWS_PATH,
    load_products=load_products,
    load_collections_cfg=load_collections_cfg,
    load_team=load_team,
    load_faqs=load_faqs,
    load_trade_show=load_trade_show,
    load_connect_event=load_connect_event,
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

install_rate_limiting(app)
warm_runtime_caches()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
