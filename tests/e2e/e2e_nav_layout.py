from __future__ import annotations

from tests.e2e.common import BaseE2ETest


class NavLayoutE2ETests(BaseE2ETest):
    browser_name = "chromium"

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
        self.assertFalse(navigation.is_visible())
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
