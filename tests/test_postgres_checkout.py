from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from sqlalchemy import delete, select

import app as webapp
from domains.orders import OrderRecord, OrderRepository
from tests.common import BaseWebTest


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL", "").startswith(("postgres://", "postgresql://")),
                     "Set TEST_DATABASE_URL to a dedicated migrated PostgreSQL test database.")
class PostgresCheckoutTests(BaseWebTest):
    def test_committed_multi_item_order_survives_email_failure_and_new_connection(self) -> None:
        repository = OrderRepository(os.environ["TEST_DATABASE_URL"])
        reader = OrderRepository(os.environ["TEST_DATABASE_URL"])
        self.addCleanup(repository.engine.dispose)
        self.addCleanup(reader.engine.dispose)
        webapp.app.extensions["order_repository"] = repository
        codes = [product["code"] for product in webapp.load_products()[:2]]
        for code, quantity in zip(codes, (2, 3)):
            self.assertEqual(self.client.post("/api/cart/add", json={"code": code, "qty": quantity}).status_code, 200)
        key = self.checkout_idempotency_key()
        data = {
            "idempotency_key": key, "name": "Integration Buyer", "company": "Test Only",
            "email": "buyer@example.com", "phone_country_code": "us", "phone": "555-0101",
            "city": "Los Angeles", "state": "California", "country_key": "us",
            "country": "United States", "notes": "Synthetic PostgreSQL integration test",
        }
        visible_before_email = []

        def failing_transport(*args, **kwargs):
            # A separate connection can see only committed rows.
            with reader.engine.connect() as connection:
                visible_before_email.append(connection.scalar(
                    select(OrderRecord.id).where(OrderRecord.idempotency_key == key)
                ))
            raise OSError("simulated transport failure")

        try:
            with patch("domains.emailing.graph_send", side_effect=failing_transport):
                response = self.client.post("/checkout", data=data)
            self.assertEqual(response.status_code, 200)
            with self.client.session_transaction() as session:
                order_id, token = session["last_order_id"], session["last_order_token"]
                self.assertNotIn("last_order_customer", session)
                self.assertNotIn("last_order_rows", session)
                self.assertEqual(session["cart"], {})
            self.assertTrue(visible_before_email)
            self.assertTrue(all(value == order_id for value in visible_before_email))
            saved = reader.get_order(order_id)
            self.assertEqual(saved.email_status, "failed")
            self.assertEqual(saved.total_quantity, 5)
            self.assertEqual([item.sku for item in saved.items], codes)
            repository.engine.dispose()
            webapp.app.extensions["order_repository"] = reader
            csv_response = self.client.get(f"/download/order/{token}.csv")
            self.assertEqual(csv_response.status_code, 200)
            self.assertIn("private, no-store", csv_response.headers["Cache-Control"])
            self.assertTrue(all(code in csv_response.get_data(as_text=True) for code in codes))
            with patch("domains.emailing.graph_send") as transport:
                self.assertEqual(self.client.post("/checkout", data=data).status_code, 200)
                transport.assert_not_called()
        finally:
            with reader.engine.begin() as connection:
                connection.execute(delete(OrderRecord).where(OrderRecord.idempotency_key == key))
