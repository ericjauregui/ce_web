"""Customer-facing commerce journeys against a live local server.

Every order uses a fresh test-only SQLite database. Graph delivery is intercepted
at its transport boundary, and email files are redirected to a temporary folder.
The shared E2E runner writes screenshots, browser events, and a hash manifest.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app as webapp
from domains import emailing
from domains.orders import OrderItemRecord, OrderRecord, OrderRepository
from tests.e2e.common import BaseE2ETest


class CommerceE2ETests(BaseE2ETest):
    browser_name = "chromium"

    def setUp(self) -> None:
        super().setUp()
        self._temporary = tempfile.TemporaryDirectory(prefix="ce-commerce-e2e-")
        self._root = Path(self._temporary.name)
        self._stack = ExitStack()
        self._prior_repository = webapp.app.extensions.get("order_repository")
        self.repository = OrderRepository(
            f"sqlite+pysqlite:///{self._root / 'orders.sqlite3'}",
            allow_sqlite_for_tests=True,
        )
        self.repository.create_schema_for_tests()
        webapp.app.extensions["order_repository"] = self.repository
        self.sent_messages = []
        self.fail_delivery = False
        self.fail_first_delivery = False
        self._stack.enter_context(patch.dict(webapp.app.config, {
            "RATE_LIMIT_TESTING": False,
            "RATE_LIMIT_TRUST_PROXY": False,
        }))
        self._stack.enter_context(patch.dict("os.environ", {
            "EMAIL_TRANSPORT": "graph",
            "AZURE_TENANT_ID": "",
            "AZURE_CLIENT_ID": "",
            "AZURE_CLIENT_SECRET": "",
            "TENANT_ID": "local-e2e-tenant",
            "CLIENT_ID": "local-e2e-client",
            "CLIENT_SECRET": "local-e2e-secret",
            "GRAPH_SENDER_UPN": "orders@example.test",
            "SMTP_USER": "orders@example.test",
            "ORDER_BCC_EMAILS": "",
        }))
        email_dir = self._root / "email"
        for name, path in (
            ("ORDER_LOG_DIR", email_dir),
            ("ORDER_DB_PATH", email_dir / "legacy.db"),
            ("ORDER_CSV_DIR", email_dir / "csv"),
            ("ORDER_EVENT_LOG_DIR", email_dir / "events"),
        ):
            self._stack.enter_context(patch.object(emailing, name, path))
        self._stack.enter_context(patch.object(emailing, "graph_send", side_effect=self._capture_delivery))
        self._stack.enter_context(patch.object(emailing.time, "sleep", return_value=None))
        self._stack.enter_context(patch.object(emailing, "ORDER_EMAIL_MAX_RETRIES", 0))
        self._reset_email_logger()
        self.limiter = webapp.app.extensions["ce_rate_limiter"]
        self.limiter.reset()

    def tearDown(self) -> None:
        try:
            super().tearDown()
        finally:
            self.limiter.reset()
            self._reset_email_logger()
            self._stack.close()
            if self._prior_repository is None:
                webapp.app.extensions.pop("order_repository", None)
            else:
                webapp.app.extensions["order_repository"] = self._prior_repository
            self.repository.engine.dispose()
            self._temporary.cleanup()

    @staticmethod
    def _reset_email_logger() -> None:
        logger = logging.getLogger("order_email_events")
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        emailing._CURRENT_LOG_PATH = None

    def _capture_delivery(self, message, settings) -> None:
        self.sent_messages.append(message)
        if self.fail_delivery or (self.fail_first_delivery and len(self.sent_messages) == 1):
            raise OSError("local simulated Graph outage")

    def _post_json(self, path: str, body: dict):
        return self.context.request.post(
            f"{self.base_url}{path}",
            data=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )

    def _add_item(self, code: str, quantity: int = 1) -> None:
        response = self._post_json("/api/cart/add", {"code": code, "qty": quantity})
        self.assertEqual(response.status, 200)

    def _fill_checkout(
        self, *, company: str = "Example Wholesale", name: str = "Synthetic Buyer",
        order_notes: str = "Please confirm availability",
    ) -> dict[str, str]:
        self.goto("/checkout")
        form = self.page.locator("#checkoutForm")
        self.assertEqual(form.count(), 1)
        form.locator('[name="name"]').fill(name)
        form.locator('[name="company"]').fill(company)
        form.locator('[name="email"]').fill("buyer@example.test")
        form.locator('[name="phone"]').fill("555-0101")
        form.locator('[name="address_line_1"]').fill("650 S Hill St")
        form.locator('[name="address_line_2"]').fill("Suite 518")
        form.locator('[name="postal_code"]').fill("90014")
        form.locator('[name="city"]').fill("Los Angeles")
        form.locator('[name="notes"]').fill(order_notes)

        self.page.locator("#checkoutPhoneCountry").fill("United States")
        self.page.locator("#checkoutPhoneCountryCombobox .checkout-combobox__option").first.click()
        self.page.locator("#checkoutCountry").fill("United States")
        self.page.locator("#checkoutCountryCombobox .checkout-combobox__option").first.click()
        self.page.locator("#checkoutState").fill("California")
        self.page.locator("#checkoutStateCombobox .checkout-combobox__option").first.click()
        self.assertEqual(self.page.locator("#checkoutCountryKey").input_value(), "us")
        self.assertEqual(self.page.locator("#checkoutPhoneCountryCode").input_value(), "us")
        return form.evaluate("form => Object.fromEntries(new FormData(form))")

    def _submit_checkout(self) -> None:
        with self.page.expect_response(
            lambda response: urlsplit(response.url).path == "/checkout"
            and response.request.method == "POST"
        ) as sent:
            self.page.locator("#checkoutForm button[type='submit']").click()
        self.assertEqual(sent.value.status, 200)
        self.page.get_by_role("heading", name="Order Submitted", exact=True).wait_for()

    def test_cart_controls_preserve_browser_isolation_and_notes(self) -> None:
        unknown = self._post_json("/api/cart/add", {"code": "NOT_A_PRODUCT", "qty": 1})
        self.assertEqual(unknown.status, 400)
        self.add_first_catalog_item_to_cart()
        cookie = next(cookie for cookie in self.context.cookies() if cookie["name"] == "session")
        self.assertTrue(cookie["httpOnly"])
        self.assertEqual(cookie["sameSite"], "Lax")
        self.assertGreater(cookie["expires"] - datetime.now(timezone.utc).timestamp(), 29 * 24 * 60 * 60)
        other_context = self._browser.new_context()
        try:
            other_count = other_context.request.get(f"{self.base_url}/api/cart/count")
            self.assertEqual(other_count.json()["total_items"], 0)
        finally:
            other_context.close()

        self.goto("/cart")
        self.page.locator(".qty-plus").click()
        self.page.wait_for_function(
            "() => document.querySelector('#cartTotalQty')?.textContent.trim() === '2'"
        )
        with self.page.expect_response(lambda response: "/api/cart/note" in response.url):
            self.page.locator(".item-note-input").fill("Matching pair requested")
        self.goto("/checkout")
        self.assertIn("Matching pair requested", self.page.locator(".checkout-items-table").inner_text())
        self.assertIn("2", self.page.locator(".checkout-summary-metrics").inner_text())
        self.goto("/cart")
        self.page.locator("#clearOrderBtn").click()
        self.page.get_by_text("Your showcase is waiting.", exact=False).wait_for()
        self.assertEqual(self.context.request.get(f"{self.base_url}/api/cart/count").json()["total_items"], 0)
        rejected_note = self._post_json("/api/cart/note", {"code": self.valid_code, "note": "orphan"})
        self.assertEqual(rejected_note.status, 400)

    def test_checkout_saves_snapshot_email_and_private_downloads(self) -> None:
        codes = [product["code"] for product in webapp.load_products()[:2]]
        self._add_item(codes[0], 2)
        self._add_item(codes[1], 3)
        note = self._post_json("/api/cart/note", {"code": codes[0], "note": "+keep paired"})
        self.assertEqual(note.status, 200)
        form_data = self._fill_checkout(
            company='=HYPERLINK("https://bad.example")',
            name="A & B <Buyer>",
            order_notes='Please confirm availability <script>alert("x")</script>',
        )
        self._submit_checkout()

        order_number = self.page.locator(".order-submitted-card strong").first.inner_text().removeprefix("Order ID: ")
        self.assertRegex(order_number, r"^#CE\d{8}$")
        self.assertIn("TotalQuantity:5", re.sub(r"\s+", "", self.page.locator(".order-submitted-summary-bar").inner_text()))
        self.assertEqual(len(self.sent_messages), 1)
        message = self.sent_messages[0]
        self.assertEqual(str(message["Subject"]), "California Earrings | Wholesale Order")
        plain_receipt = message.get_body(preferencelist=("plain",)).get_content()
        html_receipt = message.get_body(preferencelist=("html",)).get_content()
        for receipt in (plain_receipt, html_receipt):
            for value in (
                "Order request received", order_number, "Pending confirmation",
                "2 unique items · Total quantity: 5", *codes,
                "+keep paired", "650 S Hill St Suite 518", "Please confirm availability",
            ):
                self.assertIn(value, receipt)
        self.assertIn("google.com/maps", html_receipt)
        self.assertIn('href="tel:+18183319292"', html_receipt)
        self.assertLess(html_receipt.index("Cell: +1 (818) 331-9292"), html_receipt.index("Office: +1 (213) 935-7272"))
        self.assertIn("A &amp; B &lt;Buyer&gt;", html_receipt)
        self.assertIn("&lt;script&gt;alert", html_receipt)
        self.assertNotIn('<script>alert("x")</script>', html_receipt)
        self.assertTrue(any(part.get_filename() == "ce_logo_full.png" for part in message.walk()))

        csv_url = self.page.get_by_role("link", name="Download CSV").get_attribute("href")
        pdf_url = self.page.get_by_role("link", name="Download PDF").get_attribute("href")
        self.assertIsNotNone(csv_url)
        self.assertIsNotNone(pdf_url)
        csv_response = self.context.request.get(f"{self.base_url}{csv_url}")
        pdf_response = self.context.request.get(f"{self.base_url}{pdf_url}")
        for response in (csv_response, pdf_response):
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["cache-control"], "private, no-store, max-age=0")
        csv_text = csv_response.text()
        self.assertIn(f"order_id,{order_number}", csv_text)
        self.assertIn("country,USA", csv_text)
        self.assertIn("'=HYPERLINK", csv_text)
        self.assertIn("'+keep paired", csv_text)
        self.assertTrue(all(code in csv_text for code in codes))
        self.assertTrue(pdf_response.body().startswith(b"%PDF"))
        self.assertGreater(len(pdf_response.body()), 1000)
        export_artifacts = self._artifact_dir()
        export_artifacts.mkdir(parents=True, exist_ok=True)
        (export_artifacts / "synthetic-order.csv").write_text(csv_text, encoding="utf-8")
        (export_artifacts / "synthetic-order.pdf").write_bytes(pdf_response.body())
        (export_artifacts / "intercepted-email.eml").write_bytes(message.as_bytes())

        other_context = self._browser.new_context()
        try:
            denied = other_context.request.get(f"{self.base_url}{csv_url}")
            self.assertEqual(denied.status, 404)
            self.assertEqual(denied.headers["cache-control"], "private, no-store, max-age=0")
        finally:
            other_context.close()

        with Session(self.repository.engine) as session:
            record = session.scalar(select(OrderRecord).where(OrderRecord.order_number == order_number))
            self.assertIsNotNone(record)
            self.assertEqual(session.scalar(select(func.count()).select_from(OrderItemRecord)), 2)
            self.assertEqual(record.email_status, "sent")
            self.assertEqual(record.total_quantity, 5)
            saved = self.repository.get_order(record.id)
            self.assertEqual(saved.customer["address_line_1"], "650 S Hill St")
            self.assertEqual(saved.customer["address_line_2"], "Suite 518")
            self.assertEqual(saved.customer["postal_code"], "90014")
            self.assertEqual(saved.customer["country_key"], "us")
            self.assertEqual([item.sku for item in saved.items], codes)
            self.assertEqual(saved.items[0].notes, "+keep paired")
            self.assertTrue({"total_amount", "currency"}.isdisjoint(OrderRecord.__table__.columns.keys()))
            self.assertTrue({"unit_price", "line_total"}.isdisjoint(OrderItemRecord.__table__.columns.keys()))

        retry = self.context.request.post(f"{self.base_url}/checkout", form=form_data)
        self.assertEqual(retry.status, 200)
        self.assertIn(order_number, retry.text())
        self.assertEqual(len(self.sent_messages), 1)
        changed = self.context.request.post(
            f"{self.base_url}/checkout", form={**form_data, "company": "Different Company"}
        )
        self.assertEqual(changed.status, 409)

    def test_email_outage_keeps_durable_order_and_download(self) -> None:
        self.fail_delivery = True
        self._add_item(self.valid_code, 2)
        self._fill_checkout()
        self._submit_checkout()
        self.assertIn("order was saved", self.page.locator(".order-submitted-card").inner_text())
        self.assertGreaterEqual(len(self.sent_messages), 1)
        with Session(self.repository.engine) as session:
            record = session.scalar(select(OrderRecord))
            self.assertIsNotNone(record)
            self.assertEqual(record.email_status, "failed")
            self.assertEqual(record.total_quantity, 2)
        csv_url = self.page.get_by_role("link", name="Download CSV").get_attribute("href")
        self.assertEqual(self.context.request.get(f"{self.base_url}{csv_url}").status, 200)
        self.assertEqual(self.context.request.get(f"{self.base_url}/api/cart/count").json()["total_items"], 0)

    def test_transient_email_failure_uses_fallback_without_duplicate_order(self) -> None:
        self.fail_first_delivery = True
        self._add_item(self.valid_code)
        self._fill_checkout()
        self._submit_checkout()
        self.assertEqual(len(self.sent_messages), 2)
        with Session(self.repository.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(OrderRecord)), 1)
            record = session.scalar(select(OrderRecord))
            self.assertEqual(record.email_status, "sent")
        event_logs = list((self._root / "email" / "events").glob("*.log"))
        self.assertEqual(len(event_logs), 1)
        self.assertIn('"event_type": "fallback_email_success"', event_logs[0].read_text())

    def test_database_write_failure_keeps_cart_and_hides_driver_details(self) -> None:
        self._add_item(self.valid_code)
        self._fill_checkout()

        def fail_item_insert(connection, cursor, statement, parameters, context, executemany):
            if "INSERT INTO order_items" in statement:
                raise OperationalError(statement, parameters, RuntimeError("private driver detail"))

        event.listen(self.repository.engine, "before_cursor_execute", fail_item_insert)
        try:
            with self.page.expect_response(
                lambda response: urlsplit(response.url).path == "/checkout"
                and response.request.method == "POST"
            ) as sent:
                self.page.locator("#checkoutForm button[type='submit']").click()
            self.assertEqual(sent.value.status, 503)
            self.assertIn("couldn't save your order", self.page.get_by_role("alert").inner_text())
            self.assertNotIn("private driver detail", self.page.content())
            self.assertEqual(self.context.request.get(f"{self.base_url}/api/cart/count").json()["total_items"], 1)
            with Session(self.repository.engine) as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(OrderRecord)), 0)
                self.assertEqual(session.scalar(select(func.count()).select_from(OrderItemRecord)), 0)
            self.assertEqual(self.sent_messages, [])
        finally:
            event.remove(self.repository.engine, "before_cursor_execute", fail_item_insert)

    def test_rate_limit_preserves_cart_and_public_cache_boundaries(self) -> None:
        with patch.dict(webapp.app.config, {
            "RATE_LIMIT_TESTING": True,
            "CART_RATE_LIMIT": "2 per minute",
            "CHECKOUT_RATE_LIMIT": "2 per minute",
        }):
            self._add_item(self.valid_code)
            self.assertEqual(self._post_json("/api/cart/note", {"code": self.valid_code, "note": "Keep"}).status, 200)
            blocked = self._post_json("/api/cart/clear", {})
            self.assertEqual(blocked.status, 429)
            self.assertGreater(int(blocked.headers["retry-after"]), 0)
            self.assertEqual(blocked.headers["cache-control"], "private, no-store, max-age=0")
            spoofed = self.context.request.post(
                f"{self.base_url}/api/cart/clear",
                data="{}",
                headers={"Content-Type": "application/json", "X-Forwarded-For": "198.51.100.99"},
            )
            self.assertEqual(spoofed.status, 429)
            self.assertEqual(self.context.request.get(f"{self.base_url}/api/cart/count").json()["total_items"], 1)
            self.goto("/checkout")
            self.assertEqual(self.page.locator("#checkoutForm").count(), 1)
            key = self.page.locator('[name="idempotency_key"]').input_value()
            for expected in (400, 400, 429):
                response = self.context.request.post(
                    f"{self.base_url}/checkout", form={"idempotency_key": key, "name": "Incomplete"}
                )
                self.assertEqual(response.status, expected)
            self.assertIn("Your cart is still saved", response.text())
            self.assertEqual(self.context.request.get(f"{self.base_url}/api/cart/count").json()["total_items"], 1)

        home = self.goto("/")
        self.assertEqual(home.headers["cache-control"], "private, no-store, max-age=0")
        css_href = self.page.locator('link[href*="/static/css/styles/base.css?v="]').first.get_attribute("href")
        self.assertIsNotNone(css_href)
        current = self.context.request.get(f"{self.base_url}{css_href}")
        forged = self.context.request.get(f"{self.base_url}{urlsplit(css_href).path}?v=forged")
        self.assertEqual(current.headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertEqual(forged.headers["cache-control"], "public, max-age=300, must-revalidate")
        self.assertNotIn("set-cookie", current.headers)
        missing = self.context.request.get(f"{self.base_url}/missing-page")
        self.assertEqual(missing.headers["cache-control"], "private, no-store, max-age=0")
