from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from domains.trade_show_social import BRAND_ASSETS, FIELDS, LOGO_SOURCES, MANIFEST, TEMPLATE, current_image
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
        shutil.copyfile(ROOT / LOGO_SOURCES, self.root / LOGO_SOURCES)
        self.save_config()
        with patch('scripts.build_trade_show_social.generate_with_api', return_value=(self.static / self.image).read_bytes()):
            build(self.root, event_key='jis-fall-2026')
        self.image = current_image('jis-fall-2026', self.event, self.static)

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

    def test_unchanged_build_does_not_write_files_or_call_api(self):
        before = (self.static / MANIFEST).stat().st_mtime_ns
        with patch('scripts.build_trade_show_social.generate_with_api', side_effect=AssertionError('Unexpected API call')), patch('scripts.build_trade_show_social.atomic_write', side_effect=AssertionError('Unexpected write')):
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

    def test_changed_details_call_gpt_images_and_checkpoint_output(self):
        self.event['booth'] = 'Booth #999'
        self.save_config()
        with patch('scripts.build_trade_show_social.generate_with_api', return_value=(self.static / self.image).read_bytes()) as api:
            self.assertEqual(build(self.root), 0)
            api.assert_called_once()
            self.assertIn('Booth #999', api.call_args.args[2])
        record = json.loads((self.static / MANIFEST).read_text())['events']['jis-fall-2026']
        self.assertEqual(record['generator'], 'gpt-images')
        self.assertTrue(record['official_logo_composited'])
        self.assertEqual(build(self.root, check=True), 0)

    def test_api_failure_preserves_manifest_and_never_uses_renderer(self):
        before = (self.static / MANIFEST).read_bytes()
        self.event['booth'] = 'Booth #999'
        self.save_config()
        with patch('scripts.build_trade_show_social.generate_with_api', side_effect=RuntimeError('API unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'API unavailable'):
                build(self.root)
        self.assertEqual((self.static / MANIFEST).read_bytes(), before)
        self.assertEqual(build(self.root, check=True), 1)

    def test_unverified_logo_is_rejected_before_billable_call(self):
        logo = self.static / self.event['logo_asset']
        logo.write_bytes(logo.read_bytes() + b'changed')
        with patch('scripts.build_trade_show_social.generate_with_api') as api:
            with self.assertRaisesRegex(ValueError, 'verified official'):
                build(self.root)
            api.assert_not_called()

    def test_browser_generated_record_is_not_current(self):
        manifest = json.loads((self.static / MANIFEST).read_text())
        manifest['events']['jis-fall-2026']['generator'] = 'browser'
        (self.static / MANIFEST).write_text(json.dumps(manifest))
        self.assertIsNone(current_image('jis-fall-2026', self.event, self.static))

    def test_api_invokes_gpt_images_cli_and_composites_original_logo(self):
        import os
        from types import SimpleNamespace
        from scripts.build_trade_show_social import generate_with_api, generation_prompt
        cli = self.root / 'image_gen.py'
        cli.write_text('# mocked CLI')
        def fake_run(command, **kwargs):
            from PIL import Image
            Image.new('RGB', (1536, 800), '#050505').save(command[command.index('--out') + 1])
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only', 'CE_IMAGE_GEN_CLI': str(cli)}), patch('scripts.build_trade_show_social.subprocess.run', side_effect=fake_run) as run:
            content = generate_with_api(self.root, self.event, generation_prompt(self.root, self.event))
        command = run.call_args.args[0]
        self.assertIn('gpt-image-2', command)
        self.assertIn('edit', command)
        self.assertNotIn(str(self.static / self.event['logo_asset']), command)
        import io
        from PIL import Image
        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.size, (1200, 630))
            # Original purple logo is present despite a completely black API output.
            colors = [image.getpixel((x, y)) for x in range(790, 1095, 3) for y in range(70, 215, 3)]
            self.assertTrue(any(r > 80 and b > 80 and g < r - 20 for r, g, b in colors))

    def test_missing_api_key_and_api_errors_do_not_fallback(self):
        import os
        from types import SimpleNamespace
        from scripts.build_trade_show_social import generate_with_api
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), patch('scripts.build_trade_show_social.load_dotenv'):
            with self.assertRaisesRegex(RuntimeError, 'OPENAI_API_KEY'):
                generate_with_api(self.root, self.event, 'prompt')
        cli = self.root / 'image_gen.py'
        cli.write_text('# mocked CLI')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private-test-token', 'CE_IMAGE_GEN_CLI': str(cli)}), patch('scripts.build_trade_show_social.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='failed private-test-token')):
            with self.assertRaises(RuntimeError) as error:
                generate_with_api(self.root, self.event, 'prompt')
            self.assertNotIn('private-test-token', str(error.exception))
            self.assertIn('[redacted]', str(error.exception))
