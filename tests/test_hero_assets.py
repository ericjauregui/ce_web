import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageChops, ImageStat
from domains.image_assets import hero_image_path
from domains.file_cache import get_path_version


class HeroAssetTests(unittest.TestCase):
    def test_generated_heroes_keep_full_dimensions_and_metadata(self):
        root = Path(__file__).resolve().parents[1] / 'static'
        manifest = json.loads((root / 'optimized/hero-manifest.json').read_text())
        self.assertEqual(len(manifest), 3)
        for filename, entry in manifest.items():
            with self.subTest(filename=filename):
                self.assertEqual(get_path_version(root / filename), entry['source_version'])
                self.assertEqual(get_path_version(root / entry['path']), entry['version'])
                self.assertEqual(hero_image_path(root, filename), entry['path'])
                with Image.open(root / filename) as source, Image.open(root / entry['path']) as image:
                    self.assertEqual(source.size, image.size)
                    self.assertEqual(image.size, (entry['width'], entry['height']))
                    for key in ('icc_profile', 'exif'):
                        self.assertEqual(source.info.get(key), image.info.get(key))
                    stats = ImageStat.Stat(ImageChops.difference(source.convert('RGB'), image.convert('RGB')))
                    self.assertLess(sum(stats.mean) / 3, 2)
                self.assertLess((root / entry['path']).stat().st_size, (root / filename).stat().st_size)

    def test_missing_corrupt_or_stale_hero_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'optimized').mkdir()
            source = root / 'hero.png'
            output = root / 'optimized/hero.webp'
            source.write_bytes(b'original image')
            output.write_bytes(b'compressed image')
            entry = {'source_version': get_path_version(source), 'path': 'optimized/hero.webp', 'version': get_path_version(output)}
            (root / 'optimized/hero-manifest.json').write_text(json.dumps({'hero.png': entry}))
            self.assertEqual(hero_image_path(root, 'hero.png'), 'optimized/hero.webp')
            output.unlink()
            self.assertEqual(hero_image_path(root, 'hero.png'), 'hero.png')
            output.write_bytes(b'corrupted image')
            self.assertEqual(hero_image_path(root, 'hero.png'), 'hero.png')
            output.write_bytes(b'compressed image')
            source.write_bytes(b'replacement original')
            self.assertEqual(hero_image_path(root, 'hero.png'), 'hero.png')
