"""Hero-first loading journeys with real browser layout and local media.

Failure cases: early autoplay steals the hero's bandwidth, a failed hero blocks
the catalog, direct collection links stop loading, or initial cart state changes.
Screenshots, rendered HTML, browser events and asset hashes are retained by the
E2E runner. No live orders or email are used.
"""
import hashlib
import json
from urllib.parse import urlsplit

import app as webapp
from tests.e2e.common import BaseE2ETest


class HeroRenderingE2ETests(BaseE2ETest):
    viewport = {"width": 390, "height": 844}

    def test_automatic_reels_wait_for_hero_but_manual_play_is_available(self):
        pending = []
        self.page.route("**/optimized/heroes/**", lambda route: pending.append(route))
        self.goto("/")
        self.page.wait_for_function("typeof window.initializeInlineReelTrack === 'function'")
        self.assertGreater(len(pending), 0)
        self.page.locator("#latestVideosTrack").scroll_into_view_if_needed()
        # Let viewport observers run with the hero still held at the network.
        self.page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        self.assertEqual(self.page.locator("#latestVideosTrack video[src]").count(), 0)
        first = self.page.locator("#latestVideosTrack .inline-reel-card").first
        first.click()
        self.page.wait_for_function("document.querySelector('#latestVideosTrack video[src]')?.readyState >= 2")
        self.assertEqual(first.get_attribute("aria-expanded"), "true")
        for route in pending:
            route.continue_()
        self.page.evaluate("window.catalogHeroReady")
        self.assertEqual(first.get_attribute("aria-expanded"), "true")

    def test_failed_hero_keeps_catalog_and_automatic_reels_usable(self):
        self.page.route("**/optimized/heroes/**", lambda route: route.fulfill(status=404))
        self.goto("/")
        self.page.evaluate("window.catalogHeroReady")
        track = self.page.locator("#latestVideosTrack")
        track.scroll_into_view_if_needed()
        self.page.wait_for_function("document.querySelector('#latestVideosTrack .is-active video')?.readyState >= 2")
        self.page.locator('[data-target="section-hearts"]').first.click()
        target = self.page.locator("#section-hearts")
        image = target.locator("img.product-img").first
        image.scroll_into_view_if_needed()
        self.page.wait_for_function("img => img.complete && img.naturalWidth > 0", arg=image.element_handle())
        card = target.locator(".product-card").first
        card.locator(".add-to-cart-btn").click()
        self.page.wait_for_function("card => card.dataset.qty === '1'", arg=card.element_handle())
        self.assertIn("1 item in order", card.inner_text())

    def test_full_resolution_hero_and_saved_cart_across_breakpoints(self):
        manifest = json.loads((webapp.BASE_DIR / "static/optimized/hero-manifest.json").read_text())
        hero_responses = {}
        self.page.on("response", lambda response: hero_responses.update({response.url: response})
                     if "/optimized/heroes/" in response.url else None)
        self.goto("/")
        self.page.locator(".add-to-cart-btn").first.click()
        self.page.wait_for_function("document.querySelector('.product-card').dataset.qty === '1'")
        evidence = []
        for width in (320, 390, 768, 1280):
            self.page.set_viewport_size({"width": width, "height": 844})
            hero_responses.clear()
            self.goto("/")
            self.page.evaluate("window.catalogHeroReady")
            self.page.evaluate("document.fonts.ready")
            selected = self.page.evaluate("""() => {
                const link = [...document.querySelectorAll('link[rel=preload][as=image]')]
                    .find(link => link.href.includes('hero_bg') && matchMedia(link.media).matches);
                return {url:link.href, background:getComputedStyle(document.querySelector('.hero')).backgroundImage};
            }""")
            entry = next(item for item in manifest.values() if item["path"] in selected["url"])
            self.assertIn(selected["url"].split("/static/")[1], selected["background"])
            dimensions = self.page.evaluate("""async url => {
                const image = new Image(); image.src = url; await image.decode();
                return [image.naturalWidth, image.naturalHeight];
            }""", selected["url"])
            self.assertEqual(dimensions, [entry["width"], entry["height"]])
            # Inspect the delivered response, not a second download that can
            # queue behind a streaming reel on the single-threaded test server.
            image_bytes = hero_responses[selected["url"]].body()
            self.assertEqual(image_bytes, (webapp.BASE_DIR / "static" / entry["path"]).read_bytes())
            first = self.page.locator(".product-card").first
            self.assertEqual(first.get_attribute("data-qty"), "1")
            self.assertIn("is-in-cart", first.get_attribute("class"))
            self.assertEqual(first.locator(".product-qty-input").input_value(), "1")
            self.assertIn("1 item in order", first.locator(".add-to-cart-btn").inner_text())
            self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            self._artifact_dir().mkdir(parents=True, exist_ok=True)
            self.page.locator(".hero").screenshot(path=str(self._artifact_dir() / f"hero-{width}.png"), animations="disabled")
            evidence.append({"width":width, "asset":urlsplit(selected["url"]).path,
                             "dimensions":dimensions, "sha256":hashlib.sha256(image_bytes).hexdigest()})
        (self._artifact_dir() / "hero-assets.json").write_text(json.dumps(evidence, indent=2))
        # Direct navigation must reveal the target even when it starts offscreen.
        self.page.goto("about:blank")
        self.goto("/#section-jewelry-sets")
        card = self.page.locator("#section-jewelry-sets .product-card").first
        card.scroll_into_view_if_needed()
        card.focus()
        card.press("Enter")
        self.assertEqual(card.get_attribute("aria-expanded"), "true")
        image = card.locator("img.product-img")
        self.page.wait_for_function("img => img.complete && img.naturalWidth > 0", arg=image.element_handle())
