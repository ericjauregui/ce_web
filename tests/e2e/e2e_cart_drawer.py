"""Quick-order drawer journeys with local synthetic carts.

Failure inventory: stale catalog quantities, duplicate event handlers, lost notes
on close/checkout, failed reads or writes, missing undo after reopening, clipped
mobile rows, a scrolling footer, background scrolling, and escaped keyboard focus.
"""
import re
import app as webapp
from playwright.sync_api import expect
from tests.e2e.common import BaseE2ETest


class CartDrawerE2ETests(BaseE2ETest):
    viewport = {'width': 390, 'height': 844}

    def setUp(self):
        super().setUp()
        self.page.route(re.compile(r'/static/reels/[^?]+\.mp4(?:\?.*)?$', re.I), lambda r: r.fulfill(status=204, body=''))

    def seed(self, code='101SB', qty=2, note='Synthetic drawer note'):
        self.assertEqual(self.context.request.post(f'{self.base_url}/api/cart/add', data={'code': code, 'qty': qty}).status, 200)
        self.assertEqual(self.context.request.post(f'{self.base_url}/api/cart/note', data={'code': code, 'note': note}).status, 200)

    def open_drawer(self):
        self.page.locator('#catalogMiniCart').get_by_role('button', name='Review Order', exact=True).click()
        expect(self.page.locator('#cartDrawer')).to_have_attribute('aria-modal', 'true')
        expect(self.page.locator('#cartDrawer .cart-drawer__body')).to_be_visible()
        expect(self.page.locator('#cartDrawer')).not_to_have_attribute('aria-busy', 'true')
        expect(self.page.locator('#cartDrawer')).to_have_class(re.compile(r'\bshow\b'))

    def close_drawer(self):
        self.page.get_by_role('button', name='Close order').click()
        expect(self.page.locator('#cartDrawer')).not_to_have_attribute('aria-modal', 'true')

    def test_full_order_scrolls_with_fixed_actions_at_mobile_and_desktop_sizes(self):
        products = webapp.load_products()[:18]
        for product in products:
            self.seed(product['code'], 1, '')
        self.goto('/')
        view = self.context.request.get(f'{self.base_url}/api/cart/view')
        self.assertIn('private', view.headers['cache-control'])
        self.assertIn('no-store', view.headers['cache-control'])
        for width in (320, 390, 767, 768, 1280):
            self.page.set_viewport_size({'width': width, 'height': 844})
            self.page.evaluate('window.scrollTo({top: 900, behavior: "instant"})')
            self.page.wait_for_timeout(550)
            self.page.screenshot(path=str(self._artifact_dir() / f'before-drawer-{width}.png'))
            original_scroll = self.page.evaluate('window.scrollY')
            self.open_drawer()
            expect(self.page.locator('#cartTableBody tr')).to_have_count(18)
            footer = self.page.locator('#cartSummaryBar')
            initial = footer.bounding_box()
            self.assertTrue(self.page.locator('#cartDrawer').evaluate('drawer => drawer.scrollWidth <= drawer.clientWidth + 1'))
            self.assertTrue(self.page.locator('#cartTableWrap').evaluate('table => table.scrollWidth <= table.clientWidth + 1'))
            self.assertTrue(self.page.locator('.cart-order-scroll').evaluate('e => e.scrollHeight > e.clientHeight'))
            self.page.locator('.cart-order-scroll').evaluate('e => e.scrollTop = e.scrollHeight')
            self.assertAlmostEqual(footer.bounding_box()['y'], initial['y'], delta=1)
            self.assertLessEqual(initial['y'] + initial['height'], 844)
            expect(self.page.locator('#clearOrderBtn')).to_be_visible()
            expect(footer.get_by_role('link', name='Checkout', exact=True)).to_be_visible()
            self.assertEqual(self.page.evaluate('getComputedStyle(document.body).overflow'), 'hidden')
            self.page.locator('.cart-order-scroll').evaluate('e => e.scrollTop = 0')
            self.page.locator('#clearOrderBtn').click()
            expect(self.page.get_by_role('button', name='Undo clear order')).to_be_in_viewport()
            expect(self.page.locator('#cartTableBody tr.is-removed')).to_have_count(18)
            self.page.get_by_role('button', name='Undo clear order').click()
            expect(self.page.locator('#cartTotalQty')).to_have_text('18')
            self.page.get_by_role('button', name='Close order').focus()
            self.page.keyboard.press('Shift+Tab')
            self.assertTrue(self.page.evaluate('document.querySelector("#cartDrawer").contains(document.activeElement)'))
            self.page.keyboard.press('Tab')
            expect(self.page.get_by_role('button', name='Close order')).to_be_focused()
            self.page.screenshot(path=str(self._artifact_dir() / f'drawer-{width}.png'))
            self.page.keyboard.press('Escape')
            expect(self.page.locator('#cartDrawer')).not_to_have_attribute('aria-modal', 'true')
            expect(self.page.locator('#catalogMiniCart .catalog-mini-cart__submit')).to_be_focused()
            self.assertAlmostEqual(self.page.evaluate('window.scrollY'), original_scroll, delta=1)
        self.open_drawer()
        self.page.mouse.click(20, 350)
        expect(self.page.locator('#cartDrawer')).not_to_have_attribute('aria-modal', 'true')

    def test_edits_save_and_catalog_stays_in_sync_without_duplicate_writes(self):
        self.seed(note='<Synthetic & escaped note>')
        self.goto('/')
        self.open_drawer()
        row = self.page.locator('#cartTableBody tr').first
        expect(row.locator('.item-note-input')).to_have_value('<Synthetic & escaped note>')
        self.page.route('**/api/cart/set', lambda r: r.fulfill(status=503, json={'ok': False}))
        row.locator('.qty-plus').click()
        expect(self.page.locator('#cartDrawer [data-order-feedback]')).to_contain_text('couldn’t save')
        expect(row.locator('.qty-input')).to_have_value('2')
        self.page.unroute('**/api/cart/set')
        row.locator('.qty-plus').click()
        expect(row.locator('.qty-input')).to_have_value('3')
        expect(self.page.locator('.product-card').first.locator('.product-qty-input')).to_have_value('3')
        self.assertEqual(self.context.request.get(f'{self.base_url}/api/cart/count').json()['total_items'], 3)
        row.locator('.qty-input').fill('7')
        row.locator('.qty-input').blur()
        expect(self.page.locator('#cartTotalQty')).to_have_text('7')
        self.page.route('**/api/cart/note', lambda r: r.fulfill(status=503, json={'ok': False}))
        row.locator('.item-note-input').fill('Edited in quick order')
        self.page.get_by_role('button', name='Close order').click()
        expect(self.page.locator('#cartDrawer [data-order-feedback]')).to_contain_text('couldn’t save')
        expect(self.page.locator('#cartDrawer')).to_have_attribute('aria-modal', 'true')
        self.page.unroute('**/api/cart/note')
        self.close_drawer()
        card = self.page.locator('.product-card').first
        card.locator('.qty-adjust-btn[data-delta="1"]').click()
        expect(card.locator('.product-qty-input')).to_have_value('8')
        card.locator('.qty-adjust-btn[data-delta="-1"]').click()
        expect(card.locator('.product-qty-input')).to_have_value('7')
        self.open_drawer()
        expect(self.page.locator('.item-note-input')).to_have_value('Edited in quick order')
        expect(self.page.locator('.qty-input')).to_have_value('7')
        self.page.locator('.item-note-input').fill('Saved before checkout')
        self.page.locator('#cartDrawer').get_by_role('link', name='Checkout', exact=True).click()
        self.page.wait_for_url('**/checkout')
        self.assertIn('Saved before checkout', self.page.locator('.checkout-items-table').inner_text())

    def test_remove_and_clear_undo_survive_drawer_close_and_cart_navigation(self):
        self.seed()
        self.seed('102SB', 3, 'Second synthetic note')
        self.goto('/')
        self.open_drawer()
        self.page.locator('.qty-remove[data-code="101SB"]').click()
        expect(self.page.get_by_role('button', name='Undo removal of 101SB')).to_be_visible()
        expect(self.page.locator('#cartTotalQty')).to_have_text('3')
        self.close_drawer()
        self.open_drawer()
        self.page.get_by_role('button', name='Undo removal of 101SB').click()
        expect(self.page.locator('#cartTotalQty')).to_have_text('5')
        self.page.locator('#clearOrderBtn').click()
        expect(self.page.get_by_role('button', name='Undo clear order')).to_be_visible()
        expect(self.page.locator('#cartTableBody tr.is-removed')).to_have_count(2)
        expect(self.page.locator('.cart-undo-clear .cart-undo-ring-progress')).to_be_visible()
        self.page.get_by_role('button', name='Undo clear order').click()
        expect(self.page.locator('#cartTotalQty')).to_have_text('5')
        self.page.locator('.qty-remove[data-code="101SB"]').click()
        self.close_drawer()
        self.page.locator('#cartLink').click()
        self.page.wait_for_url('**/cart')
        self.page.get_by_role('button', name='Undo removal of 101SB').click()
        expect(self.page.locator('#cartTotalQty')).to_have_text('5')
        expect(self.page.locator('.item-note-input[data-code="101SB"]')).to_have_value('Synthetic drawer note')

    def test_failed_read_retries_and_empty_order_remains_recoverable(self):
        self.seed()
        self.goto('/')
        self.page.route('**/api/cart/view', lambda r: r.fulfill(status=503, json={'ok': False}))
        self.page.locator('#catalogMiniCart .catalog-mini-cart__submit').click()
        expect(self.page.locator('#cartDrawer [data-order-feedback]')).to_contain_text('couldn’t load')
        expect(self.page.get_by_role('button', name='Retry', exact=True)).to_be_visible()
        self.close_drawer()
        self.page.locator('#catalogMiniCart .catalog-mini-cart__submit').click()
        expect(self.page.get_by_role('button', name='Retry', exact=True)).to_be_visible()
        self.page.unroute('**/api/cart/view')
        self.page.get_by_role('button', name='Retry', exact=True).click()
        expect(self.page.locator('.qty-input')).to_have_value('2')
        self.page.clock.install()
        self.page.locator('#clearOrderBtn').click()
        expect(self.page.get_by_role('button', name='Undo clear order')).to_be_visible()
        expect(self.page.locator('.cart-undo-clear .cart-undo-seconds')).to_have_text('30s')
        self.page.clock.fast_forward(32000)
        expect(self.page.locator('#cartEmptyState')).to_be_visible()
        expect(self.page.locator('#cartSummaryBar')).to_be_hidden()
        self.page.screenshot(path=str(self._artifact_dir() / 'drawer-empty.png'))
        self.close_drawer()
        expect(self.page.locator('#cartLink')).to_be_focused()
