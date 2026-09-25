from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import app as webapp
from domains.connect_analytics import ConnectAnalytics
from tests.e2e.common import BaseE2ETest


class ConnectE2ETests(BaseE2ETest):
    def setUp(self) -> None:
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory(prefix="ce-connect-e2e-")
        self.source = Path(self.temporary.name) / "trade_shows.json"
        self.config = json.loads(webapp.TRADE_SHOWS_PATH.read_text(encoding="utf-8"))
        self._write_config()
        self.path_patch = patch.object(webapp, "TRADE_SHOWS_PATH", self.source)
        self.path_patch.start()
        self.prior_analytics = webapp.app.extensions.get("connect_analytics")
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.analytics = ConnectAnalytics(engine)
        self.analytics.create_schema_for_tests()
        webapp.app.extensions["connect_analytics"] = self.analytics

    def tearDown(self) -> None:
        try:
            super().tearDown()
        finally:
            if self.prior_analytics is None:
                webapp.app.extensions.pop("connect_analytics", None)
            else:
                webapp.app.extensions["connect_analytics"] = self.prior_analytics
            self.analytics.engine.dispose()
            self.path_patch.stop()
            self.temporary.cleanup()

    def _write_config(self) -> None:
        self.source.write_text(json.dumps(self.config), encoding="utf-8")

    def _make_active(self, key: str) -> None:
        show = self.config["events"][key]
        today = datetime.now(ZoneInfo(show["time_zone"])).date()
        show["start_date"] = (today - timedelta(days=1)).isoformat()
        show["end_date"] = (today + timedelta(days=1)).isoformat()
        self.config["connect_event_override"] = None
        self._write_config()

    @staticmethod
    def _event_response(action: str):
        return lambda response: response.url.endswith("/api/connect/event")

    def _counts(self) -> dict[tuple[str, str], int]:
        with self.analytics.engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT trade_show_key, action, count FROM connect_event_counts"
            )).all()
        return {(key, action): count for key, action, count in rows}

    def test_active_show_actions_and_mobile_layout(self) -> None:
        self._make_active("jis-fall-2026")
        self.page.set_viewport_size({"width": 390, "height": 844})
        with self.page.expect_response(self._event_response("visit")) as visit_response:
            response = self.goto("/connect")
        self.assertEqual(visit_response.value.status, 204)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertTrue(self.page.locator("nav.navbar.fixed-top").is_visible())
        self.assertEqual(self.page.locator('nav.navbar a[href="/connect"]').count(), 0)
        self.assertIn("ce_logo_shape.webp", self.page.evaluate(
            "getComputedStyle(document.body, '::before').backgroundImage"
        ))
        resources = self.page.evaluate("performance.getEntriesByType('resource').map(item => item.name)")
        self.assertFalse(any("layout.css" in url or "bootstrap.bundle.min.js" in url for url in resources))
        self.assertFalse(any("ce_logo_shape.png" in url or "ce_logo_full.png" in url for url in resources))
        title_style = self.page.locator("h1.connect-title").evaluate("""title => ({
            font: getComputedStyle(title).fontFamily,
            weight: getComputedStyle(title).fontWeight,
            color: getComputedStyle(title).color
        })""")
        self.assertIn("Playfair Display", title_style["font"])
        self.assertEqual(title_style["weight"], "700")
        self.assertEqual(title_style["color"], "rgb(199, 169, 95)")
        self.assertIn("GREAT MEETING YOU AT", self.page.locator("main").inner_text().upper())
        self.assertEqual(self.page.locator("h1").inner_text(), "JIS MIAMI FALL 2026")
        self.assertEqual(self.page.locator(".connect-booth").inner_text(), "Booth 117")
        self.assertTrue(self.page.locator(".connect-logo").evaluate("image => image.complete && image.naturalWidth > 0"))
        self.assertEqual(self._counts()[("jis-fall-2026", "visit")], 1)
        self.assertEqual(self.page.locator(".connect-social-actions svg").count(), 2)
        self.assertEqual(self.page.locator(".page-shell > footer").count(), 1)
        self.assertIn("California Earrings · Los Angeles, CA, USA", self.page.locator(".page-shell > footer").inner_text())
        self.assertTrue(self.page.locator(".page-shell > footer .footer-social").is_visible())
        shop = self.page.get_by_role("link", name="See Our Catalog")
        self.assertIn("hero-action-btn", shop.get_attribute("class"))
        self.assertEqual(shop.locator("svg.hero-action-btn__icon").count(), 1)

        self.page.get_by_role("button", name="Toggle navigation").click()
        self.page.wait_for_function("document.querySelector('#nav').classList.contains('show')")
        self.assertEqual(self.page.get_by_role("button", name="Toggle navigation").get_attribute("aria-expanded"), "true")
        self.page.keyboard.press("Escape")
        self.assertEqual(self.page.get_by_role("button", name="Toggle navigation").get_attribute("aria-expanded"), "false")
        self.assertFalse(self.page.locator("#nav").is_visible())
        self.page.get_by_role("button", name="Toggle navigation").click()
        self.page.get_by_role("button", name="Toggle navigation").click()
        self.page.wait_for_function("""() => {
            const nav = document.querySelector('#nav');
            return !nav.classList.contains('show') && !nav.classList.contains('collapsing');
        }""")

        whatsapp = self.page.get_by_role("link", name="Message Us on WhatsApp")
        parsed = urlsplit(whatsapp.get_attribute("href"))
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "https://wa.me/18183319292")
        self.assertEqual(
            parse_qs(parsed.query)["text"],
            ["Hi! I met California Earrings at JIS Miami Fall 2026, Booth 117 and wanted to stay connected."],
        )
        with self.page.expect_download() as download_info:
            self.page.get_by_role("link", name="Save Our Contact").click()
        vcard = Path(download_info.value.path()).read_text(encoding="utf-8")
        for expected in (
            "FN:Giancarlo Jauregui", "ORG:California Earrings", "TEL;TYPE=CELL:18183319292",
            "TEL;TYPE=WORK,VOICE:12139357272", "EMAIL;TYPE=WORK:californiaearrings@gmail.com",
            "URL;TYPE=Instagram:https://www.instagram.com/california_earrings/",
            "URL;TYPE=WhatsApp:https://wa.me/18183319292",
            "NOTE:Met at JIS Miami Fall 2026 — Booth 117",
        ):
            self.assertIn(expected, vcard)

        for width in (320, 390, 1280):
            self.page.set_viewport_size({"width": width, "height": 844})
            self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            button_styles = []
            for name in (
                "Message Us on WhatsApp", "Save Our Contact", "See Our Catalog",
                "Follow on Instagram", "Follow on TikTok",
            ):
                link = self.page.get_by_role("link", name=name)
                button_styles.append(link.evaluate("""link => {
                    const style = getComputedStyle(link);
                    return [style.fontFamily, style.fontSize, style.fontWeight,
                        style.lineHeight, style.letterSpacing, style.borderRadius];
                }"""))
                self.assertTrue(link.evaluate("link => link.getBoundingClientRect().height >= 48"))
            self.assertTrue(all(style == button_styles[0] for style in button_styles))
            if width == 1280:
                self._artifact_dir().mkdir(parents=True, exist_ok=True)
                self.page.screenshot(path=str(self._artifact_dir() / "desktop.png"), animations="disabled")
        self.page.set_viewport_size({"width": 390, "height": 667})
        self.assertTrue(whatsapp.evaluate("link => link.getBoundingClientRect().bottom <= innerHeight"))
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertEqual(urlsplit(self.page.locator('link[rel="canonical"]').get_attribute("href")).path, "/connect")
        self.assertEqual(self.page.locator('meta[name="robots"]').get_attribute("content"), "noindex, follow")

    def test_event_switch_expiration_override_and_generic_fallback(self) -> None:
        self.page.set_viewport_size({"width": 390, "height": 844})
        self._make_active("jck-2027")
        self.config["events"]["jck-2027"]["booth"] = "Booth #999"
        self._write_config()
        with self.page.expect_response(self._event_response("visit")):
            self.goto("/connect")
        self.assertEqual(self.page.locator("h1").inner_text(), "JCK 2027")
        self.assertEqual(self.page.locator(".connect-booth").inner_text(), "Booth 999")
        message = parse_qs(urlsplit(self.page.get_by_role("link", name="Message Us on WhatsApp").get_attribute("href")).query)["text"][0]
        self.assertIn("JCK 2027, Booth 999", message)

        self.config["events"]["jck-2027"]["end_date"] = "2000-01-01"
        self._write_config()
        with self.page.expect_response(self._event_response("visit")):
            self.page.reload(wait_until="domcontentloaded")
        self.assertTrue(self.page.url.endswith("/connect"))
        self.assertEqual(self.page.locator("h1").inner_text(), "CONNECT WITH CALIFORNIA EARRINGS")
        self.assertIn("Wholesale 14K gold jewelry from Los Angeles.", self.page.locator("main").inner_text())
        self.assertEqual(self.page.locator(".connect-booth").count(), 0)
        message = parse_qs(urlsplit(self.page.get_by_role("link", name="Message Us on WhatsApp").get_attribute("href")).query)["text"][0]
        self.assertEqual(message, "Hi! I met California Earrings at a trade show and wanted to stay connected.")
        self.assertEqual(self.page.get_by_role("link", name="Save Our Contact").get_attribute("href"), "/connect/contact.vcf")
        with self.page.expect_download() as download_info:
            self.page.get_by_role("link", name="Save Our Contact").click()
        self.assertNotIn("NOTE:Met at", Path(download_info.value.path()).read_text(encoding="utf-8"))

        self.config["connect_event_override"] = "jis-fall-2026"
        self._write_config()
        with self.page.expect_response(self._event_response("visit")):
            self.page.reload(wait_until="domcontentloaded")
        self.assertEqual(self.page.locator("h1").inner_text(), "JIS MIAMI FALL 2026")

        self.source.write_text("{invalid json", encoding="utf-8")
        with self.page.expect_response(self._event_response("visit")):
            self.page.reload(wait_until="domcontentloaded")
        self.assertEqual(self.page.locator("h1").inner_text(), "CONNECT WITH CALIFORNIA EARRINGS")

    def test_all_destinations_record_aggregate_clicks(self) -> None:
        self._make_active("jis-fall-2026")
        with self.page.expect_response(self._event_response("visit")):
            self.goto("/connect")
        self.page.evaluate("""() => {
            document.querySelectorAll('[data-destination]').forEach(link => {
                link.addEventListener('click', event => event.preventDefault());
            });
        }""")
        for destination in ("whatsapp", "save_contact", "instagram", "tiktok", "shop"):
            with self.page.expect_response(self._event_response(destination)) as response:
                self.page.locator(f'[data-destination="{destination}"]').click()
            self.assertEqual(response.value.status, 204)
            self.assertEqual(self._counts()[("jis-fall-2026", destination)], 1)
        self.assertIn("instagram.com/california_earrings", self.page.get_by_role("link", name="Follow on Instagram").get_attribute("href"))
        self.assertIn("tiktok.com/@californiaearrings", self.page.get_by_role("link", name="Follow on TikTok").get_attribute("href"))
        self.assertEqual(self.page.get_by_role("link", name="See Our Catalog").get_attribute("href"), "/catalog/")
