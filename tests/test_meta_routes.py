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
        self.assertIn(f"https://californiaearrings.com/team/{self.first_member['slug']}", body)
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
