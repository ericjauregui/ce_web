"""Private deployment/verification commands; never print database configuration."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, select

from domains.orders import OrderItemRecord, OrderRecord, create_database_engine, database_url_from_env


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate or privately verify the configured order database.")
    parser.add_argument("action", choices=("migrate", "check", "verify"))
    parser.add_argument("--order-number", help="For verify: exact confirmation number, including #CE prefix.")
    args = parser.parse_args(argv)
    engine = None
    try:
        # Read only the server environment. No secret is passed on the command line.
        database_url = database_url_from_env()
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        if args.action == "migrate":
            command.upgrade(config, "head")
            print("Order database migrations completed.")
            return 0

        engine = create_database_engine(database_url)
        with engine.connect() as connection:
            current_heads = set(MigrationContext.configure(connection).get_current_heads())
            expected_heads = set(ScriptDirectory.from_config(config).get_heads())
            if current_heads != expected_heads:
                print("Order database schema is not current. Run the migration command.", file=sys.stderr)
                return 1
            print("PostgreSQL connection OK; order schema is current.")
            if args.action == "check":
                return 0
            if not args.order_number:
                order_count = connection.scalar(select(func.count()).select_from(OrderRecord))
                item_count = connection.scalar(select(func.count()).select_from(OrderItemRecord))
                print(f"Saved orders: {order_count}; saved line items: {item_count}.")
                return 0
            row = connection.execute(
                select(
                    OrderRecord.internal_id, OrderRecord.order_number,
                    OrderRecord.submitted_at, OrderRecord.status,
                    OrderRecord.email_status, OrderRecord.total_distinct_items,
                    OrderRecord.total_quantity,
                ).where(OrderRecord.order_number == args.order_number)
            ).mappings().first()
            if row is None:
                print("No saved order matches that confirmation number.", file=sys.stderr)
                return 1
            actual = connection.execute(
                select(func.count(), func.sum(OrderItemRecord.quantity))
                .where(OrderItemRecord.order_id == row["internal_id"])
            ).one()
            if actual[0] != row["total_distinct_items"] or actual[1] != row["total_quantity"]:
                print("Saved order item totals do not match; investigate before processing.", file=sys.stderr)
                return 1
            print(
                f'{row["order_number"]}: submitted={row["submitted_at"].isoformat()} '
                f'status={row["status"]} email_status={row["email_status"]} '
                f'line_items={actual[0]} quantity={actual[1]}'
            )
            return 0
    except Exception:
        # Driver/configuration errors can contain connection details or SQL
        # parameters. Operators get a nonzero exit without printing those details.
        print("Database operation failed. Check server DATABASE_URL, connectivity, and migration configuration privately.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
