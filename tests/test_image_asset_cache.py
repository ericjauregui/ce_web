from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from domains.image_asset_cache import ImageAssetCache
from domains.file_cache import get_path_version


def version(data):
    return sha256(data).hexdigest()[:16]


class ImageAssetCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'optimized').mkdir()
        for name, data in [('source.png', b'original'), ('copy.webp', b'lossless'),
                           ('small.webp', b'thumbnail'), ('hero.webp', b'hero')]:
            (self.root / name).write_bytes(data)
        self.lossless = {'source.png': {'source_version': version(b'original'),
                         'path': 'copy.webp', 'version': version(b'lossless')}}
        self.responsive = {'source.png': {'source_version': version(b'original'),
            'width': 400, 'height': 200, 'candidates': [{'path': 'small.webp', 'width': 160,
            'height': 80, 'version': version(b'thumbnail')}]}}
        self.heroes = {'source.png': {'source_version': version(b'original'),
                       'path': 'hero.webp', 'version': version(b'hero')}}
        self.write_manifests()
        self.cache = ImageAssetCache(self.root, max_entries=2)

    def write_manifests(self):
        for name, data in [('manifest.json', self.lossless), ('responsive-manifest.json', self.responsive),
                           ('hero-manifest.json', self.heroes)]:
            (self.root / 'optimized' / name).write_text(json.dumps(data))

    def get(self, **kwargs):
        return self.cache.get('source.png', self.cache.snapshot(), **kwargs)

    def test_warm_lookup_reuses_validated_metadata(self):
        first = self.get()
        with patch('domains.image_asset_cache.get_path_version', wraps=get_path_version) as fingerprint:
            self.assertEqual(self.get(), first)
            fingerprint.assert_not_called()
        self.assertEqual(first.path, 'copy.webp')
        self.assertEqual([item[1] for item in first.candidates], [160, 400])
        with self.assertRaises(FrozenInstanceError):
            first.path = 'wrong.png'

    def test_source_change_and_missing_or_corrupt_derivatives_invalidate(self):
        self.get()
        (self.root / 'copy.webp').unlink()
        self.assertEqual(self.get().path, 'source.png')
        self.assertEqual(self.get().candidates[-1][0], 'source.png')
        (self.root / 'small.webp').write_bytes(b'corrupt thumbnail')
        self.assertEqual(self.get().candidates, ())
        (self.root / 'small.webp').write_bytes(b'thumbnail')
        self.assertEqual(len(self.get().candidates), 2)
        (self.root / 'source.png').write_bytes(b'new original')
        self.assertEqual(self.get().path, 'source.png')
        self.assertEqual(self.get().candidates, ())
        self.assertEqual(self.get().version, version(b'new original'))

    def test_manifest_replacement_and_removal_invalidate(self):
        self.get()
        (self.root / 'replacement.webp').write_bytes(b'new thumbnail')
        self.responsive['source.png']['candidates'] = [{'path': 'replacement.webp', 'width': 240,
            'version': version(b'new thumbnail')}]
        self.write_manifests()
        self.assertEqual(self.get().candidates[0][0], 'replacement.webp')
        (self.root / 'optimized/responsive-manifest.json').unlink()
        self.assertEqual(self.get().candidates, ())

    def test_hero_fallback_is_independent_from_lossless_selection(self):
        self.assertEqual(self.get(hero=True).path, 'hero.webp')
        self.assertEqual(self.get().path, 'copy.webp')
        (self.root / 'hero.webp').write_bytes(b'corrupt hero')
        self.assertEqual(self.get(hero=True).path, 'copy.webp')

    def test_concurrent_readers_and_bounded_cache(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.get(), range(24)))
        self.assertTrue(all(result == results[0] for result in results))
        for index in range(5):
            self.cache.get(f'new-{index}.png', self.cache.snapshot())
        self.assertLessEqual(len(self.cache._entries), 2)

    def test_url_cache_respects_mount_prefix_and_fresh_attributes(self):
        from tests.common import webapp
        with patch.object(webapp, '_image_assets', self.cache):
            for prefix in ('/shop', '', '/another'):
                with webapp.app.test_request_context('/', environ_overrides={'SCRIPT_NAME': prefix}):
                    src = webapp.optimized_image_url('source.png')
                    attributes = webapp.product_image_attributes('source.png')
                    self.assertTrue(src.startswith(prefix + '/static/'))
                    self.assertTrue(all(part.strip().startswith(prefix + '/static/')
                                        for part in attributes['srcset'].split(',')))
                    attributes['srcset'] = 'modified by caller'
                    self.assertNotEqual(webapp.product_image_attributes('source.png')['srcset'], attributes['srcset'])


class ImageCacheRenderingTests(unittest.TestCase):
    def test_cached_render_is_identical_with_empty_and_populated_carts(self):
        import random
        from flask import url_for
        from tests.common import webapp
        from domains.image_assets import optimized_image_path, responsive_image_candidates, PRODUCT_IMAGE_SIZES

        def original_url(filename):
            return webapp.asset_url(optimized_image_path(webapp.BASE_DIR / 'static', filename))

        def original_attributes(filename, usage='catalog'):
            candidates = responsive_image_candidates(webapp.BASE_DIR / 'static', filename)
            if not candidates:
                return {}
            return {'srcset': ', '.join(f"{url_for('static', filename=item['path'], v=item['version'])} {item['width']}w"
                                       for item in candidates), 'sizes': PRODUCT_IMAGE_SIZES[usage]}

        for cart in ({}, {'101SB': 2}):
            with self.subTest(cart=cart), webapp.app.test_client() as client:
                with client.session_transaction() as session:
                    session['cart'] = cart
                with patch.multiple(webapp, optimized_image_url=original_url, product_image_attributes=original_attributes):
                    random.seed(42)
                    original = client.get('/').data
                random.seed(42)
                cached = client.get('/').data
                self.assertEqual(original, cached)
