from __future__ import annotations

import unittest

from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from domains.orders import (
    DatabaseConfigurationError,
    IdempotencyConflictError,
    OrderItemRecord,
    OrderPersistenceError,
    OrderRecord,
    OrderRepository,
    OrderValidationError,
    create_database_engine,
)


CUSTOMER = {
    "name": "Ada Lovelace",
    "company": "Analytical Jewelry",
    "phone": "+1 555 0100",
    "email": "buyer@example.com",
    "address_line_1": "123 Market Street",
    "address_line_2": "Suite 4",
    "city": "Los Angeles",
    "state": "California",
    "postal_code": "90001",
    "country": "United States",
    "country_key": "us",
    "notes": "Call before shipping",
}

ITEMS = [
    {
        "code": "102SB",
        "name": "Classic Gold Diamond Studs",
        "collection": "Studs",
        "quantity": 2,
        "notes": "One pair",
        "image": "102SB.jpg",
    },
    {
        "code": "200HG",
        "name": "Gold Hoop",
        "collection": "Hoops",
        "quantity": 3,
        "notes": "",
        "image": "200HG.jpg",
    },
]


class OrderRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = OrderRepository(
            "sqlite+pysqlite:///:memory:", allow_sqlite_for_tests=True
        )
        self.repository.create_schema_for_tests()

    def tearDown(self) -> None:
        self.repository.engine.dispose()

    def test_requires_database_url_and_rejects_implicit_sqlite(self) -> None:
        with self.assertRaises(DatabaseConfigurationError):
            OrderRepository("")
        with self.assertRaises(DatabaseConfigurationError):
            OrderRepository("sqlite+pysqlite:///:memory:")
        with self.assertRaisesRegex(DatabaseConfigurationError, "DATABASE_URL is invalid") as raised:
            OrderRepository("postgresql://user:secret@localhost:not-a-port/database")
        self.assertNotIn("secret", str(raised.exception))

    def test_postgres_engine_uses_conservative_pool_and_hides_parameters(self) -> None:
        engine = create_database_engine("postgresql://db_user:secret@localhost/example")
        self.addCleanup(engine.dispose)
        self.assertEqual(engine.pool.size(), 1)
        self.assertEqual(engine.pool._max_overflow, 0)
        self.assertEqual(engine.pool._timeout, 5)
        self.assertTrue(engine.pool._pre_ping)
        self.assertTrue(engine.hide_parameters)
        self.assertNotIn("secret", repr(engine.url))

    def test_creates_and_retrieves_atomic_order_with_multiple_items(self) -> None:
        result = self.repository.create_order(
            idempotency_key="submission-0001", customer=CUSTOMER, items=ITEMS
        )

        self.assertTrue(result.created)
        self.assertRegex(result.order.order_number, r"^#CE\d{8}$")
        self.assertEqual(result.order.total_distinct_items, 2)
        self.assertEqual(result.order.total_quantity, 5)
        self.assertEqual(result.order.email_status, "pending")
        self.assertEqual([item.sku for item in result.order.items], ["102SB", "200HG"])
        self.assertIsNotNone(result.order.created_at.tzinfo)

        by_id = self.repository.get_order(result.order.id)
        by_token = self.repository.get_order_by_access_token(result.order.access_token)
        self.assertEqual(by_id, result.order)
        self.assertEqual(by_token, result.order)

    def test_address_fields_round_trip_individually(self) -> None:
        order = self.repository.create_order(
            idempotency_key="address-fields-0001", customer=CUSTOMER, items=ITEMS
        ).order

        self.assertEqual(
            {
                key: order.customer[key]
                for key in (
                    "address_line_1",
                    "address_line_2",
                    "city",
                    "state",
                    "postal_code",
                    "country",
                    "country_key",
                )
            },
            {
                "address_line_1": "123 Market Street",
                "address_line_2": "Suite 4",
                "city": "Los Angeles",
                "state": "California",
                "postal_code": "90001",
                "country": "United States",
                "country_key": "us",
            },
        )
        self.assertNotIn("address", order.customer)

    def test_schema_and_saved_models_have_no_monetary_fields(self) -> None:
        self.assertTrue(
            {"total_amount", "currency"}.isdisjoint(OrderRecord.__table__.columns.keys())
        )
        self.assertTrue(
            {"unit_price", "line_total"}.isdisjoint(OrderItemRecord.__table__.columns.keys())
        )
        order = self.repository.create_order(
            idempotency_key="no-money-fields-0001", customer=CUSTOMER, items=ITEMS
        ).order
        self.assertFalse(hasattr(order, "total_amount"))
        self.assertFalse(hasattr(order, "currency"))
        self.assertFalse(hasattr(order.items[0], "unit_price"))
        self.assertFalse(hasattr(order.items[0], "line_total"))

    def test_same_idempotency_key_and_payload_returns_existing_order(self) -> None:
        first = self.repository.create_order(
            idempotency_key="submission-0002", customer=CUSTOMER, items=ITEMS
        )
        second = self.repository.create_order(
            idempotency_key="submission-0002", customer=dict(CUSTOMER), items=list(ITEMS)
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(second.order.id, first.order.id)
        with Session(self.repository.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(OrderRecord)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(OrderItemRecord)), 2)

    def test_idempotency_key_cannot_be_reused_for_different_payload(self) -> None:
        self.repository.create_order(
            idempotency_key="submission-0003", customer=CUSTOMER, items=ITEMS
        )
        changed_items = [dict(ITEMS[0], quantity=4), ITEMS[1]]
        with self.assertRaises(IdempotencyConflictError):
            self.repository.create_order(
                idempotency_key="submission-0003", customer=CUSTOMER, items=changed_items
            )

    def test_item_insert_failure_rolls_back_order(self) -> None:
        def fail_item_insert(*args):
            statement = args[2]
            parameters = args[3]
            if "INSERT INTO order_items" in statement:
                raise OperationalError(statement, parameters, RuntimeError("simulated write failure"))

        event.listen(self.repository.engine, "before_cursor_execute", fail_item_insert)
        try:
            with self.assertRaises(OrderPersistenceError):
                self.repository.create_order(
                    idempotency_key="submission-0004", customer=CUSTOMER, items=ITEMS
                )
        finally:
            event.remove(self.repository.engine, "before_cursor_execute", fail_item_insert)

        with Session(self.repository.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(OrderRecord)), 0)
            self.assertEqual(session.scalar(select(func.count()).select_from(OrderItemRecord)), 0)

    def test_database_write_failure_is_wrapped_without_database_details(self) -> None:
        repository = OrderRepository(
            "sqlite+pysqlite:///:memory:", allow_sqlite_for_tests=True
        )
        self.addCleanup(repository.engine.dispose)
        with self.assertRaisesRegex(OrderPersistenceError, "The order could not be saved") as raised:
            repository.create_order(
                idempotency_key="submission-0005", customer=CUSTOMER, items=ITEMS
            )
        self.assertNotIn("INSERT", str(raised.exception))

    def test_delivery_status_and_csv_are_durable(self) -> None:
        created = self.repository.create_order(
            idempotency_key="submission-0006", customer=CUSTOMER, items=ITEMS
        ).order
        failed = self.repository.record_email_delivery(
            created.id, "failed", error_message="Graph provider unavailable"
        )
        self.assertEqual(failed.email_status, "failed")
        self.assertIsNotNone(failed.email_attempted_at)
        self.assertIsNone(failed.email_sent_at)

        sent = self.repository.record_email_delivery(created.id, "sent")
        saved = self.repository.store_order_csv(
            created.id, "order_id,#CE00000001\n", "ce_order_CE00000001.csv"
        )
        self.assertEqual(sent.email_status, "sent")
        self.assertIsNotNone(sent.email_sent_at)
        self.assertEqual(saved.csv_text, "order_id,#CE00000001\n")
        self.assertEqual(saved.csv_filename, "ce_order_CE00000001.csv")

    def test_rejects_monetary_fields_in_items_and_metadata(self) -> None:
        cases = (
            ([dict(ITEMS[0], price=None)], None),
            ([dict(ITEMS[0], Unit_Price="12.50")], None),
            ([dict(ITEMS[0], metadata={"catalog": {"prices": [12.5]}})], None),
            (ITEMS, {"checkout": [{"totalAmount": "12.50"}]}),
            (ITEMS, {"Currency": "USD"}),
        )
        for index, (items, metadata) in enumerate(cases, start=1):
            with self.subTest(index=index):
                with self.assertRaisesRegex(OrderValidationError, "monetary field"):
                    self.repository.create_order(
                        idempotency_key=f"money-field-{index:04d}",
                        customer=CUSTOMER,
                        items=items,
                        metadata=metadata,
                    )

    def test_rejects_fractional_boolean_and_nonfinite_values(self) -> None:
        for index, quantity in enumerate((True, 1.5, "NaN"), start=1):
            with self.subTest(quantity=quantity):
                with self.assertRaises(OrderValidationError):
                    self.repository.create_order(
                        idempotency_key=f"invalid-quantity-{index}",
                        customer=CUSTOMER,
                        items=[dict(ITEMS[0], quantity=quantity)],
                    )


if __name__ == "__main__":
    unittest.main()
