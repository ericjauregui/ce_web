from __future__ import annotations

import io
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from sqlalchemy.exc import SQLAlchemyError

from domains.catalog import build_sections, find_product_by_code
from domains.connect import (
    build_connect_vcard, connect_event_by_key, connect_whatsapp_url,
)
from domains.connect_analytics import CONNECT_ACTIONS, ConnectAnalytics
from domains.file_cache import load_json_cached
from domains.homepage import build_homepage_context, load_latest_reels
from domains.reels import load_random_reels
from domains.orders import DatabaseConfigurationError
from domains.team import build_member_vcard, build_team_members, ensure_team_qr_assets

LoadProducts = Callable[[], list[dict[str, Any]]]
LoadCollectionsCfg = Callable[[], dict[str, Any]]
LoadTeam = Callable[[], dict[str, Any]]
LoadFaqs = Callable[[], list[dict[str, Any]]]
LoadTradeShow = Callable[[], dict[str, Any]]
LoadConnectEvent = Callable[[], dict[str, str]]
GetCart = Callable[[], dict[str, int]]
GetTeamMemberBySlug = Callable[[str], tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]]
BuildSitemapUrls = Callable[[str], list[dict[str, str | float | None]]]
CanonicalBaseUrl = Callable[[], str]
Slugify = Callable[[str], str]
GetReelsPath = Callable[[], Path]
GetTradeShowsPath = Callable[[], Path]


def register_site_routes(
    app: Flask,
    *,
    base_dir: Path,
    get_reels_path: GetReelsPath,
    get_trade_shows_path: GetTradeShowsPath,
    load_products: LoadProducts,
    load_collections_cfg: LoadCollectionsCfg,
    load_team: LoadTeam,
    load_faqs: LoadFaqs,
    load_trade_show: LoadTradeShow,
    load_connect_event: LoadConnectEvent,
    get_cart: GetCart,
    get_team_member_by_slug: GetTeamMemberBySlug,
    build_sitemap_urls: BuildSitemapUrls,
    canonical_base_url: CanonicalBaseUrl,
    slugify: Slugify,
) -> None:
    connect_analytics_lock = Lock()

    @app.route("/privacy")
    def privacy_policy():
        return render_template("privacy.html")

    @app.route("/")
    def index():
        products = load_products()
        q = request.args.get("q", "")
        cfg = load_collections_cfg()
        context = build_homepage_context(products, q, cfg, get_reels_path(), get_cart())
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
        collection_label = labels.get(collection_key, collection_key.replace("-", " ").title())

        return render_template(
            "product_detail.html",
            product=product,
            initial_qty=initial_qty,
            collection_label=collection_label,
        )

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
        qr_assets = ensure_team_qr_assets(team, base_dir / "catalog" / "team.json", base_dir / "static")
        member["qr_asset"] = qr_assets[member_slug]
        return render_template("team_member.html", team=team, member=member)

    @app.route("/team/<member_slug>/contact-qr.svg")
    def team_member_vcard_qr(member_slug: str):
        team, _, member = get_team_member_by_slug(member_slug)
        if not member:
            abort(404)
        qr_assets = ensure_team_qr_assets(team, base_dir / "catalog" / "team.json", base_dir / "static")
        # Preserve old links while serving the cacheable static asset.
        return redirect(url_for("static", filename=qr_assets[member_slug]), code=302)

    @app.route("/team/<member_slug>/contact.vcf")
    def team_member_vcard(member_slug: str):
        team, _, member = get_team_member_by_slug(member_slug)
        if not member:
            abort(404)

        photo_bytes, photo_type = _member_photo(member)
        vcard_text = build_member_vcard(member, team, photo_bytes=photo_bytes, photo_type=photo_type)
        filename = f"{slugify(member.get('name', 'contact'))}.vcf"
        return send_file(
            io.BytesIO(vcard_text.encode("utf-8")),
            mimetype="text/vcard; charset=utf-8",
            as_attachment=True,
            download_name=filename,
        )

    def _member_photo(member: dict[str, Any]) -> tuple[bytes | None, str | None]:
        photo_bytes = None
        photo_type = None
        photo_name = str(member.get("photo") or "").strip()
        if photo_name:
            photo_path = base_dir / "static" / "team" / photo_name
            if photo_path.exists() and photo_path.is_file():
                photo_type = {
                    ".jpg": "JPEG",
                    ".jpeg": "JPEG",
                    ".png": "PNG",
                    ".gif": "GIF",
                }.get(photo_path.suffix.lower())
                if photo_type:
                    photo_bytes = photo_path.read_bytes()
        return photo_bytes, photo_type

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/connect")
    def connect_page():
        event = load_connect_event()
        _, _, giancarlo = get_team_member_by_slug("giancarlo")
        if not giancarlo:
            abort(404)
        return render_template(
            "connect.html",
            event=event,
            whatsapp_url=connect_whatsapp_url(event, giancarlo["phone_digits"]),
        )

    @app.route("/connect/contact.vcf")
    def connect_vcard():
        event = load_connect_event()
        team, _, giancarlo = get_team_member_by_slug("giancarlo")
        if not giancarlo:
            abort(404)
        photo_bytes, photo_type = _member_photo(giancarlo)
        social = load_json_cached(base_dir / "catalog" / "social.json", {})
        vcard = build_connect_vcard(
            giancarlo, team, social, event, photo_bytes=photo_bytes, photo_type=photo_type
        )
        return send_file(
            io.BytesIO(vcard.encode("utf-8")),
            mimetype="text/vcard; charset=utf-8",
            as_attachment=True,
            download_name="california-earrings.vcf",
        )

    @app.post("/api/connect/event")
    def connect_event():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return "", 400
        action = payload.get("action")
        key = payload.get("trade_show_key")
        if not isinstance(action, str) or action not in CONNECT_ACTIONS or not isinstance(key, str):
            return "", 400
        event = connect_event_by_key(get_trade_shows_path(), key)
        if event is None:
            return "", 400

        try:
            with connect_analytics_lock:
                analytics = app.extensions.get("connect_analytics")
                if analytics is None:
                    analytics = ConnectAnalytics()
                    app.extensions["connect_analytics"] = analytics
            analytics.record(action=action, event=event)
        except (DatabaseConfigurationError, SQLAlchemyError):
            app.logger.warning("Connect analytics could not be saved")
            return "", 503
        return "", 204

    @app.route("/trade-shows")
    def trade_shows_page():
        trade_show = load_trade_show()
        if not trade_show:
            abort(404)
        return render_template("trade_shows.html", show=trade_show, latest_reels=load_latest_reels(get_reels_path()))

    @app.route("/faq")
    def faq_redirect():
        return redirect(url_for("faqs_page"), code=301)

    @app.route("/faqs")
    def faqs_page():
        return render_template("faqs.html", faq_items=load_faqs())

    @app.route("/reels")
    def reels_page():
        reels = load_random_reels(get_reels_path())
        return render_template("reels.html", reels=reels)

    @app.route("/favicon.ico")
    def favicon():
        return send_file(
            base_dir / "static" / "favicon.ico",
            mimetype="image/x-icon",
            max_age=60 * 60 * 24 * 30,
        )

    @app.route("/robots.txt")
    def robots():
        base = canonical_base_url()
        return (
            render_template("robots.txt", sitemap_url=f"{base}/sitemap.xml"),
            200,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    @app.route("/sitemaps.xml")
    @app.route("/sitemap.xml")
    def sitemap():
        base_url = canonical_base_url()
        urls = build_sitemap_urls(base_url)
        return (
            render_template("sitemap.xml", urls=urls),
            200,
            {"Content-Type": "application/xml"},
        )

    @app.errorhandler(404)
    def not_found(_):
        return render_template("404.html"), 404
