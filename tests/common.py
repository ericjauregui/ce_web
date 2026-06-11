from __future__ import annotations

import logging
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app as webapp
from domains import emailing as emailing_domain


class BaseWebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        webapp.app.config.update(TESTING=True)
        cls.client = webapp.app.test_client()
        cls.valid_code = webapp.load_products()[0]["code"]
        cls.team_members = webapp.build_team_members(webapp.load_team())
        cls.first_member = cls.team_members[0] if cls.team_members else {"slug": "", "name": ""}

    def setUp(self) -> None:
        self._emailing_tempdir = tempfile.TemporaryDirectory()
        temp_root = Path(self._emailing_tempdir.name)
        order_log_dir = temp_root / "logs"
        order_csv_dir = order_log_dir / "orders_csv"
        order_event_log_dir = order_log_dir / ".logs"

        self._emailing_patchers = [
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
            patch.object(emailing_domain, "ORDER_LOG_DIR", order_log_dir),
            patch.object(emailing_domain, "ORDER_DB_PATH", order_log_dir / "orders.db"),
            patch.object(emailing_domain, "ORDER_CSV_DIR", order_csv_dir),
            patch.object(emailing_domain, "ORDER_EVENT_LOG_DIR", order_event_log_dir),
            patch("domains.emailing.graph_send", return_value=None),
            patch("domains.emailing.time.sleep", return_value=None),
        ]
        for patcher in self._emailing_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.addCleanup(self._cleanup_order_email_logger)
        self.addCleanup(self._emailing_tempdir.cleanup)
        self._cleanup_order_email_logger()

        with self.client.session_transaction() as sess:
            sess["cart"] = {}
            sess["cart_notes"] = {}
            sess.pop("last_order_csv", None)
            sess.pop("last_order_rows", None)
            sess.pop("last_order_token", None)
            sess.pop("last_order_id", None)
            sess.pop("last_order_csv_filename", None)

    @staticmethod
    def _cleanup_order_email_logger() -> None:
        logger = logging.getLogger("order_email_events")
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        emailing_domain._CURRENT_LOG_PATH = None

    @staticmethod
    def load_site_css() -> str:
        root_css = Path(webapp.BASE_DIR) / "static" / "css" / "style.css"
        import_pattern = re.compile(r"@import\s+url\(\s*[\"'](?P<path>[^\"']+)[\"']\s*\)\s*;")

        def read_with_imports(path: Path, seen: set[Path]) -> str:
            resolved = path.resolve()
            if resolved in seen:
                return ""
            seen.add(resolved)

            content = path.read_text(encoding="utf-8")

            def repl(match: re.Match[str]) -> str:
                rel = match.group("path")
                imported = (path.parent / rel).resolve()
                return read_with_imports(imported, seen)

            return import_pattern.sub(repl, content)

        return read_with_imports(root_css, set())
