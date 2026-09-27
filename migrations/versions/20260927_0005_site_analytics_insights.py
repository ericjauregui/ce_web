"""Add aggregate request and checkout analytics.

Revision ID: 20260927_0005
Revises: 20260925_0004
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260927_0005"
down_revision: str | None = "20260925_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "site_analytics_events",
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "site_analytics_events",
        sa.Column("field_key", sa.String(length=40), nullable=True),
    )
    op.drop_constraint(
        "ck_site_analytics_events_type",
        "site_analytics_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_site_analytics_events_type",
        "site_analytics_events",
        "event_type IN ('page_view', 'click', 'page_duration', 'checkout_field')",
    )
    op.drop_constraint(
        "ck_site_analytics_events_click_target",
        "site_analytics_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_site_analytics_events_click_target",
        "site_analytics_events",
        "(event_type IN ('page_view', 'page_duration', 'checkout_field') AND click_target IS NULL) OR "
        "(event_type = 'click' AND click_target IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_site_analytics_events_duration",
        "site_analytics_events",
        "(event_type = 'page_duration' AND duration_seconds BETWEEN 1 AND 1800) OR "
        "(event_type <> 'page_duration' AND duration_seconds IS NULL)",
    )
    op.create_check_constraint(
        "ck_site_analytics_events_checkout_field",
        "site_analytics_events",
        "(event_type = 'checkout_field' AND field_key IN "
        "('name', 'company', 'phone', 'email', 'address_line_1', 'address_line_2', "
        "'city', 'state', 'postal_code', 'country')) OR "
        "(event_type <> 'checkout_field' AND field_key IS NULL)",
    )
    op.create_table(
        "site_request_status_daily_counts",
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("page_path", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("status_code IN (200, 404)", name="ck_site_request_status_code"),
        sa.CheckConstraint("request_count > 0", name="ck_site_request_count_positive"),
        sa.PrimaryKeyConstraint("event_date", "page_path", "status_code"),
    )


def downgrade() -> None:
    op.drop_table("site_request_status_daily_counts")
    op.drop_constraint(
        "ck_site_analytics_events_checkout_field",
        "site_analytics_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_site_analytics_events_duration",
        "site_analytics_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_site_analytics_events_click_target",
        "site_analytics_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_site_analytics_events_click_target",
        "site_analytics_events",
        "(event_type = 'page_view' AND click_target IS NULL) OR "
        "(event_type = 'click' AND click_target IS NOT NULL)",
    )
    op.drop_constraint(
        "ck_site_analytics_events_type",
        "site_analytics_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_site_analytics_events_type",
        "site_analytics_events",
        "event_type IN ('page_view', 'click')",
    )
    op.drop_column("site_analytics_events", "field_key")
    op.drop_column("site_analytics_events", "duration_seconds")
