"""Isolation checks for cases the committed team cards cannot exercise.

Failure modes: same-name slugs collide; QR files rewrite for unchanged source or
stay stale after team data changes; a portrait-free member gets a broken PHOTO
property in the downloadable vCard.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import app as webapp
from tests.common import BaseWebTest


class TeamGeneratedAssetTests(BaseWebTest):
    def test_duplicate_first_names_get_distinct_slugs(self) -> None:
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
        self.assertEqual([member["slug"] for member in members], ["alex-s", "alex-j", "alex-x"])

    def test_qr_assets_change_only_when_team_source_changes(self) -> None:
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

    def test_vcard_omits_photo_when_member_has_no_portrait(self) -> None:
        member = {
            "name": "Jane Smith",
            "phone_digits": "12135551212",
            "email": "jane@example.com",
        }
        vcard = webapp.build_member_vcard(member, {"company": "California Earrings"})
        self.assertIn("FN:Jane Smith", vcard)
        self.assertIn("EMAIL;TYPE=INTERNET:jane@example.com", vcard)
        self.assertNotIn("PHOTO;ENCODING=b;TYPE=", vcard)
