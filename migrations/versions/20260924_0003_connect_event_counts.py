"""Create aggregate trade-show connect counters.

Revision ID: 20260924_0003
Revises: 20260912_0002
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260924_0003"
down_revision: str = "20260912_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connect_event_counts",
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("trade_show_key", sa.String(length=80), nullable=False),
        sa.Column("trade_show_name", sa.String(length=160), nullable=False),
        sa.Column("booth", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("count > 0", name="ck_connect_event_counts_positive"),
        sa.PrimaryKeyConstraint("event_date", "trade_show_key", "booth", "action"),
    )


def downgrade() -> None:
    op.drop_table("connect_event_counts")
