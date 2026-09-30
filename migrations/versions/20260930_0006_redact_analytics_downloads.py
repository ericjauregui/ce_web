"""Remove private order download tokens from existing analytics.

Revision ID: 20260930_0006
Revises: 20260927_0005
"""
import re
from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260930_0006"
down_revision: str | None = "20260927_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _download_path(value: str) -> str:
    return re.sub(r"^/download/order/[^/]+\.(csv|pdf)$", r"/download/order/file.\1", value)


def upgrade() -> None:
    connection = op.get_bind()
    events = sa.table("site_analytics_events", sa.column("id", sa.Integer),
        sa.column("page_path", sa.String), sa.column("click_target", sa.String))
    rows = connection.execute(sa.select(events).where(sa.or_(
        events.c.page_path.like("/download/order/%"),
        events.c.click_target.like("internal:/download/order/%"),
    ))).mappings().all()
    for row in rows:
        changes = {}
        path = _download_path(row["page_path"])
        if path != row["page_path"]:
            changes["page_path"] = path
        target = row["click_target"]
        if target and re.fullmatch(r"internal:/download/order/[^/]+\.(csv|pdf)", target):
            changes["click_target"] = f"action:download-order-{target.rsplit('.', 1)[1]}"
        if changes:
            connection.execute(events.update().where(events.c.id == row["id"]).values(**changes))

    counts = sa.table("site_request_status_daily_counts", sa.column("event_date", sa.Date),
        sa.column("page_path", sa.String), sa.column("status_code", sa.Integer),
        sa.column("request_count", sa.Integer))
    rows = connection.execute(sa.select(counts).where(
        counts.c.page_path.like("/download/order/%")
    )).mappings().all()
    for row in rows:
        path = _download_path(row["page_path"])
        if path == row["page_path"]:
            continue
        day_status = sa.and_(counts.c.event_date == row["event_date"],
            counts.c.status_code == row["status_code"])
        destination = sa.and_(day_status, counts.c.page_path == path)
        existing = connection.execute(sa.select(counts.c.request_count).where(destination)).scalar_one_or_none()
        source = sa.and_(day_status, counts.c.page_path == row["page_path"])
        if existing is None:
            connection.execute(counts.update().where(source).values(page_path=path))
        else:
            connection.execute(counts.update().where(destination).values(
                request_count=counts.c.request_count + row["request_count"]))
            connection.execute(counts.delete().where(source))


def downgrade() -> None:
    # This data-only repair preserves event/count totals. Private tokens cannot
    # be reconstructed and must not be reintroduced by rollback.
    pass
