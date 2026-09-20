"""Generate changed event previews with GPT Images, or check existing assets."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageOps

from domains.file_cache import get_path_version
from domains.trade_show_social import FIELDS, LOGO_SOURCES, MANIFEST, REFERENCE_IMAGE, TEMPLATE, current_image, input_fingerprint, static_path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "gpt-image-2"


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(content)
        temp_path = Path(temp.name)
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def validate_image(path: Path) -> None:
    with Image.open(path) as image:
        if image.format != "JPEG" or image.size != (1200, 630):
            raise ValueError("Preview must be a 1200x630 JPEG")
        image.verify()


def generation_prompt(root: Path, event: dict) -> str:
    details = {key: str(event.get(key) or "").strip() for key in FIELDS}
    if any(not details[key] for key in ('name', 'dates_display', 'venue', 'city', 'hero_image', 'logo_asset')):
        raise ValueError("Missing required event details")
    details['booth'] = details['booth'] or 'Booth details coming soon'
    cta = 'Meet Us at the Show' if 'coming soon' in details['booth'].lower() else 'Meet Us at ' + details['booth']
    return (root / TEMPLATE).read_text().format(**details, details_json=json.dumps(details, ensure_ascii=False), cta=cta)


def official_logo(root: Path, event: dict) -> Image.Image:
    records = json.loads((root / LOGO_SOURCES).read_text())
    source = records.get(event['logo_asset'])
    path = static_path(root / 'static', event['logo_asset'])
    if not source or hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('Event logo must match verified official website artwork; update catalog/trade_show_logo_sources.json')
    with Image.open(path) as logo:
        logo = logo.convert('RGBA')
        bounds = logo.getchannel('A').getbbox()
        return logo.crop(bounds) if bounds else logo


def compose_official_logo(root: Path, event: dict, content: bytes) -> bytes:
    # Only the logo is composited. All layout, copy and scenery come from GPT Images.
    with Image.open(io.BytesIO(content)) as generated:
        canvas = generated.convert('RGB').resize((1200, 630), Image.Resampling.LANCZOS)
    # Inset within the requested blank region to allow small model layout shifts.
    ImageDraw.Draw(canvas).rectangle((790, 75, 1045, 210), fill='#050505')
    logo = ImageOps.contain(official_logo(root, event), (230, 110), Image.Resampling.LANCZOS)
    canvas.paste(logo, (790 + (255-logo.width)//2, 75 + (135-logo.height)//2), logo)
    encoded = io.BytesIO()
    canvas.save(encoded, format='JPEG', quality=94)
    return encoded.getvalue()


def generate_with_api(root: Path, event: dict, prompt: str) -> bytes:
    """Use the installed ImageGen CLI, never a browser/template fallback."""
    load_dotenv(root / '.env', override=False)
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('OPENAI_API_KEY is required. Set it locally (never commit it) and retry.')
    codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    cli = Path(os.environ.get('CE_IMAGE_GEN_CLI', str(codex_home / 'skills/.system/imagegen/scripts/image_gen.py')))
    if not cli.is_file():
        raise RuntimeError('GPT Images CLI missing. Set CE_IMAGE_GEN_CLI to the installed imagegen/scripts/image_gen.py.')
    with tempfile.TemporaryDirectory(prefix='ce-gpt-images-') as directory:
        temp = Path(directory)
        prompt_path = temp / 'prompt.txt'
        prompt_path.write_text(prompt)
        output = temp / 'generated.png'
        command = [sys.executable, str(cli), 'edit', '--model', MODEL,
                   '--prompt-file', str(prompt_path), '--quality', 'high',
                   '--size', '1536x800', '--output-format', 'png', '--out', str(output)]
        for relative in (REFERENCE_IMAGE, event['hero_image'], 'assets/ce_logo_full.png'):
            command.extend(['--image', str(static_path(root / 'static', relative))])
        result = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
        if result.returncode:
            detail = (result.stderr or result.stdout)[-2000:].replace(key, '[redacted]')
            raise RuntimeError('GPT Images generation failed; existing previews were preserved.\n' + detail)
        # Normalize the generated image, then place the verified official logo.
        with Image.open(output) as image:
            image.load()
            if image.width < 1200 or image.height < 630:
                raise ValueError('GPT Images returned an undersized image')
            return compose_official_logo(root, event, output.read_bytes())


def build(root: Path, *, check: bool = False, event_key: str | None = None, force: bool = False) -> int:
    static_dir = root / 'static'
    config = json.loads((root / 'catalog/trade_shows.json').read_text())
    events = config['events']
    if config['active_event'] not in events:
        raise ValueError('active_event does not name a configured show')
    if event_key and event_key not in events:
        raise ValueError(f'Unknown event: {event_key}')
    selected = {event_key: events[event_key]} if event_key else events
    stale = {key: event for key, event in selected.items() if force or not current_image(key, event, static_dir)}
    if check:
        if stale:
            print('Stale/missing GPT Images previews: ' + ', '.join(stale))
            print('Run: uv run --extra dev --extra imagegen python -m scripts.build_trade_show_social')
            return 1
        print('All selected GPT Images previews are current.')
        return 0
    if not stale:
        print('GPT Images previews unchanged; no API calls needed.')
        return 0
    manifest_path = static_dir / MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'events': {}}
    for event_id, event in stale.items():
        fingerprint = input_fingerprint(event, static_dir)
        prompt = generation_prompt(root, event)
        official_logo(root, event)  # Validate provenance before any billable call.
        print(f'Generating {event_id} with {MODEL} (may take a few minutes)...', flush=True)
        content = generate_with_api(root, event, prompt)
        if input_fingerprint(event, static_dir) != fingerprint:
            raise ValueError('Source assets changed during generation; retry')
        latest = json.loads((root / 'catalog/trade_shows.json').read_text())['events'].get(event_id, {})
        if input_fingerprint(latest, static_dir) != fingerprint:
            raise ValueError('Event details changed during generation; retry')
        safe_key = ''.join(c if c.isascii() and (c.isalnum() or c == '-') else '-' for c in event_id)
        relative = f'assets/social/trade-shows/{safe_key}-{fingerprint[:12]}-{hashlib.sha256(content).hexdigest()[:8]}.jpg'
        atomic_write(static_dir / relative, content)
        validate_image(static_dir / relative)
        method = f'OpenAI API / {MODEL}'
        prompt_relative = str(Path(relative).with_suffix('.prompt.txt'))
        atomic_write(static_dir / prompt_relative, prompt.encode())
        manifest['events'][event_id] = {
            'input_fingerprint': fingerprint, 'image': relative,
            'image_version': get_path_version(static_dir / relative),
            'generator': 'gpt-images', 'method': method, 'prompt': prompt_relative,
            'official_logo_composited': True, 'logo_source': event['logo_asset'],
        }
        # Checkpoint each successful event so a later API failure won't bill it again.
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + '\n').encode())
        print(f'Updated {relative}', flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only freshness check; no API calls')
    parser.add_argument('--event', help='Generate/check one event; default is all configured shows')
    parser.add_argument('--force', action='store_true', help='Regenerate with GPT Images even if current (billable)')
    args = parser.parse_args()
    try:
        return build(ROOT, check=args.check, event_key=args.event, force=args.force)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
