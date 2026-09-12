from __future__ import annotations

from datetime import datetime, timezone
import importlib
import os
import unittest
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from domains.orders import OrderRepository, create_database_engine
from tests.test_orders_repository import CUSTOMER, ITEMS


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL", "").startswith(("postgres://", "postgresql://")),
                     "Requires an isolated PostgreSQL test database.")
class MoneyRemovalMigrationTests(unittest.TestCase):
    def test_upgrade_removes_money_preserves_addresses_and_order_retry(self):
        engine = create_database_engine(os.environ["TEST_DATABASE_URL"])
        namespace = "migration_test_" + uuid4().hex
        try:
            with engine.begin() as connection:
                connection.execute(sa.schema.CreateSchema(namespace))
                connection.execute(sa.text(f'SET LOCAL search_path TO "{namespace}"'))
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    importlib.import_module("migrations.versions.20260912_0001_create_orders").upgrade()
                metadata = sa.MetaData()
                orders = sa.Table("orders", metadata, autoload_with=connection)
                items = sa.Table("order_items", metadata, autoload_with=connection)
                now = datetime.now(timezone.utc)
                parent_id = connection.scalar(orders.insert().values(
                    id=str(uuid4()), order_number="#PG00000001", idempotency_key="migration-order-test",
                    payload_hash="0" * 64, access_token="private-test-token", status="submitted",
                    created_at=now, submitted_at=now,
                    **{("customer_name" if k == "name" else k): v for k, v in CUSTOMER.items()},
                    order_metadata={"source": "web_checkout", "currency": "USD", "nested": {"price": 9, "keep": True}},
                    total_distinct_items=2, total_quantity=5, total_amount=99, currency="USD", email_status="pending",
                ).returning(orders.c.internal_id))
                for position, item in enumerate(ITEMS, 1):
                    connection.execute(items.insert().values(
                        order_id=parent_id, position=position, sku=item["code"], product_name=item["name"],
                        description="", variant="", collection=item["collection"], quantity=item["quantity"],
                        notes=item["notes"], image=item["image"], unit_price=1, line_total=item["quantity"],
                        item_metadata={"amount": 1},
                    ))
                with Operations.context(context):
                    importlib.import_module("migrations.versions.20260912_0002_remove_monetary_fields").upgrade()

            inspector = sa.inspect(engine)
            self.assertTrue({"total_amount", "currency"}.isdisjoint(
                column["name"] for column in inspector.get_columns("orders", schema=namespace)))
            self.assertTrue({"unit_price", "line_total"}.isdisjoint(
                column["name"] for column in inspector.get_columns("order_items", schema=namespace)))
            repository = OrderRepository(engine=engine.execution_options(schema_translate_map={None: namespace}))
            retry = repository.create_order(
                idempotency_key="migration-order-test", customer=CUSTOMER, items=ITEMS,
                metadata={"source": "web_checkout", "nested": {"keep": True}},
            )
            self.assertFalse(retry.created)
            self.assertEqual(retry.order.order_number, "#PG00000001")
            self.assertEqual(retry.order.customer, CUSTOMER)
            self.assertEqual(retry.order.total_quantity, 5)
        finally:
            with engine.begin() as connection:
                connection.execute(sa.schema.DropSchema(namespace, cascade=True, if_exists=True))
            engine.dispose()
