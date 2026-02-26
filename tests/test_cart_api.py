from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app as webapp


class CartApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        webapp.app.config.update(TESTING=True)
        cls.client = webapp.app.test_client()
        cls.valid_code = webapp.load_products()[0]["code"]
        cls.team_members = webapp.build_team_members(webapp.load_team())
        cls.first_member = cls.team_members[0] if cls.team_members else {"slug": "", "name": ""}

    def setUp(self) -> None:
        with self.client.session_transaction() as sess:
            sess["cart"] = {}

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

    def test_team_cards_link_to_member_pages(self) -> None:
        response = self.client.get("/team")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn(f"/team/{self.first_member['slug']}", body)

    def test_team_member_slug_uses_first_name(self) -> None:
        members = webapp.build_team_members(
            {
                "company": "California Earrings",
                "members": [{"name": "Miguel Jauregui"}],
            }
        )
        self.assertEqual(members[0]["slug"], "miguel")

    def test_duplicate_first_names_append_last_initial(self) -> None:
        members = webapp.build_team_members(
            {
                "company": "California Earrings",
                "members": [
                    {"name": "Alex Stone"},
                    {"name": "Alex Johnson"},
                    {"name": "Alex"},
                ],
            }
        )
        slugs = [member["slug"] for member in members]
        self.assertEqual(slugs, ["alex-s", "alex-j", "alex-x"])

    def test_team_member_page_and_vcard_download(self) -> None:
        member_slug = self.first_member["slug"]
        member_name = self.first_member["name"]
        member_page = self.client.get(f"/team/{member_slug}")
        self.assertEqual(member_page.status_code, 200)
        page_body = member_page.get_data(as_text=True)
        self.assertIn(f"/team/{member_slug}/contact.vcf", page_body)

        vcard = self.client.get(f"/team/{member_slug}/contact.vcf")
        self.assertEqual(vcard.status_code, 200)
        vcard_body = vcard.get_data(as_text=True)
        self.assertIn("BEGIN:VCARD", vcard_body)
        self.assertIn(f"FN:{member_name}", vcard_body)

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

    def test_nav_search_clear_logic_uses_input_and_search_events(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("async function handleClearedSearch()", body)
        self.assertIn(
            "input.addEventListener(\"search\", maybeClearSearch)", body)
        self.assertIn(
            "input.addEventListener(\"input\", maybeClearSearch)", body)
        self.assertIn("setOpen(false, { restoreValue: false });", body)
        self.assertIn(
            "window.history.replaceState(null, \"\", target.pathname);", body)

    def test_default_catalog_state_has_more_cards_than_filtered_query(self) -> None:
        full_response = self.client.get("/")
        self.assertEqual(full_response.status_code, 200)
        full_body = full_response.get_data(as_text=True)
        full_count = len(re.findall(r'class=\"[^\"]*product-card', full_body))
        self.assertGreater(full_count, 0)

        filtered_response = self.client.get(f"/?q={self.valid_code}")
        self.assertEqual(filtered_response.status_code, 200)
        filtered_body = filtered_response.get_data(as_text=True)
        filtered_count = len(re.findall(
            r'class=\"[^\"]*product-card', filtered_body))

        self.assertGreater(filtered_count, 0)
        self.assertLess(filtered_count, full_count)

    def test_hover_rules_are_scoped_to_hover_capable_devices(self) -> None:
        css = (Path(webapp.BASE_DIR) / "static" / "css" /
               "style.css").read_text(encoding="utf-8")

        self.assertIn("@media (hover: hover) and (pointer: fine)", css)
        self.assertIn(".social-brand-link:hover", css)
        self.assertIn(".team-inline-icon:hover", css)
        self.assertIn(".team-phone-link:hover", css)
        self.assertIn(".chip:hover", css)
        self.assertIn(".nav-search-trigger:hover", css)
        self.assertIn(".cart-link:hover svg", css)

    def test_touch_devices_neutralize_outline_button_hover_state(self) -> None:
        css = (Path(webapp.BASE_DIR) / "static" / "css" /
               "style.css").read_text(encoding="utf-8")
        condensed = re.sub(r"\s+", " ", css)

        self.assertIn("@media (hover: none), (pointer: coarse)", condensed)
        self.assertIn(
            ".btn-outline-gold { --bs-btn-hover-bg: transparent;", condensed)
        self.assertIn("--bs-btn-hover-color: var(--gold);", condensed)
        self.assertIn(
            ".btn-outline-gold:hover { color: var(--gold);", condensed)


if __name__ == "__main__":
    unittest.main()
