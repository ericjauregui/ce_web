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

    def test_clear_endpoint_empties_cart(self) -> None:
        self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 3})

        clear_response = self.client.post("/api/cart/clear", json={})
        self.assertEqual(clear_response.status_code, 200)
        clear_data = clear_response.get_json()
        self.assertTrue(clear_data["ok"])
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

    def test_item_note_round_trip_in_cart_view(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 1})

        note_response = self.client.post(
            "/api/cart/note",
            json={"code": self.valid_code,
                  "note": "Please match screwback style"},
        )
        self.assertEqual(note_response.status_code, 200)
        note_data = note_response.get_json()
        self.assertTrue(note_data["ok"])
        self.assertEqual(note_data["note"], "Please match screwback style")

        cart_response = self.client.get("/cart")
        self.assertEqual(cart_response.status_code, 200)
        cart_body = cart_response.get_data(as_text=True)
        self.assertIn("item-note-input", cart_body)
        self.assertIn("Please match screwback style", cart_body)

    def test_item_note_requires_item_in_cart(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 1})
        self.client.post("/api/cart/remove", json={"code": self.valid_code})

        response = self.client.post(
            "/api/cart/note",
            json={"code": self.valid_code, "note": "should fail"},
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "item_not_in_cart")

    def test_checkout_csv_includes_per_item_note_column(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 2})
        self.client.post(
            "/api/cart/note",
            json={"code": self.valid_code, "note": "Need matching pair"},
        )

        checkout_response = self.client.post(
            "/checkout",
            data={
                "name": "Test Buyer",
                "company": "Sample Co",
                "phone": "555-0101",
                "notes": "general order note",
            },
        )
        self.assertEqual(checkout_response.status_code, 200)

        with self.client.session_transaction() as sess:
            token = sess.get("last_order_token")

        self.assertTrue(token)
        csv_response = self.client.get(f"/download/order/{token}.csv")
        self.assertEqual(csv_response.status_code, 200)
        csv_text = csv_response.get_data(as_text=True)

        self.assertIn("notes", csv_text)
        self.assertIn("Need matching pair", csv_text)
        self.assertIn("code,name,quantity,notes", csv_text)
        self.assertNotIn("collection", csv_text)
        self.assertNotIn("material", csv_text)
        self.assertNotIn("size_mm", csv_text)

    def test_checkout_pdf_download_endpoint_returns_pdf(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 1})

        checkout_response = self.client.post(
            "/checkout",
            data={
                "name": "Test Buyer",
                "company": "Sample Co",
                "phone": "555-0101",
                "notes": "general order note",
            },
        )
        self.assertEqual(checkout_response.status_code, 200)

        with self.client.session_transaction() as sess:
            token = sess.get("last_order_token")

        self.assertTrue(token)
        pdf_response = self.client.get(f"/download/order/{token}.pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertTrue(pdf_response.get_data().startswith(b"%PDF"))

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
