"""Create durable orders and order items.

Revision ID: 20260912_0001
Revises:
Create Date: 2026-09-12 00:00:00
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260912_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_number", sa.String(length=24), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("access_token", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("address_line_1", sa.String(length=300), nullable=False),
        sa.Column("address_line_2", sa.String(length=300), nullable=False),
        sa.Column("city", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=160), nullable=False),
        sa.Column("postal_code", sa.String(length=40), nullable=False),
        sa.Column("country", sa.String(length=160), nullable=False),
        sa.Column("country_key", sa.String(length=8), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("order_metadata", sa.JSON(), nullable=False),
        sa.Column("total_distinct_items", sa.Integer(), nullable=False),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("email_status", sa.String(length=16), nullable=False),
        sa.Column("email_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_error", sa.String(length=1000), nullable=True),
        sa.Column("csv_text", sa.Text(), nullable=True),
        sa.Column("csv_filename", sa.String(length=255), nullable=True),
        sa.CheckConstraint("email_status IN ('pending', 'sent', 'failed')", name="ck_orders_email_status"),
        sa.CheckConstraint("total_distinct_items > 0", name="ck_orders_distinct_items_positive"),
        sa.CheckConstraint("total_quantity > 0", name="ck_orders_total_quantity_positive"),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("access_token", name="uq_orders_access_token"),
        sa.UniqueConstraint("id", name="uq_orders_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
    )
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("product_name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("variant", sa.String(length=200), nullable=False),
        sa.Column("collection", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=False),
        sa.Column("image", sa.String(length=500), nullable=False),
        sa.Column("item_metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint("position > 0", name="ck_order_items_position_positive"),
        sa.CheckConstraint("quantity > 0 AND quantity <= 999", name="ck_order_items_quantity"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.internal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "position", name="uq_order_items_position"),
    )


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
