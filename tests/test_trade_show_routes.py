from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import app as webapp
from domains.trade_shows import load_trade_show
from tests.common import BaseWebTest


class TradeShowRouteTests(BaseWebTest):
    def test_trade_show_page_uses_active_event_and_global_navigation(self) -> None:
        response = self.client.get("/trade-shows")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("Visit California Earrings", body)
        self.assertIn("JIS Fall 2026", body)
        self.assertIn("October 16–19, 2026", body)
        self.assertIn("Miami Beach Convention Center", body)
        self.assertIn("Booth #117", body)
        self.assertIn('href="/trade-shows" aria-current="page"', body)
        self.assertIn("/static/assets/trade-shows/jis-fall-logo.png", body)
        self.assertIn("/static/assets/trade-shows/miami-night.webp", body)
        self.assertIn("/static/assets/trade-shows/owner-welcome.mp4", body)
        self.assertIn("Meet the Owner", body)
        self.assertIn("miami-mobile-v2.webp", body)
        self.assertIn('href="/contact">Contact Us</a>', body)
        self.assertIn('href="/team">Meet our Team</a>', body)
        self.assertIn("Show Details</a>", body)
        self.assertIn('class="trade-show-venue-link"', body)
        self.assertIn("Office Phone:", body)
        self.assertIn("Find us online:", body)
        self.assertNotIn("saveShowContact", body)
        self.assertNotIn("ownerSoundButton", body)
        self.assertNotIn("A message from our owner", body)
        self.assertNotIn('class="trade-show-booth-highlight"', body)
        self.assertEqual(body.count('class="trade-show-product-card"'), 6)
        self.assertNotIn('src="https://www.jisshow.com/', body)

    def test_trade_show_page_is_in_sitemap(self) -> None:
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/trade-shows</loc>", response.get_data(as_text=True))

    def test_active_event_can_be_switched_without_template_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "trade_shows.json"
            config_path.write_text(
                json.dumps(
                    {
                        "active_event": "future-show",
                        "events": {
                            "future-show": {
                                "name": "Future Show 2028",
                                "dates_display": "January 10–12, 2028",
                                "venue": "Test Convention Center",
                                "city": "Test City, California",
                                "logo_asset": "assets/trade-shows/jck-logo-white.png",
                                "hero_image": "assets/trade-shows/las-vegas-night.webp",
                                "curated_products": [],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            show = load_trade_show(
                config_path,
                webapp.load_products(),
                webapp.BASE_DIR / "static",
            )

        self.assertEqual(show["key"], "future-show")
        self.assertEqual(show["name"], "Future Show 2028")
        self.assertEqual(show["hero_image"], "assets/trade-shows/las-vegas-night.webp")
        self.assertIsNone(show["video"])

    def test_same_url_renders_jck_when_active_event_changes(self) -> None:
        config = json.loads(webapp.TRADE_SHOWS_PATH.read_text(encoding="utf-8"))
        config["active_event"] = "jck-2027"

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "trade_shows.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with patch.object(webapp, "TRADE_SHOWS_PATH", config_path):
                response = self.client.get("/trade-shows")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("JCK 2027", body)
        self.assertIn("June 4–7, 2027", body)
        self.assertIn("The Venetian Expo", body)
        self.assertIn("/static/assets/trade-shows/jck-logo-white.png", body)
        self.assertIn("/static/assets/trade-shows/las-vegas-night.webp", body)

    def test_trade_show_styles_keep_touch_targets_and_mobile_layout(self) -> None:
        css = (
            webapp.BASE_DIR / "static" / "css" / "styles" / "trade_shows.css"
        ).read_text(encoding="utf-8")

        self.assertIn("min-height: 48px;", css)
        self.assertIn("@media (max-width: 767.98px)", css)
        self.assertIn(".trade-show-product-grid", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)

    def test_social_image_matches_active_show_and_twitter(self) -> None:
        from domains.trade_show_social import current_image
        config = json.loads(webapp.TRADE_SHOWS_PATH.read_text())
        for key, event in config["events"].items():
            config["active_event"] = key
            with self.subTest(event=key), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "trade_shows.json"
                source.write_text(json.dumps(config))
                with patch.object(webapp, "TRADE_SHOWS_PATH", source):
                    body = self.client.get("/trade-shows").get_data(as_text=True)
                og = re.search(r'<meta property="og:image" content="([^"]+)"', body).group(1)
                twitter = re.search(r'<meta name="twitter:image" content="([^"]+)"', body).group(1)
                self.assertEqual(og, twitter)
                self.assertIn(current_image(key, event, webapp.BASE_DIR / "static"), og)

    def test_stale_social_image_falls_back_without_old_booth_details(self) -> None:
        config = json.loads(webapp.TRADE_SHOWS_PATH.read_text())
        event = config["events"][config["active_event"]]
        event["booth"] = "Booth #999"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "trade_shows.json"
            source.write_text(json.dumps(config))
            with patch.object(webapp, "TRADE_SHOWS_PATH", source):
                body = self.client.get("/trade-shows").get_data(as_text=True)
        og = re.search(r'<meta property="og:image" content="([^"]+)"', body).group(1)
        self.assertIn(event["hero_image"], og)
        self.assertNotIn("trade-shows-jis-fall-v3.jpg", og)
