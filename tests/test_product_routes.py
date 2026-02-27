from __future__ import annotations

from tests.common import BaseWebTest


class ProductRouteTests(BaseWebTest):
    def test_product_detail_page_renders_with_controls(self) -> None:
        response = self.client.get(f"/product/{self.valid_code}")
        self.assertEqual(response.status_code, 200)

        body = response.get_data(as_text=True)
        self.assertIn("Back to Catalog", body)
        self.assertIn("Contact Us", body)
        self.assertIn("Share", body)
        self.assertIn("Add to Order", body)
        self.assertNotIn("Item in order", body)
        self.assertIn("product-detail-meta-card", body)
        self.assertIn('"@type": "Product"', body)
        self.assertIn(self.valid_code, body)

    def test_product_detail_route_normalizes_code_via_redirect(self) -> None:
        response = self.client.get(f"/product/{self.valid_code.lower()}", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertIn(f"/product/{self.valid_code}", response.headers.get("Location", ""))

    def test_unknown_product_detail_returns_404(self) -> None:
        response = self.client.get("/product/does-not-exist")
        self.assertEqual(response.status_code, 404)
