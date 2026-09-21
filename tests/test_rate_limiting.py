import time
from unittest.mock import patch

import app as webapp
from domains.rate_limiting import client_address
from tests.common import BaseWebTest


class RateLimitingTests(BaseWebTest):
    def setUp(self):
        super().setUp()
        self.limiter = webapp.app.extensions["ce_rate_limiter"]
        self.limiter.reset()
        self.addCleanup(self.limiter.reset)
        config = patch.dict(webapp.app.config, {
            "RATE_LIMIT_TESTING": True,
            "RATE_LIMIT_TRUST_PROXY": False,
            "CHECKOUT_RATE_LIMIT": "2 per minute",
            "CART_RATE_LIMIT": "2 per minute",
        })
        config.start()
        self.addCleanup(config.stop)

    def test_checkout_blocks_before_submission_and_leaves_cart_available(self):
        self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 1})
        with patch("domains.orders.OrderRepository.create_order") as save:
            for _ in range(2):
                self.assertEqual(self.client.post("/checkout").status_code, 400)
            response = self.client.post("/checkout")
            self.assertEqual(response.status_code, 429)
            save.assert_not_called()
        self.assertGreater(int(response.headers["Retry-After"]), 0)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("Your cart is still saved", response.text)
        self.assertEqual(self.client.get("/checkout").status_code, 200)
        self.assertEqual(self.client.get("/api/cart/count").json["total_items"], 1)

    def test_cart_routes_share_limit_and_other_addresses_are_independent(self):
        self.assertEqual(self.client.post("/api/cart/add", json={"code": self.valid_code}).status_code, 200)
        self.assertEqual(self.client.post("/api/cart/note", json={"code": self.valid_code, "note": "Keep"}).status_code, 200)
        response = self.client.post("/api/cart/clear")
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json["ok"])
        self.assertIn("wait", response.json["error"])
        self.assertGreater(int(response.headers["Retry-After"]), 0)
        self.assertEqual(self.client.get("/api/cart/count").json["total_items"], 1)
        other = webapp.app.test_client()
        self.assertEqual(other.post("/api/cart/clear", environ_overrides={"REMOTE_ADDR": "192.0.2.2"}).status_code, 200)

    def test_browsing_and_cookie_reset_do_not_bypass_or_consume_write_limit(self):
        for _ in range(3):
            self.assertEqual(self.client.get("/privacy").status_code, 200)
        for _ in range(2):
            self.assertEqual(webapp.app.test_client().post("/api/cart/clear").status_code, 200)
        self.assertEqual(webapp.app.test_client().post("/api/cart/clear").status_code, 429)

    def test_proxy_trust_ignores_spoofed_prefix_and_untrusted_headers(self):
        headers = {"X-Forwarded-For": "198.51.100.99, 192.0.2.10"}
        with webapp.app.test_request_context(headers=headers, environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            self.assertEqual(client_address(), "127.0.0.1")
            with patch.dict(webapp.app.config, {"RATE_LIMIT_TRUST_PROXY": True}):
                self.assertEqual(client_address(), "192.0.2.10")

    def test_invalid_forwarded_address_falls_back(self):
        with patch.dict(webapp.app.config, {"RATE_LIMIT_TRUST_PROXY": True}):
            with webapp.app.test_request_context(headers={"X-Forwarded-For": "invalid"}, environ_base={"REMOTE_ADDR": "192.0.2.5"}):
                self.assertEqual(client_address(), "192.0.2.5")

    def test_requests_resume_when_window_expires(self):
        for _ in range(2):
            self.assertEqual(self.client.post("/api/cart/clear").status_code, 200)
        self.assertEqual(self.client.post("/api/cart/clear").status_code, 429)
        with patch("limits.storage.memory.time.time", return_value=time.time() + 61):
            self.assertEqual(self.client.post("/api/cart/clear").status_code, 200)
