from pathlib import Path
import tempfile
import unittest
from domains.file_cache import get_path_version
from domains.reels import discover_reels
from domains.stylesheets import bootstrap_stylesheet


class LoadingAssetTests(unittest.TestCase):
    def test_poster_is_used_only_for_current_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / 'clip.mp4'
            video.write_bytes(b'first clip')
            (root / 'posters').mkdir()
            poster = root / 'posters' / f'clip.mp4.{get_path_version(video)}.webp'
            poster.write_bytes(b'frame')
            self.assertIn('poster', discover_reels(root)[0])
            video.write_bytes(b'replacement clip')
            self.assertNotIn('poster', discover_reels(root)[0])

    def test_bootstrap_falls_back_when_sources_change(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'static/css').mkdir(parents=True)
            (root / 'app.py').write_text('original')
            output = root / 'static/css/bootstrap.site.min.css'
            output.write_text('.btn{display:block}')
            manifest = {str(p.relative_to(root)): get_path_version(p) for p in [root / 'app.py', output]}
            (root / 'static/css/bootstrap.site.manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(bootstrap_stylesheet(root), 'css/bootstrap.site.min.css')
            (root / 'app.py').write_text('changed class names')
            self.assertEqual(bootstrap_stylesheet(root), 'vendor/bootstrap/bootstrap.min.css')

    def test_shipped_posters_decode_and_cover_every_reel(self):
        from PIL import Image
        root = Path(__file__).resolve().parents[1] / 'static'
        for reel in discover_reels(root / 'reels'):
            self.assertIn('poster', reel)
            with Image.open(root / reel['poster']) as image:
                size = image.size
                image.verify()
            for width in (160, 320):
                if size[0] <= width:
                    continue
                with Image.open(root / reel[f'poster_{width}']) as image:
                    self.assertEqual(image.width, width)
                    self.assertEqual(image.height, round(size[1] * width / size[0]))
                    image.verify()
