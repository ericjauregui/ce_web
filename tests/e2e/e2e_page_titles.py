"""Every shared title stays centered beside its actions at all breakpoints.

Failure inventory: page-specific mobile rules move titles/actions to separate
rows; hidden centering spacers crowd two-control headings; long title/button
labels overlap, clip, or force horizontal scrolling; cart state changes layout.
Unequal action columns shift the title away from the page's horizontal center.
Catalog labels may wrap unnecessarily or lose their desktop wording. Team,
FAQs, and About use the compact mobile label; Contact, member navigation,
and the trade-show collection action retain their full labels.
Excess page padding and Bootstrap row gutters can leave unequal gaps above
the header and below it. A fixed-width title track can wrap short button
labels despite available space beside a short title.
The Team header must expose About Us without wrapping either action or title.
"""

import re

from playwright.sync_api import expect

from tests.e2e.common import BaseE2ETest
from tests.e2e.page_title import TITLE_WIDTHS, assert_page_title_row, assert_page_top_gap


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

    def test_page_titles_leave_room_for_single_line_actions(self):
        for width in TITLE_WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in ("/team", "/faqs", "/about", "/contact"):
                with self.subTest(width=width, path=path):
                    self.goto(path)
                    self.page.evaluate("document.fonts.ready")
                    action = self.page.locator(".page-title-action")
                    if path == "/team":
                        expect(action).to_have_text("About Us")
                        expect(action).to_have_attribute("href", "/about")
                        title = self.page.locator(".page-title-row h1")
                        self.assertTrue(title.evaluate("""e => {
                          return e.getBoundingClientRect().height <=
                            parseFloat(getComputedStyle(e).lineHeight) + 1;
                        }"""), (path, width, title.inner_text()))
                    single_line = action.evaluate("""e => {
                      const range = document.createRange();
                      range.selectNodeContents(e);
                      return range.getBoundingClientRect().height <=
                        parseFloat(getComputedStyle(e).lineHeight) + 1;
                    }""")
                    if path != "/contact" or width >= 360:
                        self.assertTrue(single_line, (path, width, action.inner_text()))
                    assert_page_title_row(self, f"single-line-{path.strip('/')}-{width}")
                    if path == "/team" and width == 390:
                        action.click()
                        expect(self.page.locator(".page-title-row h1")).to_have_text("About Us")

    def test_other_pages_have_compact_top_spacing_and_heroes_stay_flush(self):
        self.goto("/team")
        member_path = self.page.locator(".team-card-link").first.get_attribute("href")
        pages = (
            ("/privacy", "main > section > h1", 24),
            (f"/product/{self.valid_code}", ".product-detail-image-card", 24),
            ("/missing-page", ".not-found-shell", 24),
            (member_path, ".dbc-page-links", 24),
            ("/connect", ".connect-header", 24),
            ("/", "header.hero", 0),
            ("/trade-shows", ".trade-show-page", 0),
        )
        for width in (320, 390, 768, 1280):
            self.page.set_viewport_size({"width": width, "height": 900})
            for path, selector, gap in pages:
                with self.subTest(width=width, path=path):
                    if path == "/missing-page":
                        response = self.page.goto(self.base_url + path, wait_until="domcontentloaded")
                        self.assertEqual(response.status, 404)
                    else:
                        self.goto(path)
                    name = f"top-gap-{path.strip('/').replace('/', '-') or 'home'}-{width}"
                    assert_page_top_gap(self, selector, name, gap)
                    if path == member_path:
                        bottom_gap = self.page.evaluate("""() =>
                          document.querySelector('.dbc-profile').getBoundingClientRect().top -
                          document.querySelector('.dbc-page-links').getBoundingClientRect().bottom""")
                        self.assertAlmostEqual(bottom_gap, gap, delta=1)

    def test_catalog_buttons_use_one_line_mobile_label_and_full_desktop_label(self):
        self.goto("/team")
        member_path = self.page.locator(".team-card-link").first.get_attribute("href")
        paths = ("/team", "/faqs", "/about", "/contact", member_path, "/trade-shows")
        for width in TITLE_WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in paths:
                with self.subTest(width=width, path=path):
                    compact_header = path in ("/team", "/faqs", "/about")
                    expected = "Catalog" if compact_header and width < 768 else "Browse Catalog"
                    self.goto(path)
                    self.page.evaluate("document.fonts.ready")
                    button = self.page.locator("a.page-back-btn").filter(has_text="Catalog")
                    expect(button).to_be_visible()
                    self.assertEqual(" ".join(button.inner_text().split()), expected)
                    self.assertEqual(self.page.get_by_role("link", name=expected, exact=True).count(), 1)
                    self.assertTrue(button.evaluate("""(e, singleLine) => {
                      const range = document.createRange();
                      range.selectNodeContents(e.querySelector('.catalog-button-label') || e);
                      const box = range.getBoundingClientRect();
                      const parent = e.getBoundingClientRect();
                      const lineHeight = parseFloat(getComputedStyle(e).lineHeight);
                      return (!singleLine || box.height <= lineHeight + 1) &&
                        box.left >= parent.left && box.right <= parent.right;
                    }""", path != "/contact" or width >= 360), (width, path))
                    artifacts = self._artifact_dir()
                    artifacts.mkdir(parents=True, exist_ok=True)
                    name = f"catalog-label-{path.strip('/').replace('/', '-')}-{width}"
                    self.page.screenshot(path=str(artifacts / f"{name}.png"), animations="disabled")
                    (artifacts / f"{name}.html").write_text(self.page.content(), encoding="utf-8")
