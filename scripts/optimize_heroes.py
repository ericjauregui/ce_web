"""Build quality-first full-resolution hero WebPs with cwebp (libwebp).

Run: uv run python -m scripts.optimize_heroes
No resizing, cropping, composition edits, or changes to responsive breakpoints.
"""
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageChops, ImageStat
from scripts.optimize_images import HEROES, STATIC, fingerprint, write_manifest

QUALITY = 98


def main():
    manifest = {}
    with tempfile.TemporaryDirectory() as directory:
        for filename in HEROES:
            source = STATIC / filename
            output = Path(directory) / (source.name + '.webp')
            subprocess.run(['cwebp', '-quiet', '-q', str(QUALITY), '-m', '6',
                            '-sharp_yuv', '-metadata', 'all', str(source), '-o', str(output)], check=True)
            with Image.open(source) as original, Image.open(output) as decoded:
                if original.size != decoded.size:
                    raise ValueError(f'Hero dimensions changed: {filename}')
                for key in ('icc_profile', 'exif'):
                    if original.info.get(key) != decoded.info.get(key):
                        raise ValueError(f'Hero metadata changed: {filename}: {key}')
                difference = ImageStat.Stat(ImageChops.difference(original.convert('RGB'), decoded.convert('RGB')))
                error = sum(difference.mean) / 3
                # An asset-integrity guard, not a substitute for visual review.
                if error > 2:
                    raise ValueError(f'Hero requires visual review/new encoding settings: {filename}')
                width, height = original.size
            data = output.read_bytes()
            if len(data) >= source.stat().st_size:
                raise ValueError(f'No size improvement: {filename}')
            destination = f'optimized/heroes/{source.name}.webp'
            target = STATIC / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest[filename] = {'source_version': fingerprint(source.read_bytes()),
                                  'path': destination, 'version': fingerprint(data),
                                  'width': width, 'height': height, 'quality': QUALITY,
                                  'sharp_yuv': True, 'mean_channel_error': error}
            print(f'{filename}: {width}x{height}, {len(data):,} bytes, mean channel error {error:.3f}/255')
    write_manifest('hero-manifest.json', manifest)


if __name__ == '__main__':
    main()
