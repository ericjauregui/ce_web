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

    def test_catalog_picker_and_cta_buttons_are_vertically_centered(self) -> None:
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(180)

        picker_alignment = self.page.evaluate(
            """
            () => {
              const row = document.querySelector('.catalog-explorer-row');
              const summary = row?.querySelector('.catalog-collection-picker__summary');
              if (!row || !summary) return null;
              const rowRect = row.getBoundingClientRect();
              const summaryRect = summary.getBoundingClientRect();
              return {
                centerDelta: Math.abs((rowRect.top + rowRect.height / 2) - (summaryRect.top + summaryRect.height / 2)),
                summaryVisible: summaryRect.width > 0 && summaryRect.height >= 40,
              };
            }
            """
        )
        self.assertIsNotNone(picker_alignment)
        self.assertLessEqual(picker_alignment["centerDelta"], 6)
        self.assertTrue(picker_alignment["summaryVisible"])

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

    def test_mobile_catalog_picker_and_reel_scroll_hint(self) -> None:
        self.page.set_viewport_size({"width": 390, "height": 900})
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(180)

        summary = self.page.locator(".catalog-collection-picker__summary")
        self.assertIn("Choose a collection", summary.inner_text())
        summary.click()
        self.assertIn("All Collections", summary.inner_text())

        picker_state = self.page.evaluate(
            """
            () => {
              const picker = document.querySelector('#catalogCollectionPicker');
              const summary = picker?.querySelector('.catalog-collection-picker__summary');
              const menu = picker?.querySelector('.catalog-collection-picker__menu');
              const options = picker?.querySelector('.catalog-collection-picker__options');
              if (!picker || !summary || !menu || !options) return null;
              picker.open = true;
              const summaryRect = summary.getBoundingClientRect();
              const menuRect = menu.getBoundingClientRect();
              return {
                summaryHeight: summaryRect.height,
                menuLeft: menuRect.left,
                menuRight: menuRect.right,
                columns: getComputedStyle(options).gridTemplateColumns.split(' ').length,
                viewportWidth: window.innerWidth,
              };
            }
            """
        )
        self.assertIsNotNone(picker_state)
        self.assertGreaterEqual(picker_state["summaryHeight"], 40)
        self.assertGreaterEqual(picker_state["menuLeft"], 0)
        self.assertLessEqual(picker_state["menuRight"], picker_state["viewportWidth"])
        self.assertEqual(picker_state["columns"], 2)

        self.page.locator('[data-target="section-hearts"]').click()
        self.assertEqual(
            self.page.locator(".catalog-collection-section:visible").count(),
            1,
        )
        self.assertEqual(
            self.page.locator(".catalog-collection-heading:visible").count(),
            0,
        )

        self.page.locator(".catalog-collection-picker__summary").click()
        self.page.locator('[data-target="all-collections"]').click()
        visible_sections = self.page.locator(".catalog-collection-section:visible").count()
        self.assertGreater(visible_sections, 1)
        self.assertEqual(
            self.page.locator(".catalog-collection-heading:visible").count(),
            visible_sections,
        )

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
