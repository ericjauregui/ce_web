"""Isolation checks for preview generation failures absent from public pages.

Failure modes: stale or malformed source manifests serve outdated show details;
unchanged inputs trigger billable generation; an unverified logo reaches the
API; API failure damages the last good manifest; a failed subprocess leaks its
secret; generated artwork omits the verified official logo; unsafe asset paths
escape the static tree. Browser E2E covers the committed successful previews.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

from domains.trade_show_social import BRAND_ASSETS, FIELDS, LOGO_SOURCES, MANIFEST, TEMPLATE, current_image
from scripts.build_trade_show_social import ROOT, build, generate_with_api, generation_prompt


class TradeShowSocialSafetyTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.static = self.root / "static"
        config = json.loads((ROOT / "catalog/trade_shows.json").read_text())
        self.event = config["events"]["jis-fall-2026"]
        self.config = {"active_event": "jis-fall-2026", "events": {"jis-fall-2026": self.event}}
        self.image = "assets/social/trade-shows-jis-fall-v3.jpg"
        for relative in [*BRAND_ASSETS, self.event["hero_image"], self.event["logo_asset"], self.image]:
            target = self.static / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "static" / relative, target)
        target = self.root / TEMPLATE
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / TEMPLATE, target)
        shutil.copyfile(ROOT / LOGO_SOURCES, self.root / LOGO_SOURCES)
        self._save_config()
        with patch("scripts.build_trade_show_social.generate_with_api", return_value=(self.static / self.image).read_bytes()):
            build(self.root, event_key="jis-fall-2026")
        self.image = current_image("jis-fall-2026", self.event, self.static)

    def _save_config(self) -> None:
        source = self.root / "catalog/trade_shows.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(json.dumps(self.config))

    def test_committed_previews_are_current(self) -> None:
        self.assertEqual(build(ROOT, check=True), 0)

    def test_changed_inputs_and_broken_manifest_invalidate_preview(self) -> None:
        for field in FIELDS:
            with self.subTest(field=field):
                changed = {**self.event, field: self.event.get(field, "") + " changed"}
                self.assertIsNone(current_image("jis-fall-2026", changed, self.static))

        for path in (self.static / self.event["hero_image"], self.root / TEMPLATE):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                self.assertIsNone(current_image("jis-fall-2026", self.event, self.static))
                path.write_bytes(original)

        self.assertEqual(current_image("jis-fall-2026", self.event, self.static), self.image)
        outside = {**self.event, "hero_image": "../catalog/trade_shows.json"}
        self.assertIsNone(current_image("jis-fall-2026", outside, self.static))
        (self.static / MANIFEST).write_text("not json")
        self.assertIsNone(current_image("jis-fall-2026", self.event, self.static))

    def test_unchanged_inputs_never_bill_or_rewrite(self) -> None:
        manifest_path = self.static / MANIFEST
        before = manifest_path.read_bytes()
        with patch("scripts.build_trade_show_social.generate_with_api", side_effect=AssertionError("Unexpected API call")), patch(
            "scripts.build_trade_show_social.atomic_write", side_effect=AssertionError("Unexpected write")
        ):
            self.assertEqual(build(self.root), 0)
        self.assertEqual(manifest_path.read_bytes(), before)

    def test_failure_and_unverified_logo_preserve_last_good_manifest(self) -> None:
        manifest_path = self.static / MANIFEST
        before = manifest_path.read_bytes()
        self.event["booth"] = "Booth #999"
        self._save_config()
        with patch("scripts.build_trade_show_social.generate_with_api", side_effect=RuntimeError("API unavailable")):
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                build(self.root)
        self.assertEqual(manifest_path.read_bytes(), before)
        self.assertEqual(build(self.root, check=True), 1)

        logo = self.static / self.event["logo_asset"]
        logo.write_bytes(logo.read_bytes() + b"changed")
        with patch("scripts.build_trade_show_social.generate_with_api") as api:
            with self.assertRaisesRegex(ValueError, "verified official"):
                build(self.root)
            api.assert_not_called()
        self.assertEqual(manifest_path.read_bytes(), before)

    def test_generator_redacts_secret_and_composites_verified_logo(self) -> None:
        cli = self.root / "image_gen.py"
        cli.write_text("# mocked CLI")

        def fake_success(command, **_kwargs):
            Image.new("RGB", (1536, 800), "#050505").save(command[command.index("--out") + 1])
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "private-test-token", "CE_IMAGE_GEN_CLI": str(cli)}), patch(
            "scripts.build_trade_show_social.subprocess.run", side_effect=fake_success
        ):
            content = generate_with_api(self.root, self.event, generation_prompt(self.root, self.event))
        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.size, (1200, 630))
            colors = [image.getpixel((x, y)) for x in range(790, 1095, 3) for y in range(70, 215, 3)]
            self.assertTrue(any(r > 80 and b > 80 and g < r - 20 for r, g, b in colors))

        with patch.dict("os.environ", {"OPENAI_API_KEY": "private-test-token", "CE_IMAGE_GEN_CLI": str(cli)}), patch(
            "scripts.build_trade_show_social.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout="", stderr="failed private-test-token"),
        ):
            with self.assertRaises(RuntimeError) as error:
                generate_with_api(self.root, self.event, "prompt")
        self.assertNotIn("private-test-token", str(error.exception))
        self.assertIn("[redacted]", str(error.exception))
