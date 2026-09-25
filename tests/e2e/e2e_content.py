from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from xml.etree import ElementTree

import app as webapp
from tests.e2e.common import BaseE2ETest


class ContentJourneysE2ETests(BaseE2ETest):
    def test_shared_brand_logos_use_webp_on_site_pages(self) -> None:
        for width in (390, 1280):
            self.page.set_viewport_size({"width": width, "height": 844})
            for path in ("/", "/about", "/team"):
                self.goto(path)
                logo = self.page.locator(".navbar-brand .brand-logo")
                self.assertIn("ce_logo_shape.webp", logo.get_attribute("src"))
                self.page.wait_for_function(
                    "image => image.complete && image.naturalWidth > 0",
                    arg=logo.element_handle(),
                )
                self.assertIn("ce_logo_shape.webp", self.page.evaluate(
                    "getComputedStyle(document.body, '::before').backgroundImage"
                ))
                self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                if path == "/":
                    hero_logo = self.page.locator(".hero-logo")
                    self.assertIn("ce_logo_full.webp", hero_logo.get_attribute("src"))
                    self.assertIn("ce_logo_full.webp", self.page.locator(
                        'link[rel="preload"][as="image"][href*="ce_logo_full"]'
                    ).get_attribute("href"))
                    self.page.wait_for_function(
                        "image => image.complete && image.naturalWidth > 0",
                        arg=hero_logo.element_handle(),
                    )
                    self.page.wait_for_load_state("load")
                    logo_resources = self.page.evaluate("""() => performance.getEntriesByType('resource')
                        .map(item => item.name).filter(url =>
                            url.includes('ce_logo_shape.') || url.includes('ce_logo_full.'))""")
                    self.assertEqual(sum("ce_logo_shape.webp" in url for url in logo_resources), 1)
                    self.assertEqual(sum("ce_logo_full.webp" in url for url in logo_resources), 1)
                    self.assertFalse(any("ce_logo_shape.png" in url or "ce_logo_full.png" in url for url in logo_resources))
                    self._artifact_dir().mkdir(parents=True, exist_ok=True)
                    self.page.screenshot(
                        path=str(self._artifact_dir() / f"home-{width}.png"),
                        animations="disabled",
                    )

        self.goto("/team")
        self.page.locator(".team-card-link").first.click()
        wordmark = self.page.locator(".dbc-wordmark")
        self.assertIn("ce_logo_full.webp", wordmark.get_attribute("src"))
        self.page.wait_for_function(
            "image => image.complete && image.naturalWidth > 0",
            arg=wordmark.element_handle(),
        )

        self.goto("/trade-shows")
        trade_show_background = self.page.locator(".trade-show-page").evaluate(
            "element => getComputedStyle(element, '::before').backgroundImage"
        )
        self.assertNotIn("ce_logo_shape", trade_show_background)

    def test_team_cards_open_and_download_usable_contacts(self) -> None:
        self.goto("/team")
        cards = self.page.locator(".team-member-card")
        self.assertGreater(cards.count(), 0)

        for index in range(cards.count()):
            self.goto("/team")
            card = self.page.locator(".team-member-card").nth(index)
            name = card.locator(".team-card-link .fw-semibold").inner_text()
            card.locator(".team-card-link").click()
            self.assertIn(name, self.page.locator("#memberName").inner_text())

            portrait = self.page.locator(".dbc-portrait")
            if portrait.count():
                portrait.scroll_into_view_if_needed()
                self.page.wait_for_function(
                    "image => image.complete && image.naturalWidth > 0",
                    arg=portrait.element_handle(),
                )
            qr = self.page.locator(".dbc-qr-frame img")
            qr.scroll_into_view_if_needed()
            self.page.wait_for_function(
                "image => image.complete && image.naturalWidth > 0",
                arg=qr.element_handle(),
            )

            with self.page.expect_download() as download_info:
                self.page.get_by_role("link", name="Save Contact").click()
            vcard = Path(download_info.value.path()).read_text(encoding="utf-8")
            self.assertIn("BEGIN:VCARD", vcard)
            self.assertIn("END:VCARD", vcard)
            self.assertIn(f"FN:{name}", vcard)
            email = self.page.locator('.dbc-contact-email a').get_attribute("href")
            self.assertIn(email.removeprefix("mailto:"), vcard)

            canonical = self.page.locator('link[rel="canonical"]').get_attribute("href")
            self.assertEqual(urlsplit(canonical).path, urlsplit(self.page.url).path)
            social = self.page.locator('meta[property="og:image"]').get_attribute("content")
            self.assertEqual(social, self.page.locator('meta[name="twitter:image"]').get_attribute("content"))
            image = self.page.request.get(f"{self.base_url}{urlsplit(social).path}")
            self.assertEqual(image.status, 200)
            self.assertTrue(image.body().startswith(b"\xff\xd8\xff"))

    def test_trade_show_details_assets_and_calendar_export(self) -> None:
        config = json.loads(webapp.TRADE_SHOWS_PATH.read_text(encoding="utf-8"))
        show = config["events"][config["active_event"]]
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.goto("/trade-shows")
        self.assertIn(show["name"], self.page.locator("h1").inner_text())
        self.assertIn(show["booth"], self.page.locator("#booth-details").inner_text())

        logo = self.page.locator("#booth-details img")
        logo.scroll_into_view_if_needed()
        self.page.wait_for_function(
            "image => image.complete && image.naturalWidth > 0",
            arg=logo.element_handle(),
        )
        products = self.page.locator(".trade-show-product-card")
        self.assertEqual(products.count(), len(show["curated_products"]))
        for index in range(products.count()):
            product = products.nth(index)
            href = product.get_attribute("href")
            self.assertIn("#section-", href)
            image = product.locator("img")
            image.scroll_into_view_if_needed()
            self.page.wait_for_function(
                "image => image.complete && image.naturalWidth > 0",
                arg=image.element_handle(),
            )

        with self.page.expect_download() as download_info:
            self.page.get_by_role("button", name="Add to Calendar").click()
        calendar = Path(download_info.value.path()).read_text(encoding="utf-8")
        self.assertEqual(download_info.value.suggested_filename, "trade-show.ics")
        self.assertIn(f"SUMMARY:California Earrings at {show['name']}", calendar)
        self.assertIn(f"DTSTART;VALUE=DATE:{show['start_date'].replace('-', '')}", calendar)
        exclusive_end = (date.fromisoformat(show["end_date"]) + timedelta(days=1)).strftime("%Y%m%d")
        self.assertIn(f"DTEND;VALUE=DATE:{exclusive_end}", calendar)
        self.assertIn(show["booth"], calendar)

        self.page.evaluate("window.scrollTo(0, document.querySelector('.trade-show-hero').offsetHeight + 150)")
        self.page.wait_for_function("!document.getElementById('showMobileBar').hidden")
        self.assertIn(show["booth"], self.page.locator("#showMobileBar").inner_text())

        social = self.page.locator('meta[property="og:image"]').get_attribute("content")
        self.assertEqual(social, self.page.locator('meta[name="twitter:image"]').get_attribute("content"))
        self.assertEqual(self.page.request.get(f"{self.base_url}{urlsplit(social).path}").status, 200)

    def test_trade_show_event_switch_and_stale_preview_fallback(self) -> None:
        config = json.loads(webapp.TRADE_SHOWS_PATH.read_text(encoding="utf-8"))
        config["active_event"] = "jck-2027"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "trade_shows.json"
            source.write_text(json.dumps(config), encoding="utf-8")
            with patch.object(webapp, "TRADE_SHOWS_PATH", source):
                self.goto("/trade-shows")
                self.assertIn("JCK 2027", self.page.locator("h1").inner_text())
                logo = self.page.locator("#booth-details img")
                self.assertIn("jck-logo-white.png", logo.get_attribute("src"))
                logo.scroll_into_view_if_needed()
                self.page.wait_for_function(
                    "image => image.complete && image.naturalWidth > 0",
                    arg=logo.element_handle(),
                )

                config["events"]["jck-2027"]["booth"] = "Booth #999"
                source.write_text(json.dumps(config), encoding="utf-8")
                self.page.reload(wait_until="domcontentloaded")
                self.assertIn("Booth #999", self.page.locator("#booth-details").inner_text())
                social = self.page.locator('meta[property="og:image"]').get_attribute("content")
                self.assertIn("las-vegas-night.webp", social)
                self.assertEqual(self.page.request.get(f"{self.base_url}{urlsplit(social).path}").status, 200)

    def test_reels_page_renders_playlist_and_plays_a_reel(self) -> None:
        self.goto("/reels")
        self.assertIn("Jewelry Reels", self.page.locator("h1").inner_text())
        cards = self.page.locator("#reelRow .reel-card")
        self.assertGreater(cards.count(), 0)
        self.assertEqual(cards.count(), self.page.locator("#reelRow video").count())
        first = cards.first
        video_url = first.locator("video").get_attribute("data-src")
        self.assertEqual(
            self.page.request.get(f"{self.base_url}{video_url}", headers={"Range": "bytes=0-1023"}).status,
            206,
        )
        first.click()
        self.page.wait_for_function(
            "document.querySelector('#reelRow .reel-card')?.classList.contains('is-active')"
        )
        self.assertEqual(first.get_attribute("aria-expanded"), "true")

    def test_crawl_metadata_and_analytics_on_live_pages(self) -> None:
        with patch.dict("os.environ", {"CLOUDFLARE_WEB_ANALYTICS_TOKEN": "test-site-token"}):
            self.goto("/")
            canonical = self.page.locator('link[rel="canonical"]').get_attribute("href")
            self.assertEqual(urlsplit(canonical).path, "/")
            beacon = self.page.locator('script[src*="cloudflareinsights.com/beacon.min.js"]')
            self.assertEqual(beacon.count(), 1)
            self.assertEqual(json.loads(beacon.get_attribute("data-cf-beacon"))["token"], "test-site-token")
            self.goto("/privacy")
            self.assertIn("Cloudflare Web Analytics", self.page.locator("main").inner_text())
            self.assertEqual(self.page.locator('script[src*="cloudflareinsights.com/beacon.min.js"]').count(), 1)

        with patch.dict("os.environ", {"CLOUDFLARE_WEB_ANALYTICS_TOKEN": ""}):
            self.goto("/")
            self.assertEqual(self.page.locator('script[src*="cloudflareinsights.com/beacon.min.js"]').count(), 0)

        for path in ("/cart", "/checkout"):
            self.goto(path)
            self.assertEqual(self.page.locator('meta[name="robots"]').get_attribute("content"), "noindex,nofollow")

        sitemap = self.page.request.get(f"{self.base_url}/sitemap.xml")
        self.assertEqual(sitemap.status, 200)
        self.assertIn("application/xml", sitemap.headers["content-type"])
        urls = {
            node.text
            for node in ElementTree.fromstring(sitemap.body()).iter()
            if node.tag.endswith("loc")
        }
        for path in ("/", "/team", "/trade-shows", "/reels"):
            self.assertIn(f"{urlsplit(canonical).scheme}://{urlsplit(canonical).netloc}{path}", urls)

        robots = self.page.request.get(f"{self.base_url}/robots.txt")
        self.assertEqual(robots.status, 200)
        self.assertIn("Disallow: /checkout", robots.text())
        self.assertIn("Disallow: /api/", robots.text())
        self.assertIn("/sitemap.xml", robots.text())

        response = self.page.goto(f"{self.base_url}/this-page-does-not-exist")
        self.assertEqual(response.status, 404)
        self.assertEqual(self.page.locator('meta[name="robots"]').get_attribute("content"), "noindex,nofollow")
