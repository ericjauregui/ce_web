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
        self.assertIn("address_line_1,650 S Hill St Suite 518", csv_text)
        self.assertIn("address_line_2,Building A", csv_text)
        self.assertIn("postal_code,90014", csv_text)
        self.assertIn("code,quantity,item_notes", csv_text.lower())
        self.assertNotIn("collection", csv_text.lower())
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
        self.assertNotIn("text/csv", raw_message)  # CSV is saved but not attached to email
        self.assertIn("application/pdf", raw_message)

    def test_send_order_email_uses_persisted_order_number_without_sqlite_sequence(self) -> None:
        with patch("domains.emailing.next_order_number") as next_number:
            with patch("domains.emailing.graph_send", return_value=None):
                result = emailing.send_order_email(
                    self._customer(),
                    self._items(),
                    order_id="#CE00000042",
                )

        next_number.assert_not_called()
        self.assertEqual(result["order_id"], "#CE00000042")
        self.assertFalse(emailing.ORDER_DB_PATH.exists())

    def test_order_csv_neutralizes_spreadsheet_formulas(self) -> None:
        customer = self._customer()
        customer["company"] = "=HYPERLINK(\"https://bad.example\")"
        items = self._items()
        items[0]["notes"] = "+cmd|' /C calc'!A0"

        csv_text = emailing.build_order_csv("#CE00000001", customer, items)

        self.assertIn("'=HYPERLINK", csv_text)
        self.assertIn("'+cmd", csv_text)

    def test_receipt_content_and_plain_text_parity(self) -> None:
        options = dict(support_email="orders@californiaearrings.com", submitted_at="2026-09-20T17:00:00+00:00")
        html = emailing.build_order_html("#CE00000042", self._customer(), self._items(), logo_cid="logo-cid", signature_cid="signature-cid", **options)
        text = emailing.build_order_plain_text("#CE00000042", self._customer(), self._items(), **options)
        for content in (html, text):
            for value in ("Order request received", "#CE00000042", "Pending confirmation", "1 unique item · Total quantity: 3", "Sep 20, 2026 at 10:00 AM PDT", "Building A", "A100", "Need matching pair"):
                self.assertIn(value, content)
            self.assertNotIn("contact the customer", content.lower())
            self.assertNotIn("CSV attachment included", content)
        self.assertIn('width="200"', html)
        self.assertIn('max-width:600px', html)
        self.assertIn('scope="col"', html)
        self.assertNotIn("cid:signature-cid", html)
        self.assertIn("mailto:orders@californiaearrings.com?subject=Question%20about%20order%20request%20%23CE00000042", html)
        self.assertLess(len(html.encode()), 80_000)

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

    def test_receipt_codes_maps_and_cell_contact(self) -> None:
        from urllib.parse import parse_qs, urlsplit
        from html import unescape
        import re

        customer = self._customer()
        customer["address_line_1"] = '123 A & B Street'
        html = emailing.build_order_html("#CE1", customer, self._items())
        text = emailing.build_order_plain_text("#CE1", customer, self._items())
        for content in (html, text):
            self.assertNotIn("Gold Stud", content)
            self.assertIn("A100", content)
            self.assertLess(content.index("Cell: +1 (818) 331-9292"), content.index("Office: +1 (213) 935-7272"))
        links = re.findall(r'href="([^"]+)"', html)
        maps = [parse_qs(urlsplit(unescape(link)).query)["query"][0] for link in links if "google.com/maps" in link]
        self.assertEqual(maps[0], ", ".join(emailing._customer_shipping_address_lines(customer)))
        self.assertIn("650 S Hill St Suite 518", maps[1])
        self.assertIn('href="tel:+18183319292"', html)

    def test_receipt_timestamp_uses_pacific_standard_time_in_winter(self) -> None:
        for renderer in (emailing.build_order_html, emailing.build_order_plain_text):
            content = renderer("#CE1", self._customer(), self._items(), submitted_at="2026-01-20T02:30:00+00:00")
            self.assertIn("Jan 19, 2026 at 06:30 PM PST", content)

    def test_receipt_optional_fields_and_escaping(self) -> None:
        customer = dict(name='A & B <Buyer>', email='buyer@example.com', notes='First line\n<script>alert("x")</script>')
        items = [dict(code='A<100', name='Gold & Pearl', quantity=999, notes='First note'),
                 dict(code='A<100', name='Gold & Pearl', quantity=2, notes='Second note'),
                 dict(code='A<100-B', name='Variant', quantity=1, notes='')]
        html = emailing.build_order_html("#CE1", customer, items)
        self.assertIn("2 unique items · Total quantity: 1002", html)
        self.assertIn("First note", html)
        self.assertIn("Second note", html)
        self.assertIn("A &amp; B &lt;Buyer&gt;", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn(">Ship to<", html)
        self.assertNotIn("Submitted ", html)
        self.assertNotIn("<img", html)
        customer["notes"] = ""
        self.assertNotIn("Your order notes", emailing.build_order_html("#CE1", customer, items))

    def test_receipt_retains_every_line_in_large_order(self) -> None:
        items = [dict(code=f"SKU-{i}", name=f"Product {i}", quantity=999, notes=f"Note {i}") for i in range(100)]
        html = emailing.build_order_html("#CE1", self._customer(), items)
        text = emailing.build_order_plain_text("#CE1", self._customer(), items)
        for item in items:
            self.assertIn(f"<strong>{item['code']}</strong>", html)
            self.assertIn(f"{item['code']} | Qty: 999", text)
        self.assertIn("100 unique items · Total quantity: 99900", html)

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
