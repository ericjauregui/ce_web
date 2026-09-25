"""Store pseudonymous, browser-session site journeys."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone

from flask import Flask, Response, g, request
from sqlalchemy import (
    CheckConstraint, Column, DateTime, Index, Integer, MetaData, String, Table,
)
from sqlalchemy.engine import Engine

from domains.orders import create_database_engine, database_url_from_env


ANALYTICS_SESSION_COOKIE = "ce_analytics_session"
_SESSION_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_SAFE_PATH_PATTERN = re.compile(r"/[A-Za-z0-9._~/-]*\Z")
_SAFE_CONTEXT_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\Z")
_SAFE_BUTTON_PATTERN = re.compile(r"button:[A-Za-z0-9_-]{1,80}\Z")
_SAFE_CAMPAIGN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}\Z")
_SAFE_HOST_PATTERN = re.compile(r"[A-Za-z0-9.-]{1,253}\Z")

EVENT_TYPES = frozenset({"page_view", "click"})
CLICK_TARGETS = frozenset({
    "button", "external:other", "external:whatsapp", "external:instagram",
    "external:tiktok", "external:facebook", "external:youtube",
    "external:maps", "contact:email", "contact:phone",
})

metadata = MetaData()
site_analytics_events = Table(
    "site_analytics_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("session_id_hash", String(64), nullable=False),
    Column("event_type", String(24), nullable=False),
    Column("page_path", String(255), nullable=False),
    Column("page_context", String(80), nullable=True),
    Column("click_target", String(264), nullable=True),
    Column("referrer_host", String(253), nullable=True),
    Column("utm_source", String(80), nullable=True),
    Column("utm_medium", String(80), nullable=True),
    Column("utm_campaign", String(80), nullable=True),
    CheckConstraint(
        "event_type IN ('page_view', 'click')",
        name="ck_site_analytics_events_type",
    ),
    CheckConstraint(
        "(event_type = 'page_view' AND click_target IS NULL) OR "
        "(event_type = 'click' AND click_target IS NOT NULL)",
        name="ck_site_analytics_events_click_target",
    ),
)
Index(
    "ix_site_analytics_events_session_id",
    site_analytics_events.c.session_id_hash,
    site_analytics_events.c.id,
)
Index("ix_site_analytics_events_occurred_at", site_analytics_events.c.occurred_at)


def session_id_digest(token: object) -> str | None:
    """Return a one-way digest for a valid random analytics session token."""
    if not isinstance(token, str) or not _SESSION_TOKEN_PATTERN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def normalize_page_path(value: object) -> str | None:
    """Accept only a safe URL path; reject query strings, fragments, and unusual data."""
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 1024:
        return None

    from urllib.parse import unquote

    path = unquote(value)
    if len(path) > 255 or not _SAFE_PATH_PATTERN.fullmatch(path) or "//" in path:
        return None
    if any(segment in {".", ".."} for segment in path.split("/")):
        return None
    return path


def normalize_page_context(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _SAFE_CONTEXT_PATTERN.fullmatch(value):
        return None
    return value


def normalize_campaign_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split())
    if not normalized or not _SAFE_CAMPAIGN_PATTERN.fullmatch(normalized):
        return None
    if normalized.isdigit() and len(normalized) >= 7:
        return None
    return normalized


def normalize_referrer_host(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    host = value.strip().lower().rstrip(".")
    if not _SAFE_HOST_PATTERN.fullmatch(host):
        return None
    labels = host.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        for label in labels
    ):
        return None
    return host


def normalize_click_target(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if value in CLICK_TARGETS or _SAFE_BUTTON_PATTERN.fullmatch(value):
        return value
    if value.startswith("internal:"):
        path = normalize_page_path(value[len("internal:"):])
        return f"internal:{path}" if path else None
    return None


class SiteAnalytics:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_database_engine(database_url_from_env())

    def create_schema_for_tests(self) -> None:
        if self.engine.dialect.name != "sqlite":
            raise RuntimeError("Test schema creation requires an explicit SQLite engine.")
        metadata.create_all(self.engine)

    def record(
        self,
        *,
        session_hash: str,
        event_type: str,
        page_path: str,
        page_context: str | None = None,
        click_target: str | None = None,
        referrer_host: str | None = None,
        utm_source: str | None = None,
        utm_medium: str | None = None,
        utm_campaign: str | None = None,
    ) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", session_hash):
            raise ValueError("Invalid analytics session hash")
        if event_type not in EVENT_TYPES:
            raise ValueError("Unknown site analytics event")

        safe_path = normalize_page_path(page_path)
        safe_context = normalize_page_context(page_context)
        safe_target = normalize_click_target(click_target) if click_target is not None else None
        safe_referrer = normalize_referrer_host(referrer_host)
        safe_utm_source = normalize_campaign_value(utm_source)
        safe_utm_medium = normalize_campaign_value(utm_medium)
        safe_utm_campaign = normalize_campaign_value(utm_campaign)
        if not safe_path or (page_context is not None and page_context != "" and not safe_context):
            raise ValueError("Invalid analytics page")
        if event_type == "page_view" and safe_target is not None:
            raise ValueError("Page views cannot have a click target")
        if event_type == "click" and safe_target is None:
            raise ValueError("Clicks require a valid target")
        if event_type == "click" and any((
            safe_referrer, safe_utm_source, safe_utm_medium, safe_utm_campaign,
        )):
            raise ValueError("Attribution fields belong on page views")

        with self.engine.begin() as connection:
            connection.execute(
                site_analytics_events.insert().values(
                    occurred_at=datetime.now(timezone.utc),
                    session_id_hash=session_hash,
                    event_type=event_type,
                    page_path=safe_path,
                    page_context=safe_context,
                    click_target=safe_target,
                    referrer_host=safe_referrer,
                    utm_source=safe_utm_source,
                    utm_medium=safe_utm_medium,
                    utm_campaign=safe_utm_campaign,
                )
            )


def install_analytics_session_cookie(app: Flask) -> None:
    """Issue a separate HttpOnly cookie that expires with the browser session."""

    @app.before_request
    def prepare_analytics_session_cookie() -> None:
        if request.method != "GET" or request.endpoint == "static":
            return

        existing = request.cookies.get(ANALYTICS_SESSION_COOKIE)
        if session_id_digest(existing):
            return
        g.new_analytics_session_cookie = secrets.token_urlsafe(32)

    @app.after_request
    def set_analytics_session_cookie(response: Response) -> Response:
        token = getattr(g, "new_analytics_session_cookie", None)
        if token and response.status_code < 400 and response.mimetype == "text/html":
            response.set_cookie(
                ANALYTICS_SESSION_COOKIE,
                token,
                httponly=True,
                secure=bool(app.config.get("SESSION_COOKIE_SECURE", False)),
                samesite="Lax",
                path="/",
            )
        return response
