"""Every shared title stays centered beside its actions at all breakpoints.

Failure inventory: page-specific mobile rules move titles/actions to separate
rows; hidden centering spacers crowd two-control headings; long title/button
labels overlap, clip, or force horizontal scrolling; cart state changes layout.
Unequal action columns shift the title away from the page's horizontal center.
Catalog labels may wrap unnecessarily or lose their wording. Team uses the
compact mobile label; FAQs, About, Contact, member navigation, and the
trade-show collection action retain their full labels.
Excess page padding and Bootstrap row gutters can leave unequal gaps above
the header and below it. A fixed-width title track can wrap short button
labels despite available space beside a short title.
The Team header must expose About Us without wrapping either action or title.
The Reels header must link to Meet the Team. FAQs, About, and Reels must keep
their complete labels on one line, including around narrow layout transitions.
Actions must retain the Team page's standard content-sized styling. Forced
equal widths stretch buttons even when titles remain centered and labels fit.
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
        for populated in (False, True):
            if populated:
                self.add_first_catalog_item_to_cart()
            for path in ("/cart", "/checkout"):
                self.goto(path)
                for width in TITLE_WIDTHS:
                    with self.subTest(width=width, path=path, populated=populated):
                        self.page.set_viewport_size({"width": width, "height": 900})
                        label = f"{'populated-' if populated else ''}{path.strip('/')}-{width}"
                        assert_page_title_row(self, label)

    def test_page_titles_team_and_faq(self):
        self._check_single_line_titles(("/team", "/faqs"))

    def test_page_titles_about_and_contact(self):
        self._check_single_line_titles(("/about", "/contact"))

    def test_page_titles_reels(self):
        self._check_single_line_titles(("/reels",))

    def _check_single_line_titles(self, paths):
        for path in paths:
            self.goto(path)
            self.page.evaluate("document.fonts.ready")
            for width in sorted(set(TITLE_WIDTHS + (364, 365, 375))):
                with self.subTest(width=width, path=path):
                    self.page.set_viewport_size({"width": width, "height": 900})
                    action = self.page.locator(".page-title-action")
                    if path == "/team":
                        expect(action).to_have_text("About Us")
                        expect(action).to_have_attribute("href", "/about")
                    if path == "/reels":
                        expect(action).to_have_text("Meet the Team")
                        expect(action).to_have_attribute("href", "/team")
                    if path in ("/faqs", "/about"):
                        expect(self.page.locator(".page-title-back")).to_have_text("Browse Catalog")
                    if path != "/contact":
                        title = self.page.locator(".page-title-row h1")
                        self.assertTrue(title.evaluate("""e => {
                          return e.getBoundingClientRect().height <=
                            parseFloat(getComputedStyle(e).lineHeight) + 1;
                        }"""), (path, width, title.inner_text()))
                    single_line = self.page.locator(
                        ".page-title-back, .page-title-action"
                    ).evaluate_all("""buttons => buttons.every(e => {
                      const range = document.createRange();
                      range.selectNodeContents(e.querySelector('.catalog-button-label') || e);
                      return range.getBoundingClientRect().height <=
                        parseFloat(getComputedStyle(e).lineHeight) + 1;
                    })""")
                    if path != "/contact" or width >= 360:
                        self.assertTrue(single_line, (path, width, action.inner_text()))
                    geometry = assert_page_title_row(self, f"single-line-{path.strip('/')}-{width}")
                    if width in TITLE_WIDTHS and path in ("/team", "/faqs", "/about", "/contact"):
                        self._assert_catalog_label(path, width, capture=False)
                    if path in ("/team", "/faqs", "/about", "/reels"):
                        for button in (item for item in geometry["items"] if not item["isTitle"]):
                            # Shared max-width may constrain a button, but must never stretch it.
                            self.assertLessEqual(
                                button["box"]["width"],
                                button["textWidth"] + button["horizontalInsets"] + 1,
                                msg=(path, width, button),
                            )
                    if path == "/team" and width == 390:
                        action.click()
                        expect(self.page.locator(".page-title-row h1")).to_have_text("About Us")
                        self.goto(path)
                    if path == "/reels" and width == 390:
                        action.click()
                        expect(self.page.locator(".page-title-row h1")).to_have_text("Meet the Team")
                        self.goto(path)

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

    def _assert_catalog_label(self, path, width, *, capture=True):
        compact_header = path == "/team"
        expected = "Catalog" if compact_header and width < 768 else "Browse Catalog"
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
        if capture:
            artifacts = self._artifact_dir()
            artifacts.mkdir(parents=True, exist_ok=True)
            name = f"catalog-label-{path.strip('/').replace('/', '-')}-{width}"
            self.page.screenshot(path=str(artifacts / f"{name}.png"), animations="disabled")
            (artifacts / f"{name}.html").write_text(self.page.content(), encoding="utf-8")

    def test_member_and_trade_show_catalog_button_labels(self):
        self.goto("/team")
        member_path = self.page.locator(".team-card-link").first.get_attribute("href")
        for path in (member_path, "/trade-shows"):
            self.goto(path)
            self.page.evaluate("document.fonts.ready")
            for width in TITLE_WIDTHS:
                with self.subTest(width=width, path=path):
                    self.page.set_viewport_size({"width": width, "height": 900})
                    self._assert_catalog_label(path, width)
