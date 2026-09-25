from __future__ import annotations

import unittest

from domains.orders import (
    DatabaseConfigurationError,
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
