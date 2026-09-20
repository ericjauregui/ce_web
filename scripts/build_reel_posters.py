"""Extract real preview frames; run after adding/replacing static/reels/*.mp4."""
from pathlib import Path
import subprocess
import sys
from io import BytesIO
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from domains.file_cache import get_path_version

ROOT = Path(__file__).resolve().parents[1]

def main():
    output = ROOT / 'static/reels/posters'
    output.mkdir(exist_ok=True)
    for source in sorted((ROOT / 'static/reels').iterdir()):
        if source.name.startswith('.') or source.suffix.lower() != '.mp4':
            continue
        target = output / f'{source.name}.{get_path_version(source)}.webp'
        if not target.exists():
            extract_frame(source, target)
        with Image.open(target) as frame:
            for width in (160, 320):
                small = target.with_name(target.stem + f'.{width}.webp')
                if small.exists() or frame.width <= width:
                    continue
                resized = frame.resize((width, round(frame.height * width / frame.width)), Image.Resampling.LANCZOS)
                resized.save(small, format='WEBP', lossless=True, method=6)
    print(f'{len(list(output.glob("*.webp")))} reel posters ready')


def extract_frame(source, target):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '0.08', '-i', str(source),
                    '-frames:v', '1', '-vf', 'scale=540:-2:force_original_aspect_ratio=decrease',
                    '-f', 'image2pipe', '-c:v', 'png', '-'], check=True, stdout=subprocess.PIPE)
    with Image.open(BytesIO(result.stdout)) as frame:
        frame.save(target, format='WEBP', lossless=True, method=6)

if __name__ == '__main__':
    main()
