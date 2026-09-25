"""Store pseudonymous site page-view and click journeys.

Revision ID: 20260925_0004
Revises: 20260924_0003
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260925_0004"
down_revision: str | None = "20260924_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_analytics_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id_hash", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("page_path", sa.String(length=255), nullable=False),
        sa.Column("page_context", sa.String(length=80), nullable=True),
        sa.Column("click_target", sa.String(length=264), nullable=True),
        sa.Column("referrer_host", sa.String(length=253), nullable=True),
        sa.Column("utm_source", sa.String(length=80), nullable=True),
        sa.Column("utm_medium", sa.String(length=80), nullable=True),
        sa.Column("utm_campaign", sa.String(length=80), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('page_view', 'click')",
            name="ck_site_analytics_events_type",
        ),
        sa.CheckConstraint(
            "(event_type = 'page_view' AND click_target IS NULL) OR "
            "(event_type = 'click' AND click_target IS NOT NULL)",
            name="ck_site_analytics_events_click_target",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_site_analytics_events_session_id",
        "site_analytics_events",
        ["session_id_hash", "id"],
        unique=False,
    )
    op.create_index(
        "ix_site_analytics_events_occurred_at",
        "site_analytics_events",
        ["occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_site_analytics_events_occurred_at", table_name="site_analytics_events")
    op.drop_index("ix_site_analytics_events_session_id", table_name="site_analytics_events")
    op.drop_table("site_analytics_events")
