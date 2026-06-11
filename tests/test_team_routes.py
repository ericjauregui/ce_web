from __future__ import annotations

import base64

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
        self.assertNotIn("TITLE:", vcard_body)
        self.assertIn(f"TEL;TYPE=CELL:{self.first_member['phone_digits']}", vcard_body)
        self.assertIn(f"EMAIL;TYPE=INTERNET:{self.first_member['email']}", vcard_body)
        member_photo = self.first_member.get("photo")
        if member_photo:
            self.assertIn("PHOTO;ENCODING=b;TYPE=JPEG:", vcard_body)
        else:
            self.assertNotIn("PHOTO;ENCODING=b;TYPE=", vcard_body)

    def test_build_member_vcard_includes_photo_only_when_present(self) -> None:
        member = {
            "name": "Jane Smith",
            "photo": "jane.jpg",
            "phone_digits": "12135551212",
            "email": "jane@example.com",
            "title": "Ignored Title",
        }

        with_photo = webapp.build_member_vcard(
            member,
            {"company": "California Earrings"},
            photo_bytes=b"test-photo-bytes",
            photo_type="JPEG",
        )
        without_photo = webapp.build_member_vcard(member, {"company": "California Earrings"})

        self.assertIn("FN:Jane Smith", with_photo)
        self.assertIn("N:Smith;Jane;;;", with_photo)
        self.assertNotIn("TITLE:", with_photo)
        self.assertIn(f"PHOTO;ENCODING=b;TYPE=JPEG:{base64.b64encode(b'test-photo-bytes').decode('ascii')}", with_photo)
        self.assertNotIn("PHOTO;ENCODING=b;TYPE=", without_photo)
