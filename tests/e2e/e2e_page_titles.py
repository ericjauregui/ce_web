"""Every shared title stays centered beside its actions at all breakpoints.

Failure inventory: page-specific mobile rules move titles/actions to separate
rows; hidden centering spacers crowd two-control headings; long title/button
labels overlap, clip, or force horizontal scrolling; cart state changes layout.
Unequal action columns shift the title away from the page's horizontal center.
Catalog labels may wrap on phones or lose their desktop wording. The compact
mobile label belongs to page headers; member navigation and the trade-show
collection action retain their full labels.
"""

import re

from playwright.sync_api import expect

from tests.e2e.common import BaseE2ETest
from tests.e2e.page_title import TITLE_WIDTHS, assert_page_title_row


class PageTitleE2ETests(BaseE2ETest):
    def setUp(self):
        super().setUp()
        self.page.route(
            re.compile(r"/static/reels/[^?]+\.mp4(?:\?.*)?$", re.I),
            lambda route: route.fulfill(status=204, body=""),
        )

    def test_all_page_titles_and_actions_share_a_row(self):
        for width in TITLE_WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in ("/team", "/faqs", "/about", "/contact", "/reels", "/cart", "/checkout"):
                with self.subTest(width=width, path=path):
                    self.goto(path)
                    assert_page_title_row(self, f"{path.strip('/')}-{width}")

    def test_populated_cart_and_checkout_titles_share_a_row(self):
        self.add_first_catalog_item_to_cart()
        for width in TITLE_WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in ("/cart", "/checkout"):
                with self.subTest(width=width, path=path):
                    self.goto(path)
                    assert_page_title_row(self, f"populated-{path.strip('/')}-{width}")

    def test_catalog_buttons_use_one_line_mobile_label_and_full_desktop_label(self):
        self.goto("/team")
        member_path = self.page.locator(".team-card-link").first.get_attribute("href")
        paths = ("/team", "/faqs", "/about", "/contact", member_path, "/trade-shows")
        for width in TITLE_WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in paths:
                with self.subTest(width=width, path=path):
                    compact_header = path in ("/team", "/faqs", "/about", "/contact")
                    expected = "Catalog" if compact_header and width < 768 else "Browse Catalog"
                    self.goto(path)
                    self.page.evaluate("document.fonts.ready")
                    button = self.page.locator("a.page-back-btn").filter(has_text="Catalog")
                    expect(button).to_be_visible()
                    self.assertEqual(" ".join(button.inner_text().split()), expected)
                    self.assertEqual(self.page.get_by_role("link", name=expected, exact=True).count(), 1)
                    self.assertTrue(button.evaluate("""e => {
                      const range = document.createRange();
                      range.selectNodeContents(e.querySelector('.catalog-button-label') || e);
                      const box = range.getBoundingClientRect();
                      const parent = e.getBoundingClientRect();
                      const lineHeight = parseFloat(getComputedStyle(e).lineHeight);
                      return box.height <= lineHeight + 1 &&
                        box.left >= parent.left && box.right <= parent.right;
                    }"""), (width, path))
                    artifacts = self._artifact_dir()
                    artifacts.mkdir(parents=True, exist_ok=True)
                    name = f"catalog-label-{path.strip('/').replace('/', '-')}-{width}"
                    self.page.screenshot(path=str(artifacts / f"{name}.png"), animations="disabled")
                    (artifacts / f"{name}.html").write_text(self.page.content(), encoding="utf-8")
