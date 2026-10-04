"""Viewport-width storefront layouts and accessible collection overflow.

Failure inventory: Bootstrap width caps leave unused side space, card grids or
page sections extend beyond the viewport, collection links are clipped at
tablet widths, and phone users cannot discover or reach off-screen collections.
"""

import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, expect

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
        for width in (768, 900, 1024, 1440, 1695):
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
              const contentLeft = outer.left + parseFloat(styles.paddingLeft);
              const contentRight = outer.right - parseFloat(styles.paddingRight);
              return inner.left >= contentLeft - 2 && inner.right <= contentRight + 2 &&
                Math.abs((inner.left + inner.right) - (contentLeft + contentRight)) <= 4;
            }'''), width)
            self.assertTrue(track.evaluate('track => track.scrollWidth <= track.clientWidth + 1'), width)
            if width >= 1024:
                gaps = track.evaluate('''track => {
                  const items = [...track.querySelectorAll('.home-collection-option')];
                  return items.slice(1).map((item, index) =>
                    item.getBoundingClientRect().left - items[index].getBoundingClientRect().right);
                }''')
                self.assertTrue(gaps, width)
                self.assertLessEqual(max(gaps), 24, (width, gaps))
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
            self.page.screenshot(path=str(self._artifact_dir() / f'catalog-width-{width}.png'))
            if width == 1695:
                navigation.evaluate('''nav => {
                  const navbar = document.querySelector('.navbar');
                  window.scrollTo({
                    top: nav.getBoundingClientRect().top + scrollY - navbar.getBoundingClientRect().height,
                    behavior: 'instant',
                  });
                }''')
                self.page.screenshot(path=str(self._artifact_dir() / 'catalog-collections-centered-1695.png'))
            if width == 768:
                self.page.locator('.catalog-collection-section .product-card').first.scroll_into_view_if_needed()
                self.page.screenshot(path=str(self._artifact_dir() / 'catalog-cards-width-768.png'))

        self.page.set_viewport_size({"width": 1440, "height": 900})
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
            if track.evaluate('track => track.scrollLeft >= track.scrollWidth - track.clientWidth - 2'):
                break
            try:
                next_button.click(timeout=2000)
            except PlaywrightTimeoutError:
                # A final smooth-scroll frame can reach the end after the
                # check above, disabling the arrow while click retries.
                # Accept only that completed destination, never a stuck control.
                if next_button.is_enabled() or not track.evaluate(
                    'track => track.scrollLeft >= track.scrollWidth - track.clientWidth - 2'
                ):
                    raise
                break
            # Wait for smooth scrolling to settle before checking/clicking again.
            # A fixed delay can race the arrow becoming disabled at the end.
            track.evaluate('''track => new Promise((resolve, reject) => {
              let last = track.scrollLeft;
              let settledSince = performance.now();
              const deadline = setTimeout(() => reject(new Error('Collection scroll did not settle')), 3000);
              function check() {
                const now = performance.now();
                if (Math.abs(track.scrollLeft - last) > 0.1) {
                  last = track.scrollLeft;
                  settledSince = now;
                }
                if (now - settledSince >= 150) {
                  clearTimeout(deadline);
                  resolve();
                } else {
                  setTimeout(check, 25);
                }
              }
              setTimeout(check, 25);
            })''')
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
