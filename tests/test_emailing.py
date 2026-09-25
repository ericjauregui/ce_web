from __future__ import annotations

import base64
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domains import emailing


class EmailingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)

        temp_root = Path(self._tempdir.name)
        self.order_log_dir = temp_root / "logs"
        self.order_csv_dir = self.order_log_dir / "orders_csv"
        self.order_event_log_dir = self.order_log_dir / ".logs"

        self._patchers = [
            patch.dict(
                os.environ,
                {
                    "EMAIL_TRANSPORT": "graph",
                    "SMTP_USER": "orders@californiaearrings.com",
                    "TENANT_ID": "tenant-id",
                    "CLIENT_ID": "client-id",
                    "CLIENT_SECRET": "client-secret",
                    "GRAPH_SENDER_UPN": "orders@californiaearrings.com",
                    "ORDER_BCC_EMAILS": "sales@example.com,merch@example.com",
                },
                clear=False,
            ),
            patch.object(emailing, "ORDER_LOG_DIR", self.order_log_dir),
            patch.object(emailing, "ORDER_DB_PATH", self.order_log_dir / "orders.db"),
            patch.object(emailing, "ORDER_CSV_DIR", self.order_csv_dir),
            patch.object(emailing, "ORDER_EVENT_LOG_DIR", self.order_event_log_dir),
            patch("domains.emailing.time.sleep", return_value=None),
        ]
        for patcher in self._patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.addCleanup(self._reset_logger)
        self._reset_logger()

    def _reset_logger(self) -> None:
        logger = logging.getLogger("order_email_events")
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        emailing._CURRENT_LOG_PATH = None

    @staticmethod
    def _customer() -> dict[str, str]:
        return {
            "name": "Test Buyer",
            "company": "Sample Co",
            "phone": "+1 555-0101",
            "email": "buyer@example.com",
            "address_line_1": "650 S Hill St Suite 518",
            "address_line_2": "Building A",
            "postal_code": "90014",
            "city": "Los Angeles",
            "state": "California",
            "country": "United States",
            "notes": "Please confirm availability.",
        }

    @staticmethod
    def _items() -> list[dict[str, object]]:
        return [
            {
                "code": "A100",
                "name": "Gold Stud",
                "collection": "studs",
                "quantity": 3,
                "notes": "Need matching pair",
            }
        ]

    def test_receipt_embeds_original_product_photo_once(self) -> None:
        items = [dict(code="101SB", name="Gold Earrings", quantity=2, image="101SB.jpg", notes="First"),
                 dict(code="101SB", name="Gold Earrings", quantity=1, image="101SB.jpg", notes="Second"),
                 dict(code="missing", name="No photo", quantity=1, image="absent-photo.jpg")]
        message = emailing.make_message("#CE1", self._customer(), items, "", Path("order.csv"), emailing._load_email_settings())
        photos = [part for part in message.walk() if part.get_filename() == "101SB.jpg"]
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0].get_payload(decode=True), (emailing.BASE_DIR / "static/product_images/101SB.jpg").read_bytes())
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertEqual(html.count("cid:" + str(photos[0]["Content-ID"])[1:-1]), 2)
        self.assertNotIn(">Photo</th>", html)
        self.assertIn(">Notes</th>", html)
        self.assertIn("missing", html)
        self.assertNotIn("absent-photo.jpg", html)
        self.assertIn('width="56"', html)

    def test_thumbnail_loader_rejects_external_and_parent_paths(self) -> None:
        images = ["../assets/ce_logo_full.png", "https://example.com/image.jpg", "/tmp/photo.jpg", "absent.jpg"]
        self.assertEqual(emailing._product_thumbnail_attachments([dict(image=image) for image in images], emailing.BASE_DIR), {})

    def test_receipt_timestamp_uses_pacific_standard_time_in_winter(self) -> None:
        for renderer in (emailing.build_order_html, emailing.build_order_plain_text):
            content = renderer("#CE1", self._customer(), self._items(), submitted_at="2026-01-20T02:30:00+00:00")
            self.assertIn("Jan 19, 2026 at 06:30 PM PST", content)

    def test_receipt_retains_every_line_in_large_order(self) -> None:
        items = [dict(code=f"SKU-{i}", name=f"Product {i}", quantity=999, notes=f"Note {i}") for i in range(100)]
        html = emailing.build_order_html("#CE1", self._customer(), items)
        text = emailing.build_order_plain_text("#CE1", self._customer(), items)
        for item in items:
            self.assertIn(f"<strong>{item['code']}</strong>", html)
            self.assertIn(f"{item['code']} | Qty: 999", text)
        self.assertIn("100 unique items · Total quantity: 99900", html)

    def test_send_order_email_raises_with_saved_order_when_config_is_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AZURE_TENANT_ID": "",
                "AZURE_CLIENT_ID": "",
                "AZURE_CLIENT_SECRET": "",
                "TENANT_ID": "",
                "CLIENT_ID": "",
                "CLIENT_SECRET": "",
                "GRAPH_SENDER_UPN": "",
            },
            clear=False,
        ):
            with self.assertRaises(emailing.OrderEmailDeliveryError) as raised:
                emailing.send_order_email(self._customer(), self._items())

        exc = raised.exception
        self.assertEqual(exc.order_id, "#00001")
        self.assertTrue(exc.csv_path.exists())
        self.assertIn("Graph transport requires", str(exc))
        self.assertIn("order_id,#00001", exc.csv_text)

    def test_graph_send_posts_mime_message_with_inline_images(self) -> None:
        captured_request: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def getcode(self) -> int:
                return 202

        def fake_urlopen(request, timeout):
            captured_request["url"] = request.full_url
            captured_request["headers"] = {
                name.lower(): value
                for name, value in request.header_items()
            }
            captured_request["data"] = request.data
            captured_request["timeout"] = timeout
            return FakeResponse()

        settings = emailing.EmailSettings(
            sender_email="orders@californiaearrings.com",
            notify_email="orders@californiaearrings.com",
            bcc_emails=("sales@example.com", "merch@example.com"),
            graph_tenant_id="tenant-id",
            graph_client_id="client-id",
            graph_client_secret="client-secret",
            graph_sender_upn="orders@californiaearrings.com",
        )
        message = emailing.make_message(
            "#00001",
            self._customer(),
            self._items(),
            "order_id,#00001\n",
            self.order_csv_dir / "ce_order_00001_20260611.csv",
            settings,
        )

        with patch("domains.emailing._fetch_graph_access_token", return_value="graph-token"):
            with patch("domains.emailing.urlopen", side_effect=fake_urlopen):
                emailing.graph_send(message, settings)

        self.assertEqual(
            captured_request["url"],
            "https://graph.microsoft.com/v1.0/users/orders%40californiaearrings.com/sendMail",
        )
        self.assertEqual(captured_request["timeout"], emailing.ORDER_EMAIL_REQUEST_TIMEOUT_SECONDS)
        headers = captured_request["headers"]
        self.assertEqual(headers["authorization"], "Bearer graph-token")
        self.assertEqual(headers["content-type"], "text/plain")

        mime_bytes = base64.b64decode(captured_request["data"])
        self.assertIn(b"multipart/related", mime_bytes)
        self.assertIn(b"Content-ID:", mime_bytes)
        self.assertIn(b"Content-Disposition: inline", mime_bytes)
        self.assertIn(b"ce_logo_full.png", mime_bytes)
        self.assertIn(b"cid:", mime_bytes)
