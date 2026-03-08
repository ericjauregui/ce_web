from __future__ import annotations

import json
import tempfile
from pathlib import Path

import app as webapp
from tests.common import BaseWebTest


class ProductRouteTests(BaseWebTest):
    def test_catalog_search_by_tag_still_works_without_exposing_tag_data_in_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "TAG100",
                            "name": "Tag Search Product",
                            "collection": "test-collection",
                            "description": "Only code and name should be visible in cards.",
                            "image": "101SB.jpg",
                            "tags": ["needle-tag-only"],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=needle-tag-only")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("TAG100", body)
        self.assertIn("Tag Search Product", body)
        self.assertNotIn("data-tags", body)

        anchor = body.find("drawer-tag100")
        self.assertGreaterEqual(anchor, 0)
        card_markup = body[max(0, anchor - 1200): anchor + 1200]
        self.assertNotIn("needle-tag-only", card_markup)
        self.assertNotIn("\"tags\"", card_markup)

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
        self.assertNotIn("Tags:", body)

    def test_product_detail_page_does_not_render_tag_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "TAG200",
                            "name": "Detail Privacy Product",
                            "collection": "test-collection",
                            "description": "Detail page should not display tags.",
                            "image": "101SB.jpg",
                            "tags": ["detail-tag-private"],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/product/TAG200")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Detail Privacy Product", body)
        self.assertNotIn("Tags:", body)
        self.assertNotIn("detail-tag-private", body)

    def test_product_detail_route_normalizes_code_via_redirect(self) -> None:
        response = self.client.get(f"/product/{self.valid_code.lower()}", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertIn(f"/product/{self.valid_code}", response.headers.get("Location", ""))

    def test_unknown_product_detail_returns_404(self) -> None:
        response = self.client.get("/product/does-not-exist")
        self.assertEqual(response.status_code, 404)
