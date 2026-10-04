from __future__ import annotations

import json
import re

from playwright.sync_api import expect
from tests.e2e.common import BaseE2ETest


class NavLayoutE2ETests(BaseE2ETest):
    browser_name = "chromium"

    def test_compact_navbar_and_offsets_across_site_pages(self) -> None:
        # Catch page overrides, clipped controls, stale sticky offsets, and
        # menu expansion moving the page beneath the fixed navigation row.
        self.page.route(
            re.compile(r"/static/reels/[^?]+\.mp4(?:\?.*)?$", re.I),
            lambda route: route.fulfill(status=204, body=""),
        )
        self.goto("/team")
        member_path = self.page.locator(".team-card-link").first.get_attribute("href")
        paths = ("/", "/?q=stud", "/team", member_path, "/about", "/contact",
                 "/faqs", "/reels", "/trade-shows", "/connect", "/privacy",
                 f"/product/{self.valid_code}", "/cart", "/checkout", "/missing-page")
        records = []
        root = self._artifact_dir()
        root.mkdir(parents=True, exist_ok=True)
        for width in (320, 390, 767, 768, 1280, 1692):
            self.page.set_viewport_size({"width": width, "height": 900})
            for index, path in enumerate(paths):
                with self.subTest(width=width, path=path):
                    self.page.goto(f"{self.base_url}{path}", wait_until="load")
                    self.page.evaluate("document.fonts.ready")
                    self.page.wait_for_function("""() => Math.abs(
                        parseFloat(getComputedStyle(document.documentElement)
                            .getPropertyValue('--nav-actual-height')) -
                        document.querySelector('.navbar').getBoundingClientRect().height
                    ) <= 1""")
                    geometry = self.page.evaluate("""() => {
                      const nav = document.querySelector('.navbar').getBoundingClientRect();
                      const rect = e => {
                        const r = e.getBoundingClientRect();
                        return {top: r.top, bottom: r.bottom, left: r.left,
                                right: r.right, height: r.height};
                      };
                      return {
                        height: nav.height,
                        fallback: parseFloat(getComputedStyle(document.querySelector('main'))
                          .paddingTop),
                        overflow: document.documentElement.scrollWidth > innerWidth,
                        controls: Array.from(document.querySelectorAll(
                          '.brand-lockup, .nav-search-trigger, .nav-actions')).map(rect),
                      };
                    }""")
                    records.append({"width": width, "path": path, **geometry})
                    (root / "navbar-geometry.json").write_text(json.dumps(records, indent=2))
                    self.assertGreaterEqual(geometry["height"], 52)
                    self.assertLessEqual(geometry["height"], 58)
                    self.assertAlmostEqual(geometry["fallback"], geometry["height"], delta=1)
                    self.assertFalse(geometry["overflow"])
                    controls = geometry["controls"]
                    self.assertGreaterEqual(controls[0]["height"], 44)
                    for control in controls:
                        self.assertGreaterEqual(control["top"], 0)
                        self.assertLessEqual(control["bottom"], geometry["height"])
                        self.assertGreaterEqual(control["left"], 0)
                        self.assertLessEqual(control["right"], width)
                        self.assertLessEqual(abs((control["top"] + control["bottom"]) / 2
                                                 - geometry["height"] / 2), 1)
                    self.assertLessEqual(controls[0]["right"], controls[1]["left"])
                    self.assertLessEqual(controls[1]["right"], controls[2]["left"])
                    if path in ("/", "/connect"):
                        toggle = self.page.get_by_role("button", name="Toggle navigation")
                        before_y = self.page.evaluate("scrollY")
                        toggle.click()
                        expect(self.page.locator("#nav")).to_be_visible()
                        self.page.wait_for_function("!document.querySelector('#nav').classList.contains('collapsing')")
                        self.assertAlmostEqual(self.page.locator(".navbar").bounding_box()["height"],
                                               geometry["height"], delta=1)
                        self.assertAlmostEqual(self.page.evaluate("scrollY"), before_y, delta=1)
                        self.assertGreaterEqual(self.page.locator("#nav").bounding_box()["y"],
                                                max(control["bottom"] for control in controls) - 1)
                        self.page.screenshot(path=str(root / f"menu-{index}-{width}.png"))
                        toggle.click()
                        expect(self.page.locator("#nav")).to_be_hidden()
                        self.page.locator(".nav-search-trigger").click()
                        expect(self.page.locator(".nav-search-input")).to_be_focused()
                        # Search restores input focus on its opening frame.
                        # Finish that frame before testing Escape focus return.
                        self.page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                        self.page.keyboard.press("Escape")
                        expect(self.page.locator(".nav-search-trigger")).to_be_focused()
                    if width in (390, 1692):
                        self.page.screenshot(path=str(root / f"page-{index}-{width}.png"))

    def test_navbar_resize_keeps_home_sticky_collections_flush(self) -> None:
        self.page.route(
            re.compile(r"/static/reels/[^?]+\.mp4(?:\?.*)?$", re.I),
            lambda route: route.fulfill(status=204, body=""),
        )
        self.goto("/", wait_until="load")
        self.page.evaluate("document.fonts.ready")
        root = self._artifact_dir()
        root.mkdir(parents=True, exist_ok=True)
        for width in (1692, 1280, 768, 767, 390, 320, 1692):
            self.page.set_viewport_size({"width": width, "height": 900})
            self.page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            self.page.evaluate("scrollTo({top: 8000, behavior: 'instant'})")
            self.page.wait_for_function("""() => Math.abs(
                document.querySelector('.home-collections').getBoundingClientRect().top -
                document.querySelector('.navbar').getBoundingClientRect().bottom
            ) <= 1""")
            self.page.wait_for_timeout(150)
            self.assertEqual(self.page.evaluate("innerWidth"), width)
            self.assertAlmostEqual(self.page.locator(".navbar").bounding_box()["y"], 0, delta=1)
            self.page.screenshot(path=str(root / f"sticky-{width}.png"))
            self.page.get_by_role("link", name="Jump to top", exact=True).click()
            self.page.wait_for_function("scrollY <= 2")
            expect(self.page.locator(".home-collections-toggle")).to_have_attribute("aria-expanded", "true")

    def test_nav_search_stays_centered_and_expands(self) -> None:
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")

        nav_rect = self.page.locator("nav.navbar.fixed-top").bounding_box()
        trigger_rect = self.page.locator(".nav-search-trigger").bounding_box()

        self.assertIsNotNone(nav_rect)
        self.assertIsNotNone(trigger_rect)

        nav_center_y = nav_rect["y"] + (nav_rect["height"] / 2)
        trigger_center_y = trigger_rect["y"] + (trigger_rect["height"] / 2)
        self.assertLessEqual(abs(nav_center_y - trigger_center_y), 5)

        self.page.locator(".nav-search-trigger").click()
        self.page.wait_for_selector(".nav-search.is-open .nav-search-form", state="visible")

        input_box = self.page.locator("#navSearchForm .nav-search-input").bounding_box()
        self.assertIsNotNone(input_box)
        self.assertGreaterEqual(input_box["width"], 300)

        self.page.evaluate("window.scrollTo(0, 1200)")
        self.page.wait_for_timeout(120)

        nav_rect_after = self.page.locator("nav.navbar.fixed-top").bounding_box()
        trigger_rect_after = self.page.locator(".nav-search-trigger").bounding_box()

        self.assertIsNotNone(nav_rect_after)
        self.assertIsNotNone(trigger_rect_after)

        trigger_center_after = trigger_rect_after["y"] + (trigger_rect_after["height"] / 2)
        nav_center_after = nav_rect_after["y"] + (nav_rect_after["height"] / 2)
        self.assertLessEqual(abs(nav_center_after - trigger_center_after), 6)

    def test_collection_controls_and_cta_buttons_are_vertically_centered(self) -> None:
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(180)

        collection_alignment = self.page.evaluate(
            """
            () => {
              const row = document.querySelector('.home-collections .home-row-heading');
              const toggle = row?.querySelector('.home-collections-toggle');
              if (!row || !toggle) return null;
              const rowRect = row.getBoundingClientRect();
              const toggleRect = toggle.getBoundingClientRect();
              return {
                centerDelta: Math.abs((rowRect.top + rowRect.height / 2) - (toggleRect.top + toggleRect.height / 2)),
                toggleVisible: toggleRect.width >= 30 && toggleRect.height >= 30,
              };
            }
            """
        )
        self.assertIsNotNone(collection_alignment)
        self.assertLessEqual(collection_alignment["centerDelta"], 8)
        self.assertTrue(collection_alignment["toggleVisible"])

        cta_styles = self.page.evaluate(
            """
            () => {
              const button = document.querySelector('.hero-action-btn');
              if (!button) return null;
              const style = window.getComputedStyle(button);
              return {
                display: style.display,
                alignItems: style.alignItems,
                justifyContent: style.justifyContent,
              };
            }
            """
        )
        self.assertIsNotNone(cta_styles)
        self.assertIn(cta_styles["display"], {"inline-flex", "flex"})
        self.assertEqual(cta_styles["alignItems"], "center")
        self.assertEqual(cta_styles["justifyContent"], "center")

    def test_mobile_collection_navigation_and_reel_scroll_hint(self) -> None:
        self.page.set_viewport_size({"width": 390, "height": 900})
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(180)

        toggle = self.page.locator(".home-collections-toggle")
        navigation = self.page.locator("#homeCollectionNavigation")
        self.assertTrue(navigation.is_visible())
        self.assertGreater(self.page.locator(".home-collection-option").count(), 1)
        toggle.click()
        self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
        expect(navigation).to_be_hidden()
        toggle.click()
        self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
        self.assertTrue(navigation.is_visible())

        self.page.locator('[data-target="section-hearts"]').click()
        self.page.wait_for_function("() => location.hash === '#section-hearts'")
        self.page.wait_for_function("() => window.scrollY > 0")
        self.assertGreater(self.page.locator(".catalog-collection-section").count(), 1)

        reel_state = self.page.evaluate(
            """
            async () => {
              const shell = document.querySelector('.latest-videos-shell.scroll-cue-shell');
              const track = shell?.querySelector('.scroll-cue-track');
              if (!shell || !track) return null;

              const maxScrollLeft = Math.max(0, track.scrollWidth - track.clientWidth);
              const before = {
                maxScrollLeft,
                isOverflowing: shell.classList.contains('is-overflowing'),
                canScrollRight: shell.classList.contains('can-scroll-right'),
              };

              track.scrollLeft = maxScrollLeft;
              track.dispatchEvent(new Event('scroll'));
              await new Promise((resolve) => requestAnimationFrame(resolve));

              return {
                before,
                after: {
                  isOverflowing: shell.classList.contains('is-overflowing'),
                  canScrollRight: shell.classList.contains('can-scroll-right'),
                },
              };
            }
            """
        )
        self.assertIsNotNone(reel_state)
        self.assertGreater(reel_state["before"]["maxScrollLeft"], 0)
        self.assertTrue(reel_state["before"]["canScrollRight"])
        self.assertFalse(reel_state["after"]["canScrollRight"])
