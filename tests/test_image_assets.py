from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from domains.image_assets import optimized_image_path, responsive_image_candidates
from scripts.optimize_images import build_product_sizes


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class OptimizedImageTests(unittest.TestCase):
    def test_responsive_manifest_covers_every_product_with_proportional_current_images(self) -> None:
        manifest = json.loads((STATIC / "optimized/responsive-manifest.json").read_text())
        products = json.loads((ROOT / "catalog/products.json").read_text())
        expected = {f"product_images/{p['image']}" for p in products}
        shows = json.loads((ROOT / "catalog/trade_shows.json").read_text())
        expected.update(item["image"] for event in shows["events"].values()
                        for item in event.get("curated_products", [])
                        if item.get("image") and (STATIC / item["image"]).is_file())
        self.assertEqual(set(manifest), expected)
        for filename, entry in manifest.items():
            with self.subTest(image=filename):
                source = STATIC / filename
                self.assertEqual(entry["source_version"], sha256(source.read_bytes()).hexdigest()[:16])
                widths = [candidate["width"] for candidate in entry["candidates"]]
                self.assertEqual(widths, sorted(set(widths)))
                self.assertTrue(widths)
                with Image.open(source) as original:
                    for candidate in entry["candidates"]:
                        target = STATIC / candidate["path"]
                        self.assertEqual(candidate["version"], sha256(target.read_bytes()).hexdigest()[:16])
                        self.assertLess(target.stat().st_size, source.stat().st_size)
                        self.assertLess(candidate["width"], entry["width"])
                        self.assertLessEqual(abs(candidate["height"] - entry["height"] * candidate["width"] / entry["width"]), 0.5)
                        with Image.open(target) as resized:
                            self.assertEqual(resized.size, (candidate["width"], candidate["height"]))
                            self.assertEqual(resized.info.get("icc_profile"), original.info.get("icc_profile"))
                            self.assertEqual(resized.format, "WEBP")

    def test_resizing_preserves_orientation_and_does_not_upscale_or_modify_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "image.png"
            image = Image.effect_noise((400, 200), 80).convert("RGB")
            exif = image.getexif()
            exif[274] = 6
            image.save(source, exif=exif)
            before = source.read_bytes()
            with patch("scripts.optimize_images.STATIC", root):
                _, entry = build_product_sizes("image.png")
                self.assertEqual((entry["width"], entry["height"]), (200, 400))
                self.assertEqual([(c["width"], c["height"]) for c in entry["candidates"]], [(160, 320)])
                with Image.open(root / entry["candidates"][0]["path"]) as thumbnail:
                    self.assertEqual(thumbnail.getexif().get(274, 1), 1)
                self.assertEqual(source.read_bytes(), before)
                image.resize((80, 40)).save(source)
                _, small = build_product_sizes("image.png")
                self.assertEqual(small["candidates"], [])

    def test_responsive_candidates_skip_missing_or_changed_files_and_reject_stale_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "optimized").mkdir()
            source = root / "source.png"
            target = root / "small.webp"
            source.write_bytes(b"source")
            target.write_bytes(b"small")
            manifest = {"source.png": {"source_version": sha256(source.read_bytes()).hexdigest()[:16],
                "width": 400, "height": 200, "candidates": [{"path": "small.webp", "width": 160, "height": 80,
                "version": sha256(target.read_bytes()).hexdigest()[:16]}]}}
            (root / "optimized/responsive-manifest.json").write_text(json.dumps(manifest))
            self.assertEqual([c["width"] for c in responsive_image_candidates(root, "source.png")], [160, 400])
            source.write_bytes(b"new source")
            self.assertEqual(responsive_image_candidates(root, "source.png"), [])
            source.write_bytes(b"source")
            target.write_bytes(b"changed")
            self.assertEqual(responsive_image_candidates(root, "source.png"), [])
            target.unlink()
            self.assertEqual(responsive_image_candidates(root, "source.png"), [])
            self.assertEqual(responsive_image_candidates(root, "new.png"), [])

    def test_every_alternative_preserves_pixels_dimensions_and_color_metadata(self) -> None:
        manifest = json.loads((STATIC / "optimized/manifest.json").read_text())
        self.assertTrue(manifest)
        for filename, entry in manifest.items():
            with self.subTest(image=filename):
                source, target = STATIC / filename, STATIC / entry["path"]
                self.assertEqual(entry["source_version"], sha256(source.read_bytes()).hexdigest()[:16])
                self.assertEqual(entry["version"], sha256(target.read_bytes()).hexdigest()[:16])
                self.assertLess(target.stat().st_size, source.stat().st_size)
                with Image.open(source) as original, Image.open(target) as optimized:
                    self.assertEqual(original.size, optimized.size)
                    self.assertEqual(original.convert("RGBA").tobytes(), optimized.convert("RGBA").tobytes())
                    self.assertEqual(original.info.get("icc_profile"), optimized.info.get("icc_profile"))
                    # JPEG prefixes the TIFF payload with Exif\0\0; WebP does not.
                    self.assertEqual(
                        original.info.get("exif", b"").removeprefix(b"Exif\x00\x00"),
                        optimized.info.get("exif", b"").removeprefix(b"Exif\x00\x00"),
                    )

    def test_new_changed_missing_or_corrupt_derivatives_fall_back_to_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "optimized").mkdir()
            source = root / "source.png"
            source.write_bytes(b"original")
            target = root / "optimized/source.webp"
            target.write_bytes(b"optimized")
            manifest = {"source.png": {
                "source_version": sha256(source.read_bytes()).hexdigest()[:16],
                "path": "optimized/source.webp",
                "version": sha256(target.read_bytes()).hexdigest()[:16],
            }}
            (root / "optimized/manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(optimized_image_path(root, "source.png"), "optimized/source.webp")
            self.assertEqual(optimized_image_path(root, "new.png"), "new.png")
            source.write_bytes(b"changed original")
            self.assertEqual(optimized_image_path(root, "source.png"), "source.png")
            source.write_bytes(b"original")
            target.write_bytes(b"corrupt derivative")
            self.assertEqual(optimized_image_path(root, "source.png"), "source.png")
            target.unlink()
            self.assertEqual(optimized_image_path(root, "source.png"), "source.png")
            (root / "optimized/manifest.json").unlink()
            self.assertEqual(optimized_image_path(root, "source.png"), "source.png")

    def test_nested_font_and_logo_urls_have_current_content_fingerprints(self) -> None:
        found = []
        for filename in ("css/styles/fonts.css", "css/styles/base.css"):
            css = (STATIC / filename).read_text()
            found.extend(re.findall(r"/static/((?:vendor/fonts/[^'\"?]+\.woff2|assets/ce_logo_shape\.png))\?v=([a-f0-9]+)", css))
        self.assertGreater(len(found), 2)
        for filename, version in found:
            self.assertEqual(version, sha256((STATIC / filename).read_bytes()).hexdigest()[:16])


if __name__ == "__main__":
    unittest.main()
