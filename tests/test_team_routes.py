from __future__ import annotations

import base64
import json
import tempfile
import time
import re
from urllib.parse import urlsplit
from pathlib import Path

import app as webapp
from tests.common import BaseWebTest


class TeamRouteTests(BaseWebTest):
    def test_team_photos_with_jpg_extension_are_real_jpegs(self) -> None:
        for member in webapp.load_team()["members"]:
            photo = member.get("photo")
            if not photo:
                continue

            image_bytes = (webapp.BASE_DIR / "static" / "team" / photo).read_bytes()
            self.assertTrue(
                image_bytes.startswith(b"\xff\xd8\xff"),
                f"{photo} must contain JPEG data for cross-browser support",
            )

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
        self.assertIn(f"/static/assets/team-qr/{member_slug}.svg", page_body)

        vcard = self.client.get(f"/team/{member_slug}/contact.vcf")
        self.assertEqual(vcard.status_code, 200)
        vcard_body = vcard.get_data(as_text=True)
        self.assertIn("BEGIN:VCARD", vcard_body)
        self.assertIn(f"FN:{member_name}", vcard_body)
        self.assertIn(f"TITLE:{self.first_member['title']}", vcard_body)
        self.assertIn(f"TEL;TYPE=CELL:{self.first_member['phone_digits']}", vcard_body)
        self.assertIn("TEL;TYPE=WORK,VOICE:12139357272", vcard_body)
        self.assertIn(f"EMAIL;TYPE=INTERNET:{self.first_member['email']}", vcard_body)
        self.assertIn("URL:https://californiaearrings.com", vcard_body)
        self.assertIn("ADR;TYPE=WORK:;;650 S Hill St Suite 518;Los Angeles;CA;90014;US", vcard_body)
        member_photo = self.first_member.get("photo")
        if member_photo:
            self.assertIn("PHOTO;ENCODING=b;TYPE=JPEG:", vcard_body)
        else:
            self.assertNotIn("PHOTO;ENCODING=b;TYPE=", vcard_body)

        qr_response = self.client.get(f"/static/assets/team-qr/{member_slug}.svg")
        self.assertEqual(qr_response.status_code, 200)
        self.assertIn("image/svg+xml", qr_response.content_type)
        qr_svg = qr_response.get_data(as_text=True)
        self.assertIn("<svg", qr_svg)
        self.assertIn('fill="#050505"', qr_svg)
        self.assertIn("<image", qr_svg)
        self.assertIn("data:image/png;base64,", qr_svg)

        legacy_qr_response = self.client.get(f"/team/{member_slug}/contact-qr.svg")
        self.assertEqual(legacy_qr_response.status_code, 302)
        self.assertIn(f"/static/assets/team-qr/{member_slug}.svg", legacy_qr_response.location)

    def test_static_team_qr_assets_regenerate_only_when_team_json_changes(self) -> None:
        team = webapp.load_team()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            team_path = root / "team.json"
            static_dir = root / "static"
            team_path.write_text(json.dumps(team), encoding="utf-8")

            assets = webapp.ensure_team_qr_assets(team, team_path, static_dir)
            qr_path = static_dir / assets[self.first_member["slug"]]
            first_mtime = qr_path.stat().st_mtime_ns
            self.assertTrue(qr_path.read_text(encoding="utf-8").startswith("<?xml"))

            webapp.ensure_team_qr_assets(team, team_path, static_dir)
            self.assertEqual(qr_path.stat().st_mtime_ns, first_mtime)

            changed_team = dict(team)
            changed_team["headline"] = "Updated Team"
            time.sleep(0.001)
            team_path.write_text(json.dumps(changed_team), encoding="utf-8")
            webapp.ensure_team_qr_assets(changed_team, team_path, static_dir)
            self.assertGreater(qr_path.stat().st_mtime_ns, first_mtime)

    def test_digital_cards_have_individual_previews_and_focused_actions(self) -> None:
        for member in self.team_members:
            with self.subTest(member=member["slug"]):
                response = self.client.get(f"/team/{member['slug']}?utm_source=test")
                body = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('id="shareCard"', body)
                self.assertIn('id="shareLink"', body)
                self.assertIn('id="contactQr"', body)
                self.assertIn(member["bio"], body)
                self.assertIn('id="navSearchForm"', body)
                self.assertIn('id="cartLink"', body)
                self.assertIn('class="footer-social mb-2"', body)
                self.assertNotIn('latest-videos-section', body)
                self.assertEqual(body.count(f'href="{member["call_url"]}"'), 2)
                main = body.split('<main>', 1)[1].split('</main>', 1)[0]
                self.assertEqual(main.count(f'href="mailto:{member["email"]}"'), 2)
                profile = body.split('<article class="dbc-profile"', 1)[1].split('</article>', 1)[0]
                self.assertIn('650 S Hill St, Suite 518', profile)
                self.assertIn('Office', profile)
                self.assertIn('href="tel:+12139357272"', profile)
                self.assertIn(f'href="{member["call_url"]}"', profile)
                self.assertIn(f'href="mailto:{member["email"]}"', profile)
                og = re.search(r'<meta property="og:image" content="([^"]+)"', body).group(1)
                twitter = re.search(r'<meta name="twitter:image" content="([^"]+)"', body).group(1)
                self.assertEqual(og, twitter)
                self.assertTrue(og.startswith("http"))
                self.assertIn(f"/team-social/{member['slug']}.jpg", og)
                asset = self.client.get(urlsplit(og).path)
                self.assertEqual(asset.status_code, 200)
                self.assertTrue(asset.data.startswith(b"\xff\xd8\xff"))
                asset.close()
                canonical = re.search(r'<link rel="canonical" href="([^"]+)"', body).group(1)
                self.assertTrue(canonical.endswith(f"/team/{member['slug']}"))

    def test_other_pages_retain_full_site_navigation(self) -> None:
        body = self.client.get("/team").get_data(as_text=True)
        self.assertIn('id="navSearchForm"', body)
        self.assertIn('id="cartLink"', body)
        self.assertNotIn('class="dbc-page-links"', body)

    def test_member_not_found(self) -> None:
        self.assertEqual(self.client.get("/team/unknown-member").status_code, 404)

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
        self.assertIn("TITLE:Ignored Title", with_photo)
        self.assertIn("TEL;TYPE=WORK,VOICE:12139357272", with_photo)
        self.assertIn("URL:https://californiaearrings.com", with_photo)
        self.assertIn("ADR;TYPE=WORK:;;650 S Hill St Suite 518;Los Angeles;CA;90014;US", with_photo)
        self.assertIn(f"PHOTO;ENCODING=b;TYPE=JPEG:{base64.b64encode(b'test-photo-bytes').decode('ascii')}", with_photo)
        self.assertNotIn("PHOTO;ENCODING=b;TYPE=", without_photo)
