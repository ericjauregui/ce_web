"""Store pseudonymous, browser-session site journeys."""
from __future__ import annotations

import hashlib
import math
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Flask, Response, g, request
from sqlalchemy import (
    CheckConstraint, Column, DateTime, Index, Integer, MetaData, String,
    Table, and_, case, func, inspect, literal, or_, select,
)
from sqlalchemy.engine import Engine

from domains.connect_analytics import connect_event_counts
from domains.orders import create_database_engine, database_url_from_env


ANALYTICS_SESSION_COOKIE = "ce_analytics_session"
_SESSION_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_SAFE_PATH_PATTERN = re.compile(r"/[A-Za-z0-9._~/-]*\Z")
_SAFE_CONTEXT_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\Z")
_SAFE_BUTTON_PATTERN = re.compile(r"button:[A-Za-z0-9_-]{1,80}\Z")
_SAFE_SEMANTIC_TARGET_PATTERN = re.compile(
    r"(?:action|component):[a-z0-9]+(?:-[a-z0-9]+){0,19}\Z"
)
_SAFE_CAMPAIGN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}\Z")
_SAFE_HOST_PATTERN = re.compile(r"[A-Za-z0-9.-]{1,253}\Z")

EVENT_TYPES = frozenset({"page_view", "click"})
CLICK_TARGETS = frozenset({
    "button", "external:other", "external:whatsapp", "external:instagram",
    "external:tiktok", "external:facebook", "external:youtube",
    "external:maps", "contact:email", "contact:phone",
})
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
GRANULARITIES = frozenset({"day", "week", "month"})
PERIOD_UNITS = frozenset({"days", "weeks", "months"})
MAX_CUSTOM_RANGE_DAYS = 1825


def _shift_months(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)


def _format_date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def resolve_dashboard_range(query_args, *, today: date | None = None) -> dict[str, object]:
    """Resolve complete Pacific-time periods or an inclusive custom date range."""
    today = today or datetime.now(PACIFIC_TIME).date()
    latest_complete_date = today - timedelta(days=1)
    mode = query_args.get("range", "rolling")
    unit = query_args.get("unit", "days")
    if unit not in PERIOD_UNITS:
        unit = "days"

    legacy_days = query_args.get("days")
    if "range" not in query_args and legacy_days in {"7", "30", "90"}:
        mode = "rolling"
        unit = "days"
        count_value = legacy_days
    else:
        count_value = query_args.get("count", "30")

    max_count = {"days": 365, "weeks": 104, "months": 60}[unit]
    try:
        count = int(count_value)
    except (TypeError, ValueError):
        count = 30 if unit == "days" else 4
    count = min(max(count, 1), max_count)

    if mode == "previous_month":
        end_exclusive = date(today.year, today.month, 1)
        start_date = _shift_months(end_exclusive, -1)
        description = "Previous calendar month"
    elif mode == "custom":
        try:
            start_date = date.fromisoformat(query_args.get("date_from", ""))
            end_date = date.fromisoformat(query_args.get("date_to", ""))
        except (TypeError, ValueError):
            start_date = latest_complete_date - timedelta(days=29)
            end_date = latest_complete_date
        end_date = min(end_date, latest_complete_date)
        if start_date > end_date:
            start_date = end_date - timedelta(days=29)
        if (end_date - start_date).days + 1 > MAX_CUSTOM_RANGE_DAYS:
            start_date = end_date - timedelta(days=MAX_CUSTOM_RANGE_DAYS - 1)
        end_exclusive = end_date + timedelta(days=1)
        description = "Custom date range"
    else:
        mode = "rolling"
        if unit == "days":
            end_exclusive = today
            start_date = end_exclusive - timedelta(days=count)
            unit_label = "day"
        elif unit == "weeks":
            end_exclusive = today - timedelta(days=today.weekday())
            start_date = end_exclusive - timedelta(weeks=count)
            unit_label = "week"
        else:
            end_exclusive = date(today.year, today.month, 1)
            start_date = _shift_months(end_exclusive, -count)
            unit_label = "month"
        description = f"Last {count} complete {unit_label}{'' if count == 1 else 's'}"

    end_date = end_exclusive - timedelta(days=1)
    return {
        "mode": mode,
        "unit": unit,
        "count": count,
        "max_count": max_count,
        "start_date": start_date,
        "end_date": end_date,
        "end_exclusive": end_exclusive,
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "latest_complete_date": latest_complete_date.isoformat(),
        "range_days": (end_exclusive - start_date).days,
        "range_description": description,
        "range_label": f"{_format_date(start_date)} – {_format_date(end_date)}",
    }


def _bucket_start(value: date, granularity: str) -> date:
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    if granularity == "month":
        return date(value.year, value.month, 1)
    return value


def _next_bucket(value: date, granularity: str) -> date:
    if granularity == "week":
        return value + timedelta(days=7)
    if granularity == "month":
        return _shift_months(value, 1)
    return value + timedelta(days=1)


def _pacific_bucket(value: datetime, granularity: str) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return _bucket_start(value.astimezone(PACIFIC_TIME).date(), granularity)

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
    if (
        value in CLICK_TARGETS
        or _SAFE_BUTTON_PATTERN.fullmatch(value)
        or _SAFE_SEMANTIC_TARGET_PATTERN.fullmatch(value)
    ):
        return value
    if value.startswith("internal:"):
        path = normalize_page_path(value[len("internal:"):])
        return f"internal:{path}" if path else None
    return None


def _page_filter_clause(events, page_filter: str):
    if page_filter == "home":
        return events.c.page_path == "/"
    if page_filter == "cart":
        return or_(
            events.c.page_path.in_(("/cart", "/checkout")),
            events.c.click_target.in_((
                "internal:/cart",
                "internal:/checkout",
                "action:add-to-order",
                "action:add-to-cart",
                "action:open-cart",
            )),
        )
    if page_filter == "team":
        return or_(events.c.page_path == "/team", events.c.page_path.like("/team/%"))
    if page_filter == "trade-shows":
        return or_(
            events.c.page_path.in_(("/connect", "/trade-shows")),
            events.c.page_context.is_not(None),
        )
    if page_filter.startswith("path:"):
        path = normalize_page_path(page_filter[5:])
        return events.c.page_path == path if path else literal(False)
    return None


def _page_filter_label(page_filter: str) -> str:
    labels = {
        "all": "All pages",
        "home": "Homepage",
        "cart": "Cart and checkout",
        "team": "Team pages",
        "trade-shows": "Trade-show pages",
    }
    if page_filter.startswith("path:"):
        return page_filter[5:]
    return labels.get(page_filter, "All pages")


def _click_target_label(target: str) -> str:
    labels = {
        "button": "Unlabeled button (older event)",
        "external:other": "Other external link",
        "external:whatsapp": "WhatsApp",
        "external:instagram": "Instagram",
        "external:tiktok": "TikTok",
        "external:facebook": "Facebook",
        "external:youtube": "YouTube",
        "external:maps": "Maps",
        "contact:email": "Email link",
        "contact:phone": "Phone link",
        "internal:/cart": "Open cart",
        "internal:/checkout": "Open checkout",
        "action:add-to-order": "Add to order",
        "action:add-to-cart": "Add to cart",
        "action:open-cart": "Open cart",
        "component:product-card": "Product card",
    }
    if target in labels:
        return labels[target]
    for prefix, label in (("internal:", "Open"), ("action:", ""), ("component:", ""), ("button:", "Button")):
        if target.startswith(prefix):
            value = target[len(prefix):].replace("-", " ").replace("_", " ").strip()
            title = value.title()
            return f"{label} {title}".strip() if label else title
    return "Other click"


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

    def _journey_edges(
        self,
        connection,
        *,
        time_conditions: list,
        page_filter: str,
        journey_start: str,
    ) -> list[dict[str, object]]:
        events = site_analytics_events
        ordering = [events.c.occurred_at, events.c.id]
        sequence = select(
            events.c.session_id_hash,
            events.c.page_path,
            events.c.page_context,
            func.row_number().over(
                partition_by=events.c.session_id_hash,
                order_by=ordering,
            ).label("step"),
            func.lead(events.c.page_path).over(
                partition_by=events.c.session_id_hash,
                order_by=ordering,
            ).label("next_path"),
        ).where(*time_conditions, events.c.event_type == "page_view").cte("page_sequence")

        first_page_conditions = [sequence.c.step == 1]
        if journey_start == "filter":
            start_clause = _page_filter_clause(sequence, page_filter)
            if start_clause is not None:
                first_page_conditions.append(start_clause)
        elif journey_start.startswith("path:"):
            start_path = normalize_page_path(journey_start[5:])
            if start_path:
                first_page_conditions.append(sequence.c.page_path == start_path)
        starts = select(sequence.c.session_id_hash).where(*first_page_conditions).cte("journey_starts")

        target_path = case(
            (
                and_(sequence.c.step == 5, sequence.c.next_path.is_not(None)),
                literal("More pages"),
            ),
            (sequence.c.next_path.is_(None), literal("Exit")),
            else_=sequence.c.next_path,
        ).label("target_path")
        edge_counts = select(
            sequence.c.step,
            sequence.c.page_path.label("source_path"),
            target_path,
            func.count(func.distinct(sequence.c.session_id_hash)).label("sessions"),
        ).select_from(
            sequence.join(starts, sequence.c.session_id_hash == starts.c.session_id_hash)
        ).where(sequence.c.step <= 5).group_by(
            sequence.c.step,
            sequence.c.page_path,
            target_path,
        ).cte("journey_edge_counts")
        ranked_edges = select(
            edge_counts.c.step,
            edge_counts.c.source_path,
            edge_counts.c.target_path,
            edge_counts.c.sessions,
            func.row_number().over(
                partition_by=edge_counts.c.step,
                order_by=[
                    edge_counts.c.sessions.desc(),
                    edge_counts.c.source_path,
                    edge_counts.c.target_path,
                ],
            ).label("edge_rank"),
        ).cte("ranked_journey_edges")
        rows = connection.execute(
            select(
                ranked_edges.c.step,
                ranked_edges.c.source_path,
                ranked_edges.c.target_path,
                ranked_edges.c.sessions,
            )
            .where(ranked_edges.c.edge_rank <= 8)
            .order_by(ranked_edges.c.step, ranked_edges.c.edge_rank)
        ).all()
        return [
            {
                "step": int(row.step),
                "source": row.source_path,
                "target": row.target_path,
                "count": int(row.sessions or 0),
            }
            for row in rows
        ]

    def dashboard_summary(
        self,
        *,
        range_values: dict[str, object],
        granularity: str = "day",
        chart_metric: str = "both",
        page_filter: str = "all",
        journey_start: str = "filter",
    ) -> dict[str, object]:
        """Return aggregate analytics for the selected Pacific-time range and filters."""
        if granularity not in GRANULARITIES:
            granularity = "day"
        if chart_metric not in {"both", "page_views", "clicks"}:
            chart_metric = "both"

        start_date = range_values["start_date"]
        end_date = range_values["end_date"]
        end_exclusive = range_values["end_exclusive"]
        start_at = datetime.combine(start_date, time.min, tzinfo=PACIFIC_TIME).astimezone(timezone.utc)
        end_at = datetime.combine(end_exclusive, time.min, tzinfo=PACIFIC_TIME).astimezone(timezone.utc)
        events = site_analytics_events
        is_page_view = events.c.event_type == "page_view"
        is_click = events.c.event_type == "click"
        time_conditions = [events.c.occurred_at >= start_at, events.c.occurred_at < end_at]
        page_paths: list[str]

        with self.engine.connect() as connection:
            page_paths = [
                str(row.page_path)
                for row in connection.execute(
                    select(events.c.page_path.distinct())
                    .where(*time_conditions, is_page_view)
                    .order_by(events.c.page_path)
                ).all()
                if normalize_page_path(row.page_path)
            ]

            if page_filter not in {"all", "home", "cart", "team", "trade-shows"}:
                candidate_path = normalize_page_path(page_filter[5:]) if page_filter.startswith("path:") else None
                page_filter = f"path:{candidate_path}" if candidate_path in page_paths else "all"
            page_clause = _page_filter_clause(events, page_filter)
            scoped_conditions = [*time_conditions]
            if page_clause is not None:
                scoped_conditions.append(page_clause)

            if journey_start not in {"filter", "all"}:
                candidate_start = normalize_page_path(journey_start[5:]) if journey_start.startswith("path:") else None
                journey_start = f"path:{candidate_start}" if candidate_start in page_paths else "filter"

            page_views = connection.execute(
                select(func.count()).select_from(events).where(*scoped_conditions, is_page_view)
            ).scalar_one()
            clicks = connection.execute(
                select(func.count()).select_from(events).where(*scoped_conditions, is_click)
            ).scalar_one()
            sessions = connection.execute(
                select(func.count(func.distinct(events.c.session_id_hash)))
                .select_from(events)
                .where(*scoped_conditions)
            ).scalar_one()

            if self.engine.dialect.name == "postgresql":
                local_event_time = func.timezone("America/Los_Angeles", events.c.occurred_at)
                event_bucket = func.date_trunc(granularity, local_event_time)
                chart_rows = connection.execute(
                    select(
                        event_bucket.label("event_bucket"),
                        func.sum(case((is_page_view, 1), else_=0)).label("page_views"),
                        func.sum(case((is_click, 1), else_=0)).label("clicks"),
                        func.count(func.distinct(events.c.session_id_hash)).label("sessions"),
                    )
                    .where(*scoped_conditions)
                    .group_by(event_bucket)
                    .order_by(event_bucket)
                ).all()
                chart_lookup = {}
                for row in chart_rows:
                    bucket = row.event_bucket
                    bucket_date = bucket.date() if isinstance(bucket, datetime) else bucket
                    chart_lookup[bucket_date.isoformat()] = {
                        "page_views": int(row.page_views or 0),
                        "clicks": int(row.clicks or 0),
                        "sessions": int(row.sessions or 0),
                    }
            else:
                chart_rows = connection.execute(
                    select(events.c.occurred_at, events.c.event_type, events.c.session_id_hash)
                    .where(*scoped_conditions)
                ).all()
                chart_accumulator: dict[str, dict[str, object]] = {}
                for row in chart_rows:
                    bucket_date = _pacific_bucket(row.occurred_at, granularity)
                    bucket = chart_accumulator.setdefault(
                        bucket_date.isoformat(),
                        {"page_views": 0, "clicks": 0, "sessions": set()},
                    )
                    bucket["page_views" if row.event_type == "page_view" else "clicks"] += 1
                    bucket["sessions"].add(row.session_id_hash)
                chart_lookup = {
                    key: {
                        "page_views": int(bucket["page_views"]),
                        "clicks": int(bucket["clicks"]),
                        "sessions": len(bucket["sessions"]),
                    }
                    for key, bucket in chart_accumulator.items()
                }

            page_rows = connection.execute(
                select(events.c.page_path, func.count().label("count"))
                .where(*scoped_conditions, is_page_view)
                .group_by(events.c.page_path)
                .order_by(func.count().desc(), events.c.page_path)
                .limit(12)
            ).all()
            click_rows = connection.execute(
                select(events.c.click_target, func.count().label("count"))
                .where(*scoped_conditions, is_click)
                .group_by(events.c.click_target)
                .order_by(func.count().desc(), events.c.click_target)
                .limit(12)
            ).all()
            referrer_rows = connection.execute(
                select(
                    events.c.referrer_host,
                    func.count(func.distinct(events.c.session_id_hash)).label("sessions"),
                )
                .where(*scoped_conditions, is_page_view, events.c.referrer_host.is_not(None))
                .group_by(events.c.referrer_host)
                .order_by(
                    func.count(func.distinct(events.c.session_id_hash)).desc(),
                    events.c.referrer_host,
                )
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
                    *scoped_conditions,
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
                .where(*scoped_conditions, events.c.page_context.is_not(None))
                .group_by(events.c.page_context)
                .order_by(func.sum(case((is_page_view, 1), else_=0)).desc())
                .limit(10)
            ).all()

            connect_rows = []
            if (
                page_filter in {"all", "trade-shows", "path:/connect"}
                and inspect(connection).has_table(connect_event_counts.name)
            ):
                connect_rows = connection.execute(
                    select(
                        connect_event_counts.c.trade_show_key,
                        connect_event_counts.c.trade_show_name,
                        connect_event_counts.c.booth,
                        connect_event_counts.c.action,
                        func.sum(connect_event_counts.c.count).label("count"),
                    )
                    .where(
                        connect_event_counts.c.event_date >= start_date,
                        connect_event_counts.c.event_date <= end_date,
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

            journey_edges = self._journey_edges(
                connection,
                time_conditions=time_conditions,
                page_filter=page_filter,
                journey_start=journey_start,
            )

        last_day = end_exclusive - timedelta(days=1)
        bucket_date = _bucket_start(start_date, granularity)
        final_bucket = _bucket_start(last_day, granularity)
        chart = []
        while bucket_date <= final_bucket:
            counts = chart_lookup.get(bucket_date.isoformat(), {})
            page_count = counts.get("page_views", 0)
            click_count = counts.get("clicks", 0)
            if (
                (chart_metric == "both" and (page_count or click_count))
                or (chart_metric == "page_views" and page_count)
                or (chart_metric == "clicks" and click_count)
            ):
                chart.append({
                    "label": f"{bucket_date.month}/{bucket_date.day}",
                    "page_views": page_count,
                    "clicks": click_count,
                })
            bucket_date = _next_bucket(bucket_date, granularity)

        label_interval = max(1, math.ceil(len(chart) / 14))
        for index, bucket in enumerate(chart):
            bucket["show_label"] = (
                index == 0 or index == len(chart) - 1 or index % label_interval == 0
            )

        if chart_metric == "page_views":
            top_peak = max((row["page_views"] for row in chart), default=1) or 1
        elif chart_metric == "clicks":
            top_peak = max((row["clicks"] for row in chart), default=1) or 1
        else:
            top_peak = max(
                (max(row["page_views"], row["clicks"]) for row in chart),
                default=1,
            ) or 1
        page_filter_options = [
            {"value": "all", "label": "All pages"},
            {"value": "home", "label": "Homepage only"},
            {"value": "cart", "label": "Cart-related events"},
            {"value": "team", "label": "Team pages"},
            {"value": "trade-shows", "label": "Trade-show pages"},
            *({"value": f"path:{path}", "label": path} for path in page_paths),
        ]
        journey_start_options = [
            {"value": "filter", "label": f"Match page filter: {_page_filter_label(page_filter)}"},
            {"value": "all", "label": "Any entry page"},
            *({"value": f"path:{path}", "label": path} for path in page_paths),
        ]

        return {
            **range_values,
            "days": int(range_values["range_days"]),
            "page_views": int(page_views),
            "clicks": int(clicks),
            "sessions": int(sessions),
            "pages_per_session": round(page_views / sessions, 1) if sessions else 0,
            "chart": chart,
            "chart_peak": top_peak,
            "granularity": granularity,
            "granularity_label": {"day": "Daily", "week": "Weekly", "month": "Monthly"}[granularity],
            "chart_metric": chart_metric,
            "chart_metric_label": {
                "both": "Page views and clicks",
                "page_views": "Page views",
                "clicks": "Clicks",
            }[chart_metric],
            "page_filter": page_filter,
            "page_filter_label": _page_filter_label(page_filter),
            "page_filter_options": page_filter_options,
            "page_paths": page_paths,
            "journey_start": journey_start,
            "journey_start_options": journey_start_options,
            "journey_flow": journey_edges,
            "top_pages": [
                {"path": row.page_path, "count": int(row.count)} for row in page_rows
            ],
            "top_clicks": [
                {"target": _click_target_label(row.click_target), "count": int(row.count)}
                for row in click_rows
            ],
            "referrers": [
                {"host": row.referrer_host, "sessions": int(row.sessions)}
                for row in referrer_rows
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
