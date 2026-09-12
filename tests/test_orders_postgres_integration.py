from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from uuid import uuid4

from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from domains.orders import OrderItemRecord, OrderPersistenceError, OrderRecord, OrderRepository
from tests.test_orders_repository import CUSTOMER, ITEMS


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL", "").startswith(("postgres://", "postgresql://")),
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database.",
)
class PostgresOrderRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = OrderRepository(os.environ["TEST_DATABASE_URL"])
        # Migrations must be applied before this test; runtime schema creation is intentionally absent.
        self.keys: set[str] = set()

    def new_key(self) -> str:
        key = f"pg-test-{uuid4()}"
        self.keys.add(key)
        return key

    def tearDown(self) -> None:
        if self.keys:
            with Session(self.repository.engine) as session, session.begin():
                session.execute(delete(OrderRecord).where(OrderRecord.idempotency_key.in_(self.keys)))
        self.repository.engine.dispose()

    def test_postgres_atomic_multi_item_idempotency_and_retrieval(self) -> None:
        key = self.new_key()
        result = self.repository.create_order(
            idempotency_key=key, customer=CUSTOMER, items=ITEMS
        )
        duplicate = self.repository.create_order(
            idempotency_key=key, customer=CUSTOMER, items=ITEMS
        )

        self.assertTrue(result.created)
        self.assertFalse(duplicate.created)
        self.assertEqual(result.order.id, duplicate.order.id)
        self.assertEqual(
            self.repository.get_order_by_access_token(result.order.access_token), result.order
        )
        with Session(self.repository.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(OrderRecord).where(OrderRecord.id == result.order.id)
                ),
                1,
            )
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(OrderItemRecord)
                    .join(OrderRecord)
                    .where(OrderRecord.id == result.order.id)
                ),
                2,
            )

    def test_postgres_item_failure_rolls_back_parent_order(self) -> None:
        key = self.new_key()

        def fail_item_insert(*args):
            statement = args[2]
            parameters = args[3]
            if "INSERT INTO order_items" in statement:
                raise OperationalError(statement, parameters, RuntimeError("simulated item failure"))

        event.listen(self.repository.engine, "before_cursor_execute", fail_item_insert)
        try:
            with self.assertRaises(OrderPersistenceError):
                self.repository.create_order(
                    idempotency_key=key, customer=CUSTOMER, items=ITEMS
                )
        finally:
            event.remove(self.repository.engine, "before_cursor_execute", fail_item_insert)

        with Session(self.repository.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(OrderRecord)
                    .where(OrderRecord.idempotency_key == key)
                ),
                0,
            )

    def test_concurrent_idempotent_submissions_create_exactly_one_order(self) -> None:
        key = self.new_key()
        barrier = threading.Barrier(2)

        def submit() -> tuple[str, bool]:
            repository = OrderRepository(os.environ["TEST_DATABASE_URL"])
            try:
                barrier.wait(timeout=5)
                result = repository.create_order(
                    idempotency_key=key, customer=CUSTOMER, items=ITEMS
                )
                return result.order.id, result.created
            finally:
                repository.engine.dispose()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))

        self.assertEqual(len({order_id for order_id, _ in results}), 1)
        self.assertEqual(sorted(created for _, created in results), [False, True])
        with Session(self.repository.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(OrderRecord)
                    .where(OrderRecord.idempotency_key == key)
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
