from __future__ import annotations

import base64
import logging
import os
import tempfile
import unittest
from datetime import datetime
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

    def test_current_week_log_path_uses_monday_start_of_week_date(self) -> None:
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 6, 11, 12, 0, 0, tzinfo=tz)

        with patch("domains.emailing.datetime", FixedDatetime):
            log_path = emailing.current_week_log_path()

        self.assertEqual(log_path.name, "email_events_20260608.log")

    def test_send_order_email_saves_csv_and_embeds_signature(self) -> None:
        sent_messages: list[str] = []

        def fake_graph_send(message, settings) -> None:
            sent_messages.append(message.as_string())

        with patch("domains.emailing.graph_send", side_effect=fake_graph_send):
            result = emailing.send_order_email(self._customer(), self._items())

        self.assertTrue(result["ok"])
        self.assertEqual(result["order_id"], "#00001")
        self.assertFalse(result["fallback_used"])

        csv_path = Path(result["csv_path"])
        self.assertTrue(csv_path.exists())
        csv_text = csv_path.read_text(encoding="utf-8")
        self.assertIn("order_id,#00001", csv_text)
        self.assertIn("code,name,collection,quantity,item_notes", csv_text.lower())
        self.assertIn("Need matching pair", csv_text)

        self.assertEqual(len(sent_messages), 1)
        raw_message = sent_messages[0]
        self.assertIn("Subject: California Earrings | Wholesale Order", raw_message)
        self.assertIn("To: buyer@example.com", raw_message)
        self.assertIn("Bcc: orders@californiaearrings.com, sales@example.com, merch@example.com", raw_message)
        self.assertIn("ce_logo_full.png", raw_message)
        self.assertIn("ce_email_signature.png", raw_message)
        self.assertIn("Content-ID:", raw_message)
        self.assertIn("cid:", raw_message)

    def test_build_order_html_uses_cleaner_layout_and_social_cta(self) -> None:
        html = emailing.build_order_html(
            "#00001",
            self._customer(),
            self._items(),
            logo_cid="logo-cid",
            signature_cid="signature-cid",
        )

        self.assertIn("Wholesale Order</h1>", html)
        self.assertNotIn("Wholesale Order #00001", html)
        self.assertNotIn("Order ID", html)
        self.assertNotIn(">Item<", html)
        self.assertIn("width=\"420\"", html)
        self.assertIn("max-width:540px", html)
        self.assertIn("Keep up with us on Instagram and TikTok", html)
        self.assertIn("Instagram @california_earrings", html)
        self.assertIn("TikTok @californiaearrings", html)
        self.assertIn("href=\"https://www.instagram.com/california_earrings/\"", html)
        self.assertIn("href=\"https://www.tiktok.com/@californiaearrings\"", html)
        self.assertNotIn("background:#0d0d0d", html)
        self.assertNotIn("background:#ffffff;text-align:center;", html)

    def test_build_order_html_renders_without_customer_notes(self) -> None:
        customer = self._customer()
        customer["notes"] = ""

        html = emailing.build_order_html(
            "#00001",
            customer,
            self._items(),
            logo_cid="logo-cid",
            signature_cid="signature-cid",
        )

        self.assertIn("Submitted by <strong>Test Buyer</strong>", html)
        self.assertIn("Instagram @california_earrings", html)
        self.assertNotIn("<td style=\"padding:8px 0;color:#8f7b54;vertical-align:top;\">Notes</td>", html)

    def test_send_order_email_uses_fallback_after_normal_retries(self) -> None:
        subjects: list[str] = []

        def fake_graph_send(message, settings) -> None:
            subjects.append(str(message["Subject"]))
            if len(subjects) == 1:
                raise RuntimeError("smtp down")

        with patch("domains.emailing.graph_send", side_effect=fake_graph_send):
            result = emailing.send_order_email(self._customer(), self._items())

        self.assertTrue(result["ok"])
        self.assertTrue(result["fallback_used"])
        self.assertEqual(
            subjects,
            [
                "California Earrings | Wholesale Order",
                "California Earrings | Wholesale Order",
            ],
        )

        log_files = list(self.order_event_log_dir.glob("*.log"))
        self.assertEqual(len(log_files), 1)
        log_text = log_files[0].read_text(encoding="utf-8")
        self.assertIn('"event_type": "order_email_exhausted_retries"', log_text)
        self.assertIn('"event_type": "fallback_email_success"', log_text)

    def test_send_order_email_raises_with_saved_order_when_config_is_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
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

    def test_send_order_email_rejects_non_graph_transport(self) -> None:
        with patch.dict(os.environ, {"EMAIL_TRANSPORT": "smtp"}, clear=False):
            with self.assertRaises(emailing.OrderEmailDeliveryError) as raised:
                emailing.send_order_email(self._customer(), self._items())

        self.assertIn("Only EMAIL_TRANSPORT=graph is supported.", str(raised.exception))

    def test_send_order_email_uses_graph_transport_when_configured(self) -> None:
        sent_messages: list[str] = []

        def fake_graph_send(message, settings) -> None:
            self.assertEqual(settings.graph_sender_upn, "orders@californiaearrings.com")
            sent_messages.append(str(message["Subject"]))

        graph_env = {
            "EMAIL_TRANSPORT": "graph",
            "TENANT_ID": "tenant-id",
            "CLIENT_ID": "client-id",
            "CLIENT_SECRET": "client-secret",
            "GRAPH_SENDER_UPN": "orders@californiaearrings.com",
        }
        with patch.dict(os.environ, graph_env, clear=False):
            with patch("domains.emailing.graph_send", side_effect=fake_graph_send):
                result = emailing.send_order_email(self._customer(), self._items())

        self.assertTrue(result["ok"])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(sent_messages, ["California Earrings | Wholesale Order"])

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
        self.assertIn(b"ce_email_signature.png", mime_bytes)
        self.assertIn(b"cid:", mime_bytes)