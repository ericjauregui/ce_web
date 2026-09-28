"""Undo failure inventory: lost notes, duplicate restores, overwritten edits,
expired/tampered/cross-session tokens, failed writes, refresh loss, inaccessible
or clipped actions, and deleting the last item. Exercised through local browsers.
"""
import time
from itsdangerous import URLSafeTimedSerializer
import app as webapp
from unittest.mock import patch
from playwright.sync_api import expect
from tests.e2e.common import BaseE2ETest


class CartUndoE2ETests(BaseE2ETest):
    viewport = {'width': 390, 'height': 900}

    def seed(self, code='101SB', qty=2, note='Synthetic item note'):
        result = self.context.request.post(f'{self.base_url}/api/cart/add', data={'code': code, 'qty': qty})
        self.assertEqual(result.status, 200)
        self.assertEqual(self.context.request.post(f'{self.base_url}/api/cart/note', data={'code': code, 'note': note}).status, 200)

    def test_item_undo_preserves_quantity_note_and_compact_layout(self):
        self.seed()
        self.goto('/cart')
        self.page.locator('.qty-remove').click()
        expect(self.page.locator('.cart-undo-item')).to_be_visible()
        self.assertRegex(self.page.locator('.cart-undo-timer').inner_text(), r'^\d{1,2}s$')
        self.assertEqual(self.context.request.get(f'{self.base_url}/api/cart/count').json()['total_items'], 0)
        self.page.reload()
        expect(self.page.locator('.cart-undo-item')).to_be_visible()
        for width in (320, 390, 767, 768, 1280):
            self.page.set_viewport_size({'width': width, 'height': 900})
            expect(self.page.get_by_role('button', name='Undo removal of 101SB')).to_be_visible()
            self.assertTrue(self.page.locator('#cartTableWrap').evaluate('e => e.scrollWidth <= e.clientWidth + 1'))
            badge = self.page.locator('.cart-product-code-link')
            self.assertLessEqual(badge.evaluate('e => parseFloat(getComputedStyle(e).borderRadius)'), 8)
        self.page.get_by_role('button', name='Undo removal of 101SB').click()
        expect(self.page.locator('.qty-input')).to_have_value('2')
        expect(self.page.locator('.item-note-input')).to_have_value('Synthetic item note')
        expect(self.page.locator('.cart-undo-item')).to_have_count(0)
        self.assertEqual(self.context.request.get(f'{self.base_url}/api/cart/count').json()['total_items'], 2)

    def test_clear_undo_survives_refresh_and_preserves_newer_edits(self):
        self.seed()
        self.seed('102SB', 3, 'Second note')
        self.goto('/cart')
        with self.page.expect_response('**/api/cart/clear') as response:
            self.page.locator('#clearOrderBtn').click()
        token = response.value.json()['undo_token']
        expect(self.page.locator('.cart-undo-clear')).to_be_visible()
        expect(self.page.locator('.cart-undo-clear .cart-undo-ring-progress')).to_be_visible()
        expect(self.page.locator('#cartTableBody tr.is-removed')).to_have_count(2)
        self.seed('101SB', 7, 'Newer note')
        self.page.reload()
        expect(self.page.locator('.cart-undo-clear')).to_be_visible()
        self.page.get_by_role('button', name='Undo clear order').click()
        expect(self.page.locator('.qty-control[data-code="101SB"] input')).to_have_value('7')
        expect(self.page.locator('.qty-control[data-code="102SB"] input')).to_have_value('3')
        expect(self.page.locator('.item-note-input[data-code="101SB"]')).to_have_value('Newer note')
        expect(self.page.locator('.item-note-input[data-code="102SB"]')).to_have_value('Second note')
        replay = self.context.request.post(f'{self.base_url}/api/cart/undo', data={'token': token})
        self.assertEqual(replay.status, 200)
        self.assertEqual(replay.json()['total_items'], 10)
        other = self._browser.new_context()
        try:
            self.assertEqual(other.request.post(f'{self.base_url}/api/cart/undo', data={'token': token}).status, 403)
        finally:
            other.close()
        self.assertEqual(self.context.request.post(f'{self.base_url}/api/cart/undo', data={'token': token + 'broken'}).status, 400)

    def test_failed_remove_and_failed_undo_recover_without_losing_notes(self):
        self.seed()
        self.goto('/cart')
        self.page.route('**/api/cart/set', lambda r: r.fulfill(status=503, json={'ok': False}))
        self.page.locator('.qty-remove').click()
        expect(self.page.locator('#orderFeedback')).to_be_visible()
        expect(self.page.locator('.cart-undo-item')).to_have_count(0)
        expect(self.page.locator('.item-note-input')).to_have_value('Synthetic item note')
        self.page.unroute('**/api/cart/set')
        self.page.locator('.qty-remove').click()
        expect(self.page.locator('.cart-undo-item')).to_be_visible()
        self.page.route('**/api/cart/undo', lambda r: r.fulfill(status=503, json={'ok': False}))
        self.page.get_by_role('button', name='Undo removal of 101SB').click()
        expect(self.page.locator('#orderFeedback')).to_be_visible()
        expect(self.page.get_by_role('button', name='Undo removal of 101SB')).to_be_enabled()
        self.page.unroute('**/api/cart/undo')
        self.page.route('**/api/cart/undo', lambda r: r.fulfill(status=200, json={'ok': True, 'total_items': 2, 'distinct_items': 1}))
        self.page.get_by_role('button', name='Undo removal of 101SB').click()
        expect(self.page.locator('#orderFeedback')).to_contain_text('couldn’t confirm')
        expect(self.page.get_by_role('button', name='Undo removal of 101SB')).to_be_enabled()
        self.page.unroute('**/api/cart/undo')
        self.page.get_by_role('button', name='Undo removal of 101SB').click()
        expect(self.page.locator('.qty-input')).to_have_value('2')
        expect(self.page.locator('.item-note-input')).to_have_value('Synthetic item note')

    def test_last_removed_item_expires_after_sixty_seconds(self):
        self.seed()
        self.goto('/cart')
        self.page.clock.install()
        self.page.locator('.qty-remove').click()
        expect(self.page.locator('.cart-undo-item')).to_be_visible()
        expect(self.page.locator('.cart-undo-seconds')).to_have_text('60s')
        ring = self.page.locator('.cart-undo-ring-progress')
        self.assertLess(float(ring.get_attribute('stroke-dashoffset')), 2)
        self.page.clock.fast_forward(30000)
        expect(self.page.locator('.cart-undo-seconds')).to_have_text('30s')
        self.assertAlmostEqual(float(ring.get_attribute('stroke-dashoffset')), 50, delta=2)
        self.page.clock.fast_forward(29000)
        expect(self.page.locator('.cart-undo-seconds')).to_have_text('1s')
        expect(self.page.locator('.cart-undo-item')).to_be_visible()
        self.page.clock.fast_forward(2000)
        expect(self.page.locator('#cartEmptyState')).to_be_visible()
        expect(self.page.locator('.cart-undo-item')).to_have_count(0)
        self.page.reload()
        expect(self.page.locator('#cartEmptyState')).to_be_visible()

    def test_individual_and_clear_undo_remain_independent(self):
        self.seed()
        self.seed('102SB', 3)
        self.seed('103SB', 4)
        self.goto('/cart')
        self.page.locator('.qty-remove[data-code="101SB"]').click()
        expect(self.page.locator('.cart-undo-item')).to_be_visible()
        self.page.locator('#clearOrderBtn').click()
        expect(self.page.locator('#cartTableBody tr.is-removed')).to_have_count(3)
        self.page.get_by_role('button', name='Undo removal of 101SB').click()
        expect(self.page.get_by_role('button', name='Undo clear order')).to_be_visible()
        expect(self.page.locator('#cartTotalQty')).to_have_text('2')
        self.page.get_by_role('button', name='Undo clear order').click()
        expect(self.page.locator('#cartTotalQty')).to_have_text('9')
        expect(self.page.locator('#cartTableBody tr.is-removed')).to_have_count(0)

    def test_server_rejects_expired_undo_token(self):
        self.seed()
        self.goto('/cart')
        with self.page.expect_response('**/api/cart/set') as response:
            self.page.locator('.qty-remove').click()
        serializer = URLSafeTimedSerializer(webapp.app.secret_key, salt='cart-undo-v1')
        snapshot = serializer.loads(response.value.json()['undo_token'])
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=int(time.time()) - 65):
            token = serializer.dumps(snapshot)
        self.assertEqual(self.context.request.post(f'{self.base_url}/api/cart/undo', data={'token': token}).status, 410)
