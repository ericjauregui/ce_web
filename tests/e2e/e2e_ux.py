"""UX recovery and accessibility journeys; local synthetic carts only."""
import re
from playwright.sync_api import expect
from tests.e2e.common import BaseE2ETest


class UXE2ETests(BaseE2ETest):
    viewport = {"width": 390, "height": 844}

    def test_checkout_names_validation_and_action_wording(self):
        self.add_first_catalog_item_to_cart()
        self.goto('/cart')
        self.page.get_by_role('link', name='Checkout', exact=True).click()
        expect(self.page.get_by_role('heading', name='Checkout', exact=True)).to_be_visible()
        form = self.page.locator('#checkoutForm')
        self.assertTrue(form.locator('input:not([type=hidden])').evaluate_all(
            'els => els.every(e => e.labels.length || e.getAttribute("aria-label"))'))
        self.page.get_by_label('Company Name', exact=False).fill('Synthetic Wholesale')
        self.page.locator('#checkoutPhone').fill('5550101')
        self.page.get_by_label('City', exact=False).fill('Los Angeles')
        for key, value in [('PhoneCountry', 'United States'), ('Country', 'United States'), ('State', 'California')]:
            self.page.locator('#checkout' + key).fill(value)
            self.page.locator('#checkout' + key + 'Combobox .checkout-combobox__option').first.click()
        posts = []
        def intercept(route):
            if route.request.method == 'POST':
                posts.append(route.request.url)
                route.fulfill(status=400, body='Unexpected synthetic submission')
            else:
                route.continue_()
        self.page.route('**/checkout', intercept)
        self.page.get_by_role('button', name='Submit Order', exact=True).click()
        expect(self.page.locator('#checkoutNameError')).to_have_text('Please enter your name.')
        expect(self.page.locator('#checkoutName')).to_be_focused()
        self.page.locator('#checkoutName').fill('Synthetic Buyer')
        self.page.locator('#checkoutCompany').fill('')
        self.page.get_by_role('button', name='Submit Order', exact=True).click()
        expect(self.page.locator('#checkoutCompanyError')).to_have_text('Please enter your company name.')
        expect(self.page.locator('#checkoutCompany')).to_be_focused()
        self.assertEqual(posts, [])

    def test_rejected_quantity_changes_preserve_saved_state_on_all_surfaces(self):
        # Background video streaming can occupy the single-threaded test server.
        # Reels have separate playback coverage; cart requests still hit the server.
        self.page.route(re.compile(r'/static/reels/[^?]+\.mp4(?:\?.*)?$', re.I), lambda r: r.fulfill(status=204, body=''))
        self.add_first_catalog_item_to_cart()
        code = self.page.locator('.add-to-cart-btn').first.get_attribute('data-code')
        for path, selector in [('/', '.product-card.is-in-cart'), (f'/product/{code}', '.product-detail-meta-card'), ('/cart', '#cartTableBody tr')]:
            with self.subTest(path=path):
                self.goto(path)
                card = self.page.locator(selector).first
                qty = card.locator('.product-qty-input')
                self.page.route('**/api/cart/set', lambda r: r.fulfill(status=429, json={'ok': False, 'error': 'rate_limited'}))
                card.locator('.qty-adjust-btn').last.click()
                expect(self.page.locator('#orderFeedback')).to_contain_text('Please wait')
                expect(qty).to_have_value('1')
                expect(self.page.locator('#cartCountBadge')).to_have_text('1')
                self.page.unroute('**/api/cart/set')
                card.locator('.qty-adjust-btn').last.click()
                expect(qty).to_have_value('2')
                self.assertEqual(self.context.request.get(f'{self.base_url}/api/cart/count').json()['total_items'], 2)
                # Reset through the UI for the next surface.
                card.locator('.qty-adjust-btn').first.click()
                expect(qty).to_have_value('1')

    def test_network_and_bad_response_add_failures_are_recoverable(self):
        self.goto('/')
        button = self.page.locator('.add-to-cart-btn').first
        self.page.route('**/api/cart/add', lambda r: r.abort('internetdisconnected'))
        button.click()
        expect(self.page.locator('#orderFeedback')).to_contain_text('couldn’t confirm')
        expect(button).to_have_text('Add to Order')
        self.page.unroute('**/api/cart/add')
        self.page.route('**/api/cart/add', lambda r: r.fulfill(status=503, content_type='text/html', body='Unavailable'))
        button.click()
        expect(self.page.locator('#orderFeedback')).to_contain_text('try again')
        expect(button).to_have_text('Add to Order')
        self.page.unroute('**/api/cart/add')
        button.click()
        expect(self.page.locator('#cartCountBadge')).to_have_text('1')
        self.assertEqual(self.page_errors, [])

    def test_item_note_failure_blocks_navigation_and_retry_preserves_text(self):
        self.add_first_catalog_item_to_cart()
        self.goto('/cart')
        note = self.page.locator('.item-note-input')
        self.page.route('**/api/cart/note', lambda r: r.fulfill(status=503, json={'ok': False}))
        note.fill('Synthetic note to preserve')
        self.page.get_by_role('link', name='Checkout', exact=True).click()
        expect(self.page.locator('#orderFeedback')).to_be_visible()
        self.assertTrue(self.page.url.endswith('/cart'))
        expect(note).to_have_value('Synthetic note to preserve')
        self.page.unroute('**/api/cart/note')
        self.page.get_by_role('link', name='Checkout', exact=True).click()
        self.page.wait_for_url('**/checkout')
        expect(self.page.locator('.checkout-items-table')).to_contain_text('Synthetic note to preserve')
        self.goto('/cart')
        self.page.locator('.item-note-input').fill('')
        self.page.get_by_role('link', name='Checkout', exact=True).click()
        self.page.wait_for_url('**/checkout')
        expect(self.page.locator('.checkout-items-table')).not_to_contain_text('Synthetic note to preserve')

    def test_clear_order_failure_and_undo(self):
        self.add_first_catalog_item_to_cart()
        self.goto('/cart')
        self.page.route('**/api/cart/clear', lambda r: r.fulfill(status=429, json={'ok': False}))
        self.page.locator('#clearOrderBtn').click()
        expect(self.page.locator('#orderFeedback')).to_contain_text('Please wait')
        expect(self.page.locator('#cartTableBody tr:not(.is-removed)')).to_have_count(1)
        self.page.unroute('**/api/cart/clear')
        self.page.locator('#clearOrderBtn').click()
        expect(self.page.get_by_role('button', name='Undo clear order')).to_be_visible()
        self.assertEqual(self.context.request.get(f'{self.base_url}/api/cart/count').json()['total_items'], 0)
        self.page.get_by_role('button', name='Undo clear order').click()
        expect(self.page.locator('#cartTableBody tr:not(.is-removed)')).to_have_count(1)

    def test_empty_search_has_query_and_recovery(self):
        self.goto('/?q=zzzxxyy-no-match')
        expect(self.page.locator('.search-empty-state [role=status]')).to_contain_text('No items found')
        expect(self.page.locator('.search-empty-state [role=status]')).to_contain_text('zzzxxyy-no-match')
        card = self.page.locator('.search-empty-state .card')
        for width in (320, 390, 1280):
            self.page.set_viewport_size({'width': width, 'height': 900})
            expect(card.get_by_role('link', name='Clear Search', exact=True)).to_be_visible()
            self.assertTrue(card.evaluate('e => { const a=e.querySelector("a").getBoundingClientRect(), c=e.getBoundingClientRect(); return a.left>=c.left && a.right<=c.right && a.bottom<=c.bottom; }'))
            self.assertNotEqual(card.evaluate('e => getComputedStyle(e).backgroundColor'), 'rgba(0, 0, 0, 0)')
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
        self.page.get_by_role('link', name='Clear Search', exact=True).click()
        expect(self.page.locator('.product-card').first).to_be_visible()

    def test_home_secondary_buttons_share_sizing_and_style(self):
        button_style = 'e => { const s=getComputedStyle(e); return [s.height,s.fontSize,s.fontWeight,s.paddingLeft,s.paddingRight,s.borderRadius,s.borderTopColor,s.backgroundColor,s.color]; }'
        for width in (320, 390, 768, 1280):
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.goto('/?q=zzzxxyy-no-match')
            buttons = [self.page.get_by_role('link', name=name, exact=True) for name in ('← Full Catalog', 'Clear Search', 'View All')]
            styles = []
            for button in buttons:
                expect(button).to_be_visible()
                styles.append(button.evaluate(button_style))
            self.assertEqual(styles[0], styles[1])
            self.assertEqual(styles[1], styles[2])
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
            self.goto('/')
            jump = self.page.get_by_role('link', name='Jump to top', exact=True)
            expect(jump).to_be_visible()
            self.assertEqual(jump.evaluate(button_style), styles[0])
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)

    def test_floating_contact_keeps_order_action_clear_and_still_drags(self):
        self.add_first_catalog_item_to_cart()
        bubble = self.page.locator('.whatsapp-float')
        self.page.wait_for_function("""() => {
          const bubble = document.querySelector('.whatsapp-float').getBoundingClientRect();
          const cart = document.querySelector('#catalogMiniCart').getBoundingClientRect();
          return bubble.bottom <= cart.top;
        }""")
        start = bubble.bounding_box()
        self.page.mouse.move(start['x'] + 20, start['y'] + 20)
        self.page.mouse.down()
        self.page.mouse.move(start['x'] - 90, start['y'] - 120, steps=12)
        self.page.mouse.up()
        moved = bubble.bounding_box()
        self.assertLess(moved['x'], start['x'] - 50)
        self.assertIn(self.base_url, self.page.url)
        self.page.set_viewport_size({'width': 320, 'height': 700})
        self.page.wait_for_function("""() => {
          const r = document.querySelector('.whatsapp-float').getBoundingClientRect();
          return r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight;
        }""")

    def test_mobile_touch_controls_fit_and_have_names(self):
        self.add_first_catalog_item_to_cart()
        code = self.page.locator('.add-to-cart-btn').first.get_attribute('data-code')
        for width in (320, 390, 767, 768, 1280):
            self.page.set_viewport_size({'width': width, 'height': 900})
            for path in ('/', '/cart', f'/product/{code}', '/checkout', '/team', '/contact', '/about'):
                self.goto(path)
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
                if path == '/':
                    self.page.locator('.product-card.is-in-cart').scroll_into_view_if_needed()
                    self.assertTrue(self.page.locator('.product-card.is-in-cart').evaluate('''(card) => {
                      const r = card.getBoundingClientRect();
                      return [...card.querySelectorAll('.qty-adjust-btn, .qty-clear-btn, .product-qty-input')].every(e => {
                        const q = e.getBoundingClientRect(); return q.left >= r.left && q.right <= r.right;
                      });
                    }'''))
                if width < 768 and path in ('/', f'/product/{code}'):
                    for control in self.page.locator('.qty-adjust-btn:visible, .qty-clear-btn:visible, .product-qty-input:visible').all():
                        box = control.bounding_box()
                        self.assertGreaterEqual(box['width'], 44)
                        self.assertGreaterEqual(box['height'], 44)
                        self.assertTrue(control.get_attribute('aria-label'))
                if path == '/':
                    self.page.locator('.product-card.is-in-cart .product-qty-control').evaluate(
                        "element => element.scrollIntoView({block: 'center'})")
                elif path.startswith('/product/'):
                    self.page.locator('.product-qty-control').evaluate(
                        "element => element.scrollIntoView({block: 'center'})")
                self.page.screenshot(path=str(self._artifact_dir_for_capture() / f'{path.strip("/").replace("/", "-")}-{width}.png'))

    def test_cart_keeps_compact_rows_and_single_line_centered_heading(self):
        self.add_first_catalog_item_to_cart()
        for width in (320, 360, 390, 414, 575, 576, 767, 768, 1024, 1280, 1440):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': 900})
                self.goto('/cart')
                self.page.evaluate('document.fonts.ready')
                geometry = self.page.locator('.page-title-row').evaluate("""row => {
                  const nodes = [row.querySelector('.page-title-back'), row.querySelector('h1'), row.querySelector('.page-title-action')];
                  const r = row.getBoundingClientRect();
                  const boxes = nodes.map(e => {const b=e.getBoundingClientRect(); return {left:b.left,right:b.right,center:b.top+b.height/2,width:b.width,height:b.height,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth};});
                  const text = document.createRange(); text.selectNodeContents(nodes[1]);
                  return {boxes, rowCenter:r.left+r.width/2, textLines:text.getClientRects().length};
                }""")
                left, title, right = geometry['boxes']
                self.assertLessEqual(abs(title['center'] - left['center']), 1)
                self.assertLessEqual(abs(title['center'] - right['center']), 1)
                self.assertLessEqual(abs((title['left'] + title['right']) / 2 - geometry['rowCenter']), 1)
                self.assertLessEqual(left['right'], title['left'])
                self.assertLessEqual(title['right'], right['left'])
                self.assertEqual(geometry['textLines'], 1)
                for box in geometry['boxes']:
                    self.assertLessEqual(box['scrollWidth'], box['clientWidth'] + 1)
                expect(self.page.locator('.cart-items-table thead')).to_be_visible()
                remove = self.page.locator('.qty-remove')
                self.assertRegex(remove.get_attribute('aria-label'), r'^Remove .+ from order$')
                expect(remove).to_be_visible()
                expect(remove.locator('.cart-remove-icon' if width < 768 else '.cart-remove-text')).to_be_visible()
                expect(remove.locator('.cart-remove-text' if width < 768 else '.cart-remove-icon')).to_be_hidden()
                self.assertEqual(self.page.locator('#cartTableBody tr').evaluate('e => getComputedStyle(e).display'), 'table-row')
                if width < 768:
                    note = self.page.locator('.item-note-shell')
                    self.assertLess(note.bounding_box()['width'], 70)
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
                self.assertTrue(self.page.locator('#cartTableWrap').evaluate('e => e.scrollWidth <= e.clientWidth + 1'))
                actions = self.page.locator('.cart-summary-bar .btn').evaluate_all('es => es.map(e => e.getBoundingClientRect().toJSON())')
                self.assertLessEqual(actions[0]['right'], actions[1]['left'])
                self.page.screenshot(path=str(self._artifact_dir_for_capture() / f'compact-cart-{width}.png'), animations='disabled')
        self.page.set_viewport_size({'width': 390, 'height': 900})
        self.goto('/cart')
        self.page.locator('.item-note-input').fill('Synthetic compact note')
        self.page.get_by_role('link', name='Checkout', exact=True).click()
        self.page.wait_for_url('**/checkout')
        expect(self.page.locator('.checkout-items-table')).to_contain_text('Synthetic compact note')
        self.goto('/cart')
        self.page.locator('#clearOrderBtn').click()
        expect(self.page.get_by_role('button', name='Undo clear order')).to_be_visible()

    def _artifact_dir_for_capture(self):
        path = self._artifact_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path
