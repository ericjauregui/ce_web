from __future__ import annotations

import app as webapp
from tests.common import BaseWebTest


class TeamRouteTests(BaseWebTest):
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
