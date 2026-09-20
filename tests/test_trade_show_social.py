from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from domains.trade_show_social import BRAND_ASSETS, FIELDS, MANIFEST, TEMPLATE, current_image
from scripts.build_trade_show_social import ROOT, build


class TradeShowSocialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.static = self.root / 'static'
        self.config = json.loads((ROOT / 'catalog/trade_shows.json').read_text())
        self.event = self.config['events']['jis-fall-2026']
        self.config = {'active_event': 'jis-fall-2026', 'events': {'jis-fall-2026': self.event}}
        self.image = 'assets/social/trade-shows-jis-fall-v3.jpg'
        for relative in [*BRAND_ASSETS, self.event['hero_image'], self.event['logo_asset'], self.image]:
            target = self.static / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'static' / relative, target)
        target = self.root / TEMPLATE
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / TEMPLATE, target)
        (self.root / 'catalog').mkdir()
        self.save_config()
        build(self.root, event_key='jis-fall-2026', adopt=self.image)

    def save_config(self):
        (self.root / 'catalog/trade_shows.json').write_text(json.dumps(self.config))

    def test_all_committed_show_previews_are_current(self):
        self.assertEqual(build(ROOT, check=True), 0)

    def test_every_show_detail_change_invalidates_preview(self):
        for field in FIELDS:
            with self.subTest(field=field):
                event = {**self.event, field: self.event.get(field, '') + ' changed'}
                self.assertIsNone(current_image('jis-fall-2026', event, self.static))
        self.assertEqual(current_image('jis-fall-2026', self.event, self.static), self.image)

    def test_unrelated_video_edit_does_not_rebuild(self):
        changed = copy.deepcopy(self.event)
        changed['video'] = {'description': 'Updated welcome'}
        self.assertEqual(current_image('jis-fall-2026', changed, self.static), self.image)

    def test_image_asset_and_template_changes_are_detected(self):
        for path in [self.static / self.event['hero_image'], self.static / self.image, self.root / TEMPLATE]:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                self.assertIsNone(current_image('jis-fall-2026', self.event, self.static))
                path.write_bytes(original)
        self.assertEqual(current_image('jis-fall-2026', self.event, self.static), self.image)

    def test_missing_output_and_malformed_manifest_are_safe(self):
        (self.static / self.image).unlink()
        self.assertIsNone(current_image('jis-fall-2026', self.event, self.static))
        (self.static / MANIFEST).write_text('not json')
        self.assertIsNone(current_image('jis-fall-2026', self.event, self.static))

    def test_check_fails_for_changed_details_without_rendering(self):
        self.event['booth'] = 'Booth #999'
        self.save_config()
        self.assertEqual(build(self.root, check=True), 1)

    def test_unchanged_build_does_not_write_files_or_launch_browser(self):
        before = (self.static / MANIFEST).stat().st_mtime_ns
        with patch('scripts.build_trade_show_social.atomic_write', side_effect=AssertionError('Unexpected write')):
            self.assertEqual(build(self.root), 0)
        self.assertEqual((self.static / MANIFEST).stat().st_mtime_ns, before)

    def test_changing_active_event_selects_its_own_preview(self):
        config = json.loads((ROOT / 'catalog/trade_shows.json').read_text())
        images = [current_image(key, event, ROOT / 'static') for key, event in config['events'].items()]
        self.assertTrue(all(images))
        self.assertEqual(len(set(images)), 3)

    def test_outside_static_assets_are_rejected(self):
        event = {**self.event, 'hero_image': '../catalog/trade_shows.json'}
        self.assertIsNone(current_image('jis-fall-2026', event, self.static))
