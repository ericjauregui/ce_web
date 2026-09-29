"""Viewport-width storefront layouts and accessible collection overflow.

Failure inventory: Bootstrap width caps leave unused side space, card grids or
page sections extend beyond the viewport, collection links are clipped at
tablet widths, and phone users cannot discover or reach off-screen collections.
"""

import re

from playwright.sync_api import expect

from tests.e2e.common import BaseE2ETest


class FullWidthLayoutE2ETests(BaseE2ETest):
    viewport = {"width": 900, "height": 900}

    def setUp(self):
        super().setUp()
        self.page.route(
            re.compile(r'/static/reels/[^?]+\.mp4(?:\?.*)?$', re.I),
            lambda route: route.fulfill(status=204, body=''),
        )

    def test_catalog_and_browse_pages_use_available_width(self):
        for width in (768, 900, 1024, 1440):
            self.page.set_viewport_size({"width": width, "height": 900})
            self.goto('/')
            self.page.wait_for_function(
                "document.querySelector('.home-collection-current .home-collection-option') !== null"
            )
            for selector in ('#catalogCollectionPicker > .container', '.catalog-collection-section > .container'):
                box = self.page.locator(selector).first.bounding_box()
                self.assertLessEqual(abs(box['x']), 1, (width, selector, box))
                self.assertGreaterEqual(box['width'], width - 1, (width, selector, box))
            navigation = self.page.locator('#homeCollectionNavigation')
            track = navigation.locator('.home-collection-track')
            self.assertTrue(navigation.evaluate('''nav => {
              const outer = nav.closest('.container').getBoundingClientRect();
              const inner = nav.getBoundingClientRect();
              const styles = getComputedStyle(nav.closest('.container'));
              return Math.abs(inner.left - outer.left - parseFloat(styles.paddingLeft)) <= 2 &&
                Math.abs(outer.right - parseFloat(styles.paddingRight) - inner.right) <= 2;
            }'''), width)
            self.assertTrue(track.evaluate('track => track.scrollWidth <= track.clientWidth + 1'), width)
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
            self.page.screenshot(path=str(self._artifact_dir() / f'catalog-width-{width}.png'))
            if width == 768:
                self.page.locator('.catalog-collection-section .product-card').first.scroll_into_view_if_needed()
                self.page.screenshot(path=str(self._artifact_dir() / 'catalog-cards-width-768.png'))

        for path, selector in (
            ('/reels', '.reels-page'),
            ('/team', '.team-page'),
            ('/product/101SB', '.product-detail-page'),
            ('/trade-shows', '.trade-show-content'),
            ('/cart', '.cart-page'),
        ):
            self.goto(path)
            box = self.page.locator(selector).first.bounding_box()
            self.assertLessEqual(abs(box['x']), 1, (path, box))
            self.assertGreaterEqual(box['width'], 1439, (path, box))
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 1440, path)
            self.page.screenshot(path=str(self._artifact_dir() / f'{path.strip("/").replace("/", "-")}-width-1440.png'))

    def test_phone_collections_show_and_scroll_to_remaining_links(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.goto('/')
        navigation = self.page.locator('#homeCollectionNavigation')
        track = navigation.locator('.home-collection-track')
        self.page.wait_for_function(
            "document.querySelector('.home-collection-current .home-collection-option') !== null"
        )
        self.assertTrue(track.evaluate('track => track.scrollWidth > track.clientWidth + 1'))
        next_button = navigation.get_by_role('button', name='Scroll collections right')
        expect(next_button).to_be_visible()
        for _ in range(8):
            if not next_button.is_visible():
                break
            next_button.click()
            self.page.wait_for_timeout(180)
        self.assertTrue(track.evaluate('track => track.scrollLeft >= track.scrollWidth - track.clientWidth - 2'))
        expect(track.locator('.home-collection-option').last).to_be_in_viewport()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 390)
        self.page.screenshot(path=str(self._artifact_dir() / 'collections-phone-end.png'))

    def test_pages_have_no_side_clipping_across_viewports(self):
        pages = (
            '/', '/reels', '/team', '/product/101SB', '/trade-shows',
            '/cart', '/checkout', '/about', '/contact', '/faqs', '/privacy',
        )
        for width in (320, 390, 768, 1440):
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in pages:
                self.goto(path)
                dimensions = self.page.evaluate('''() => ({
                    viewport: document.documentElement.clientWidth,
                    document: document.documentElement.scrollWidth,
                    main: document.querySelector('.page-shell > main').getBoundingClientRect().toJSON(),
                })''')
                self.assertLessEqual(dimensions['document'], dimensions['viewport'] + 1, (width, path, dimensions))
                self.assertLessEqual(abs(dimensions['main']['x']), 1, (width, path, dimensions))
                self.assertGreaterEqual(dimensions['main']['width'], width - 1, (width, path, dimensions))
            self.page.screenshot(path=str(self._artifact_dir() / f'page-width-smoke-{width}.png'))
