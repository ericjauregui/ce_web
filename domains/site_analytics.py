"""Store pseudonymous, browser-session site journeys."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, g, request
from sqlalchemy import (
    CheckConstraint, Column, DateTime, Index, Integer, MetaData, String,
    Table, case, func, inspect, select,
)
from sqlalchemy.engine import Engine

from domains.connect_analytics import connect_event_counts
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

    def dashboard_summary(
        self,
        *,
        days: int = 30,
        selected_session: str | None = None,
    ) -> dict[str, object]:
        """Return bounded, aggregated data for the private analytics dashboard."""
        if days not in {7, 30, 90}:
            days = 30

        now = datetime.now(timezone.utc)
        first_day = now.date() - timedelta(days=days - 1)
        since = datetime.combine(first_day, datetime.min.time(), tzinfo=timezone.utc)
        events = site_analytics_events
        is_page_view = events.c.event_type == "page_view"
        is_click = events.c.event_type == "click"

        with self.engine.connect() as connection:
            page_views = connection.execute(
                select(func.count()).select_from(events).where(
                    events.c.occurred_at >= since, is_page_view
                )
            ).scalar_one()
            clicks = connection.execute(
                select(func.count()).select_from(events).where(
                    events.c.occurred_at >= since, is_click
                )
            ).scalar_one()
            sessions = connection.execute(
                select(func.count(func.distinct(events.c.session_id_hash))).where(
                    events.c.occurred_at >= since
                )
            ).scalar_one()

            date_bucket = (
                func.date_trunc("day", events.c.occurred_at)
                if self.engine.dialect.name == "postgresql"
                else func.date(events.c.occurred_at)
            )
            daily_rows = connection.execute(
                select(
                    date_bucket.label("event_day"),
                    func.sum(case((is_page_view, 1), else_=0)).label("page_views"),
                    func.sum(case((is_click, 1), else_=0)).label("clicks"),
                    func.count(func.distinct(events.c.session_id_hash)).label("sessions"),
                )
                .where(events.c.occurred_at >= since)
                .group_by("event_day")
                .order_by("event_day")
            ).all()

            page_rows = connection.execute(
                select(events.c.page_path, func.count().label("count"))
                .where(events.c.occurred_at >= since, is_page_view)
                .group_by(events.c.page_path)
                .order_by(func.count().desc(), events.c.page_path)
                .limit(10)
            ).all()
            click_rows = connection.execute(
                select(events.c.click_target, func.count().label("count"))
                .where(events.c.occurred_at >= since, is_click)
                .group_by(events.c.click_target)
                .order_by(func.count().desc(), events.c.click_target)
                .limit(10)
            ).all()
            referrer_rows = connection.execute(
                select(
                    events.c.referrer_host,
                    func.count(func.distinct(events.c.session_id_hash)).label("sessions"),
                )
                .where(
                    events.c.occurred_at >= since,
                    is_page_view,
                    events.c.referrer_host.is_not(None),
                )
                .group_by(events.c.referrer_host)
                .order_by(func.count(func.distinct(events.c.session_id_hash)).desc(), events.c.referrer_host)
                .limit(10)
            ).all()
            campaign_rows = connection.execute(
                select(
                    events.c.utm_source,
                    events.c.utm_medium,
                    events.c.utm_campaign,
                    func.count(func.distinct(events.c.session_id_hash)).label("sessions"),
                )
                .where(
                    events.c.occurred_at >= since,
                    is_page_view,
                    (events.c.utm_source.is_not(None))
                    | (events.c.utm_medium.is_not(None))
                    | (events.c.utm_campaign.is_not(None)),
                )
                .group_by(events.c.utm_source, events.c.utm_medium, events.c.utm_campaign)
                .order_by(func.count(func.distinct(events.c.session_id_hash)).desc())
                .limit(10)
            ).all()
            context_rows = connection.execute(
                select(
                    events.c.page_context,
                    func.sum(case((is_page_view, 1), else_=0)).label("page_views"),
                    func.sum(case((is_click, 1), else_=0)).label("clicks"),
                )
                .where(
                    events.c.occurred_at >= since,
                    events.c.page_context.is_not(None),
                )
                .group_by(events.c.page_context)
                .order_by(func.sum(case((is_page_view, 1), else_=0)).desc())
                .limit(10)
            ).all()
            connect_rows = []
            if inspect(connection).has_table(connect_event_counts.name):
                connect_rows = connection.execute(
                    select(
                        connect_event_counts.c.trade_show_key,
                        connect_event_counts.c.trade_show_name,
                        connect_event_counts.c.booth,
                        connect_event_counts.c.action,
                        func.sum(connect_event_counts.c.count).label("count"),
                    )
                    .where(
                        connect_event_counts.c.event_date >= first_day,
                        connect_event_counts.c.event_date <= now.date(),
                    )
                    .group_by(
                        connect_event_counts.c.trade_show_key,
                        connect_event_counts.c.trade_show_name,
                        connect_event_counts.c.booth,
                        connect_event_counts.c.action,
                    )
                    .order_by(func.sum(connect_event_counts.c.count).desc())
                    .limit(20)
                ).all()
            session_rows = connection.execute(
                select(
                    events.c.session_id_hash,
                    func.max(events.c.occurred_at).label("last_seen"),
                    func.sum(case((is_page_view, 1), else_=0)).label("page_views"),
                    func.sum(case((is_click, 1), else_=0)).label("clicks"),
                )
                .where(events.c.occurred_at >= since)
                .group_by(events.c.session_id_hash)
                .order_by(func.max(events.c.occurred_at).desc())
                .limit(12)
            ).all()

            journey = []
            if selected_session and re.fullmatch(r"[0-9a-f]{64}", selected_session):
                journey = [
                    {
                        "occurred_at": row.occurred_at,
                        "event_type": row.event_type,
                        "page_path": row.page_path,
                        "page_context": row.page_context,
                        "click_target": row.click_target,
                    }
                    for row in connection.execute(
                        select(
                            events.c.occurred_at,
                            events.c.event_type,
                            events.c.page_path,
                            events.c.page_context,
                            events.c.click_target,
                        )
                        .where(
                            events.c.session_id_hash == selected_session,
                            events.c.occurred_at >= since,
                        )
                        .order_by(events.c.occurred_at, events.c.id)
                        .limit(250)
                    ).all()
                ]

        daily_lookup = {
            str(row.event_day)[:10]: {
                "page_views": int(row.page_views or 0),
                "clicks": int(row.clicks or 0),
                "sessions": int(row.sessions or 0),
            }
            for row in daily_rows
        }
        daily = []
        for offset in range(days):
            date_value = first_day + timedelta(days=offset)
            counts = daily_lookup.get(date_value.isoformat(), {})
            daily.append({
                "label": date_value.strftime("%b %d"),
                "page_views": counts.get("page_views", 0),
                "clicks": counts.get("clicks", 0),
                "sessions": counts.get("sessions", 0),
            })

        return {
            "days": days,
            "page_views": int(page_views),
            "clicks": int(clicks),
            "sessions": int(sessions),
            "pages_per_session": round(page_views / sessions, 1) if sessions else 0,
            "daily": daily,
            "daily_peak": max(
                (max(row["page_views"], row["clicks"]) for row in daily),
                default=1,
            ) or 1,
            "top_pages": [{"path": row.page_path, "count": int(row.count)} for row in page_rows],
            "top_clicks": [{"target": row.click_target, "count": int(row.count)} for row in click_rows],
            "referrers": [
                {"host": row.referrer_host, "sessions": int(row.sessions)} for row in referrer_rows
            ],
            "campaigns": [
                {
                    "source": row.utm_source,
                    "medium": row.utm_medium,
                    "campaign": row.utm_campaign,
                    "sessions": int(row.sessions),
                }
                for row in campaign_rows
            ],
            "contexts": [
                {
                    "name": row.page_context,
                    "page_views": int(row.page_views or 0),
                    "clicks": int(row.clicks or 0),
                }
                for row in context_rows
            ],
            "connect_actions": [
                {
                    "key": row.trade_show_key,
                    "show": row.trade_show_name,
                    "booth": row.booth,
                    "action": row.action,
                    "count": int(row.count or 0),
                }
                for row in connect_rows
            ],
            "recent_sessions": [
                {
                    "hash": row.session_id_hash,
                    "short_id": row.session_id_hash[-8:],
                    "last_seen": row.last_seen,
                    "page_views": int(row.page_views or 0),
                    "clicks": int(row.clicks or 0),
                }
                for row in session_rows
            ],
            "selected_session": selected_session if journey else None,
            "selected_session_short": selected_session[-8:] if journey and selected_session else None,
            "journey": journey,
        }


def install_analytics_session_cookie(app: Flask) -> None:
    """Issue a separate HttpOnly cookie that expires with the browser session."""

    @app.before_request
    def prepare_analytics_session_cookie() -> None:
        if request.method != "GET" or request.endpoint in {"static", "site_analytics_dashboard"}:
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
