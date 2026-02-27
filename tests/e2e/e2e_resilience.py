from __future__ import annotations

from tests.e2e.common import BaseE2ETest


class WebKitResilienceE2ETests(BaseE2ETest):
    browser_name = "webkit"
    viewport = {"width": 390, "height": 844}

    @staticmethod
    def _is_known_third_party_noise(error_message: str) -> bool:
        normalized = error_message.lower()
        return "tiktok.com" in normalized and "accessing a frame" in normalized

    def test_rapid_resize_and_scroll_keeps_nav_search_stable(self) -> None:
        page_errors: list[str] = []
        self.page.on("pageerror", lambda error: page_errors.append(str(error)))

        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")

        sizes = [
            {"width": 390, "height": 844},
            {"width": 430, "height": 932},
            {"width": 375, "height": 812},
            {"width": 414, "height": 896},
            {"width": 390, "height": 844},
        ]

        for size in sizes * 2:
            self.page.set_viewport_size(size)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(60)
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(60)

        self.page.locator(".nav-search-trigger").click()
        self.page.wait_for_selector(".nav-search.is-open .nav-search-input", state="visible")

        trigger_rect = self.page.locator(".nav-search-trigger").bounding_box()
        nav_rect = self.page.locator("nav.navbar.fixed-top").bounding_box()

        self.assertIsNotNone(trigger_rect)
        self.assertIsNotNone(nav_rect)

        trigger_center = trigger_rect["y"] + (trigger_rect["height"] / 2)
        nav_center = nav_rect["y"] + (nav_rect["height"] / 2)
        self.assertLessEqual(abs(trigger_center - nav_center), 8)
        actionable_errors = [
            message for message in page_errors
            if not self._is_known_third_party_noise(message)
        ]
        self.assertEqual(actionable_errors, [])

    def test_catalog_images_use_native_lazy_loading_hint(self) -> None:
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")

        lazy_count = self.page.locator("img.product-img[loading='lazy'][decoding='async']").count()
        total_count = self.page.locator("img.product-img").count()

        self.assertGreater(total_count, 0)
        self.assertEqual(lazy_count, total_count)
