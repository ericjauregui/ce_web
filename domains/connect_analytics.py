"""Aggregate QR landing-page activity without visitor identifiers."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Date, DateTime, Integer, MetaData, PrimaryKeyConstraint,
    String, Table, text,
)
from sqlalchemy.engine import Engine

from domains.orders import create_database_engine, database_url_from_env


CONNECT_ACTIONS = frozenset({
    "visit", "whatsapp", "save_contact", "instagram", "tiktok", "shop",
})

metadata = MetaData()
connect_event_counts = Table(
    "connect_event_counts",
    metadata,
    Column("event_date", Date, nullable=False),
    Column("trade_show_key", String(80), nullable=False),
    Column("trade_show_name", String(160), nullable=False),
    Column("booth", String(80), nullable=False),
    Column("action", String(24), nullable=False),
    Column("count", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("event_date", "trade_show_key", "booth", "action"),
)


class ConnectAnalytics:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_database_engine(database_url_from_env())

    def create_schema_for_tests(self) -> None:
        if self.engine.dialect.name != "sqlite":
            raise RuntimeError("Test schema creation requires an explicit SQLite engine.")
        metadata.create_all(self.engine)

    def record(self, *, action: str, event: dict[str, str]) -> None:
        if action not in CONNECT_ACTIONS:
            raise ValueError("Unknown connect action")
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO connect_event_counts
                        (event_date, trade_show_key, trade_show_name, booth, action, count, updated_at)
                    VALUES
                        (:event_date, :trade_show_key, :trade_show_name, :booth, :action, 1, :updated_at)
                    ON CONFLICT (event_date, trade_show_key, booth, action)
                    DO UPDATE SET count = connect_event_counts.count + 1, updated_at = excluded.updated_at
                """),
                {
                    "event_date": now.date(),
                    "trade_show_key": event.get("key", ""),
                    "trade_show_name": event.get("name", ""),
                    "booth": event.get("booth", ""),
                    "action": action,
                    "updated_at": now,
                },
            )
