from __future__ import annotations

import os
from unittest.mock import patch

from tests.common import BaseWebTest


class MetaRouteTests(BaseWebTest):
    def test_sitemap_uses_site_base_url_and_lists_team_members(self) -> None:
        with patch.dict(os.environ, {"SITE_BASE_URL": "https://californiaearrings.com"}, clear=False):
            response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("https://californiaearrings.com/", body)
        self.assertIn("https://californiaearrings.com/faqs", body)
        self.assertIn(f"https://californiaearrings.com/team/{self.first_member['slug']}", body)
        self.assertIn(
            f"https://californiaearrings.com/product/{self.valid_code}", body)
        self.assertIn("<changefreq>daily</changefreq>", body)

    def test_sitemaps_alias_and_robots_include_expected_directives(self) -> None:
        alias_response = self.client.get("/sitemaps.xml")
        self.assertEqual(alias_response.status_code, 200)
        self.assertIn("<urlset", alias_response.get_data(as_text=True))

        with patch.dict(os.environ, {"SITE_BASE_URL": "https://californiaearrings.com"}, clear=False):
            robots_response = self.client.get("/robots.txt")

        self.assertEqual(robots_response.status_code, 200)
        robots_body = robots_response.get_data(as_text=True)
        self.assertIn("Disallow: /api/", robots_body)
        self.assertIn("Disallow: /checkout", robots_body)
        self.assertIn("Sitemap: https://californiaearrings.com/sitemap.xml", robots_body)

    def test_base_layout_exposes_global_schema_and_noindex_for_transaction_pages(self) -> None:
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        home_body = home.get_data(as_text=True)
        self.assertIn('"@type": "Organization"', home_body)
        self.assertIn('"@type": "WebSite"', home_body)

        cart = self.client.get("/cart")
        self.assertEqual(cart.status_code, 200)
        self.assertIn('meta name="robots" content="noindex,nofollow"',
                      cart.get_data(as_text=True))

        checkout = self.client.get("/checkout")
        self.assertEqual(checkout.status_code, 200)
        self.assertIn('meta name="robots" content="noindex,nofollow"',
                      checkout.get_data(as_text=True))

        not_found = self.client.get("/this-page-does-not-exist")
        self.assertEqual(not_found.status_code, 404)
        self.assertIn('meta name="robots" content="noindex,nofollow"',
                      not_found.get_data(as_text=True))
