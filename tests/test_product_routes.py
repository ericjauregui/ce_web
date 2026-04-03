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

    def test_catalog_search_matches_close_name_typo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "FUZZ100",
                            "name": "Precision Seeder",
                            "collection": "planting-tools",
                            "description": "Designed for even row spacing.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "MISS200",
                            "name": "Harvest Scoop",
                            "collection": "planting-tools",
                            "description": "A different product that should not match.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=precison seeder")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Precision Seeder", body)
        self.assertNotIn("Harvest Scoop", body)

    def test_catalog_search_ignores_spacing_and_punctuation_in_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "BD-200X",
                            "name": "Broadfork Deluxe",
                            "collection": "field-tools",
                            "description": "Heavy duty broadfork.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "RK-300",
                            "name": "Rake Standard",
                            "collection": "field-tools",
                            "description": "Should stay out of the results.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=bd200x")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("BD-200X", body)
        self.assertNotIn("RK-300", body)

    def test_catalog_search_matches_plural_name_with_missing_vowel_typo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "TUR100",
                            "name": "Turtles Pendant",
                            "collection": "charms",
                            "description": "Sea turtle inspired pendant.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "STAR200",
                            "name": "Star Pendant",
                            "collection": "charms",
                            "description": "Different charm that should not match.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=trtle")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Turtles Pendant", body)
        self.assertNotIn("Star Pendant", body)

    def test_catalog_search_matches_short_abbreviation_against_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "HRT100",
                            "name": "Heart Earrings",
                            "collection": "charms",
                            "description": "Classic heart shape.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "HAR200",
                            "name": "Harvest Earrings",
                            "collection": "charms",
                            "description": "Should not match the abbreviation query.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=hrt")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Heart Earrings", body)
        self.assertNotIn("Harvest Earrings", body)

    def test_catalog_search_matches_translation_from_product_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "COR100",
                            "name": "Heart Hoops",
                            "collection": "charms",
                            "description": "Heart-forward everyday hoops.",
                            "image": "101SB.jpg",
                            "aliases": ["corazon", "corazones", "heart hoops"],
                        },
                        {
                            "code": "STR200",
                            "name": "Star Hoops",
                            "collection": "charms",
                            "description": "Different shape that should not match.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=corazon")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Heart Hoops", body)
        self.assertNotIn("Star Hoops", body)

    def test_catalog_search_normalizes_accents_and_special_characters_in_query(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "ACC100",
                            "name": "Gold Heart Studs",
                            "collection": "hearts",
                            "description": "Classic heart studs.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "ACC200",
                            "name": "Gold Star Studs",
                            "collection": "studs",
                            "description": "Classic star studs.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=%C2%A1cora-z%C3%B3n!!!")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Gold Heart Studs", body)
        self.assertNotIn("Gold Star Studs", body)

    def test_catalog_search_matches_spanish_query_against_english_metadata_without_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "ENG100",
                            "name": "Gold Heart Studs",
                            "collection": "hearts",
                            "description": "Classic heart studs.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "ENG200",
                            "name": "Gold Star Studs",
                            "collection": "studs",
                            "description": "Classic star studs.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=corazones")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Gold Heart Studs", body)
        self.assertNotIn("Gold Star Studs", body)

    def test_catalog_search_matches_english_query_against_spanish_metadata_without_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "ESP100",
                            "name": "Aretes Corazon Oro",
                            "collection": "corazones",
                            "description": "Aretes de corazon en oro.",
                            "image": "101SB.jpg",
                            "tags": ["corazon", "oro", "aretes"],
                        },
                        {
                            "code": "ESP200",
                            "name": "Aretes Estrella Oro",
                            "collection": "estrellas",
                            "description": "Aretes de estrella en oro.",
                            "image": "101SB.jpg",
                            "tags": ["estrella", "oro", "aretes"],
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=heart")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Aretes Corazon Oro", body)
        self.assertNotIn("Aretes Estrella Oro", body)

    def test_catalog_search_matches_product_alias_without_rendering_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "ALS100",
                            "name": "Sacred Heart Pendant",
                            "collection": "charms",
                            "description": "A heart pendant with alternate search metadata.",
                            "image": "101SB.jpg",
                            "aliases": ["corazon", "hrt pendant"],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=corazon")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Sacred Heart Pendant", body)
        anchor = body.find("drawer-als100")
        self.assertGreaterEqual(anchor, 0)
        card_markup = body[max(0, anchor - 1200): anchor + 1200]
        self.assertNotIn("corazon", card_markup)
        self.assertNotIn("hrt pendant", card_markup)
        self.assertNotIn("\"aliases\"", card_markup)

    def test_catalog_search_tortuga_filters_out_unrelated_products(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "TUR100",
                            "name": "Gold Turtle Studs",
                            "collection": "animal-studs",
                            "description": "Playful turtle earrings.",
                            "image": "101SB.jpg",
                            "aliases": ["tortuga"],
                        },
                        {
                            "code": "102SB",
                            "name": "Classic Gold Diamond Studs",
                            "collection": "studs",
                            "description": "Elegant everyday studs for any jewelry assortment.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=tortuga")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Gold Turtle Studs", body)
        self.assertNotIn("Classic Gold Diamond Studs", body)

    def test_catalog_search_hearts_filters_out_description_only_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "HRT100",
                            "name": "Gold Heart Studs",
                            "collection": "hearts",
                            "description": "Classic heart studs.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "STR100",
                            "name": "Strawberry Enamel Studs",
                            "collection": "studs",
                            "description": "Bright enamel studs for the young at heart.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            webapp.CATALOG_PATH = catalog_path
            try:
                response = self.client.get("/?q=hearts")
            finally:
                webapp.CATALOG_PATH = original_catalog_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Gold Heart Studs", body)
        self.assertNotIn("Strawberry Enamel Studs", body)

    def test_catalog_search_returns_single_ranked_section_when_query_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "products.json"
            collections_path = Path(temp_dir) / "collections.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "code": "FLW100",
                            "name": "Floral Gold Studs",
                            "collection": "flower-studs",
                            "description": "Classic flower studs.",
                            "image": "101SB.jpg",
                        },
                        {
                            "code": "HRT200",
                            "name": "Gold Heart & Flower Studs",
                            "collection": "hearts",
                            "description": "Heart studs with a flower accent.",
                            "image": "101SB.jpg",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            collections_path.write_text(
                json.dumps(
                    {
                        "order": ["hearts", "flower-studs"],
                        "labels": {
                            "hearts": "Heart Studs",
                            "flower-studs": "Flower Studs",
                        },
                    }
                ),
                encoding="utf-8",
            )

            original_catalog_path = webapp.CATALOG_PATH
            original_collections_path = webapp.COLLECTIONS_PATH
            webapp.CATALOG_PATH = catalog_path
            webapp.COLLECTIONS_PATH = collections_path
            try:
                response = self.client.get("/?q=flower")
            finally:
                webapp.CATALOG_PATH = original_catalog_path
                webapp.COLLECTIONS_PATH = original_collections_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Floral Gold Studs", body)
        self.assertIn("Gold Heart &amp; Flower Studs", body)
        self.assertIn("id=\"section-search-results\"", body)
        self.assertEqual(body.count("id=\"section-search-results\""), 1)

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
