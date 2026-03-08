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

    def test_chips_and_cta_buttons_are_vertically_centered(self) -> None:
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")

        chip_alignment = self.page.evaluate(
            """
            () => {
          const cats = document.querySelector('.section-header-cats');
          const scrollRail = document.querySelector('.section-header-cats-scroll');
          const chip = scrollRail?.querySelector('.chip');
          if (!cats || !scrollRail || !chip) return null;

          const catsRect = cats.getBoundingClientRect();
          const scrollRailRect = scrollRail.getBoundingClientRect();
          const chipRect = chip.getBoundingClientRect();
          const centerDelta = Math.abs((catsRect.top + catsRect.height / 2) - (chipRect.top + chipRect.height / 2));
          const railCenterDelta = Math.abs((catsRect.left + catsRect.width / 2) - (scrollRailRect.left + scrollRailRect.width / 2));
          const firstChipVisible = chipRect.left >= scrollRailRect.left - 1;
          return { centerDelta, railCenterDelta, firstChipVisible, scrollLeft: scrollRail.scrollLeft };
            }
            """
        )
        self.assertIsNotNone(chip_alignment)
        self.assertLessEqual(chip_alignment["centerDelta"], 6)
        self.assertLessEqual(chip_alignment["railCenterDelta"], 2)
        self.assertTrue(chip_alignment["firstChipVisible"])
        self.assertEqual(chip_alignment["scrollLeft"], 0)

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

    def test_horizontal_scroll_rows_show_right_hint_until_scrolled_to_end(self) -> None:
        self.page.set_viewport_size({"width": 390, "height": 900})
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")

        chip_state = self.page.evaluate(
            """
            () => {
              const shell = document.querySelector('.section-header-cats.scroll-cue-shell');
              const track = shell?.querySelector('.scroll-cue-track');
              const lastChip = track?.querySelector('.chip:last-of-type');
              if (!shell || !track || !lastChip) return null;

              const maxScrollLeft = Math.max(0, track.scrollWidth - track.clientWidth);
              const before = {
                maxScrollLeft,
                isOverflowing: shell.classList.contains('is-overflowing'),
                canScrollRight: shell.classList.contains('can-scroll-right'),
              };

              track.scrollLeft = maxScrollLeft;
              track.dispatchEvent(new Event('scroll'));

              const trackRect = track.getBoundingClientRect();
              const lastChipRect = lastChip.getBoundingClientRect();
              const lastChipVisibleAtEnd = lastChipRect.right <= trackRect.right + 1;

              return {
                before,
                after: {
                  isOverflowing: shell.classList.contains('is-overflowing'),
                  canScrollRight: shell.classList.contains('can-scroll-right'),
                  lastChipVisibleAtEnd,
                },
              };
            }
            """
        )
        self.assertIsNotNone(chip_state)
        self.assertGreater(chip_state["before"]["maxScrollLeft"], 0)
        self.assertTrue(chip_state["before"]["isOverflowing"])
        self.assertTrue(chip_state["before"]["canScrollRight"])
        self.assertTrue(chip_state["after"]["isOverflowing"])
        self.assertFalse(chip_state["after"]["canScrollRight"])
        self.assertTrue(chip_state["after"]["lastChipVisibleAtEnd"])

        reel_state = self.page.evaluate(
            """
            () => {
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
        self.assertTrue(reel_state["before"]["isOverflowing"])
        self.assertTrue(reel_state["before"]["canScrollRight"])
        self.assertTrue(reel_state["after"]["isOverflowing"])
        self.assertFalse(reel_state["after"]["canScrollRight"])
