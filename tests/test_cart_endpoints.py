from __future__ import annotations

import re

from tests.common import BaseWebTest


class CartEndpointTests(BaseWebTest):
    def test_index_renders_catalog_and_script(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("product-grid-row", body)
        self.assertIn("/static/js/catalog.js", body)

    def test_add_set_and_count_flow(self) -> None:
        add_response = self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 2})
        self.assertEqual(add_response.status_code, 200)
        add_data = add_response.get_json()
        self.assertTrue(add_data["ok"])
        self.assertEqual(add_data["total_items"], 2)
        self.assertEqual(add_data["distinct_items"], 1)

        set_response = self.client.post("/api/cart/set", json={"code": self.valid_code, "qty": 5})
        self.assertEqual(set_response.status_code, 200)
        set_data = set_response.get_json()
        self.assertEqual(set_data["total_items"], 5)
        self.assertEqual(set_data["distinct_items"], 1)

        count_response = self.client.get("/api/cart/count")
        self.assertEqual(count_response.status_code, 200)
        count_data = count_response.get_json()
        self.assertEqual(count_data["total_items"], 5)
        self.assertEqual(count_data["distinct_items"], 1)

    def test_set_zero_clears_item_in_single_request(self) -> None:
        self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 4})

        clear_response = self.client.post("/api/cart/set", json={"code": self.valid_code, "qty": 0})
        self.assertEqual(clear_response.status_code, 200)
        clear_data = clear_response.get_json()
        self.assertEqual(clear_data["total_items"], 0)
        self.assertEqual(clear_data["distinct_items"], 0)

        count_response = self.client.get("/api/cart/count")
        self.assertEqual(count_response.status_code, 200)
        count_data = count_response.get_json()
        self.assertEqual(count_data["total_items"], 0)
        self.assertEqual(count_data["distinct_items"], 0)

    def test_unknown_code_is_rejected(self) -> None:
        response = self.client.post("/api/cart/add", json={"code": "NOT_A_CODE", "qty": 1})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "unknown_code")

    def test_default_catalog_state_has_more_cards_than_filtered_query(self) -> None:
        full_response = self.client.get("/")
        self.assertEqual(full_response.status_code, 200)
        full_body = full_response.get_data(as_text=True)
        full_count = len(re.findall(r'class=\"[^\"]*product-card', full_body))
        self.assertGreater(full_count, 0)

        filtered_response = self.client.get(f"/?q={self.valid_code}")
        self.assertEqual(filtered_response.status_code, 200)
        filtered_body = filtered_response.get_data(as_text=True)
        filtered_count = len(re.findall(r'class=\"[^\"]*product-card', filtered_body))

        self.assertGreater(filtered_count, 0)
        self.assertLess(filtered_count, full_count)
