"""Build/check static event previews: python -m scripts.build_trade_show_social."""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import tempfile

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from domains.file_cache import get_path_version
from domains.trade_show_social import FIELDS, MANIFEST, current_image, input_fingerprint, static_path

ROOT = Path(__file__).resolve().parent.parent


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


def build(root: Path, *, check: bool = False, event_key: str | None = None, adopt: str | None = None, force: bool = False) -> int:
    static_dir = root / "static"
    config = json.loads((root / "catalog/trade_shows.json").read_text())
    events = config["events"]
    if config["active_event"] not in events:
        raise ValueError("active_event does not name a configured show")
    if event_key and event_key not in events:
        raise ValueError(f"Unknown event: {event_key}")
    if adopt and (not event_key or check or force):
        raise ValueError("--adopt-image requires --event and cannot use --check/--force")
    selected = {event_key: events[event_key]} if event_key else events
    stale = {key: event for key, event in selected.items() if force or adopt or not current_image(key, event, static_dir)}
    if check:
        if stale:
            print("Stale/missing trade-show previews: " + ", ".join(stale))
            print("Run: uv run --extra dev python -m scripts.build_trade_show_social")
            return 1
        print("All selected trade-show previews are current.")
        return 0
    if not stale:
        print("Trade-show previews unchanged; no rendering needed.")
        return 0
    manifest_path = static_dir / MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"events": {}}

    def record(key: str, event: dict, relative: str, expected_fingerprint: str | None = None) -> None:
        validate_image(static_path(static_dir, relative))
        fingerprint = input_fingerprint(event, static_dir)
        if expected_fingerprint is not None and fingerprint != expected_fingerprint:
            raise ValueError("Preview sources changed during rendering; rerun the build")
        manifest["events"][key] = {"input_fingerprint": fingerprint, "image": relative, "image_version": get_path_version(static_dir / relative)}

    if adopt:
        record(event_key, events[event_key], adopt)
    else:
        # Imported only when an image actually needs building. Runtime and --check
        # do not require Playwright or a browser.
        from playwright.sync_api import sync_playwright
        env = Environment(loader=FileSystemLoader(root / "templates/social"), autoescape=select_autoescape(["html"]))
        def asset_data(relative: str) -> str:
            asset = static_path(static_dir, relative)
            mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
            return f"data:{mime};base64," + base64.b64encode(asset.read_bytes()).decode()
        with sync_playwright() as playwright:
            options = {"executable_path": os.environ["CE_CHROME_PATH"]} if os.environ.get("CE_CHROME_PATH") else {}
            browser = playwright.chromium.launch(headless=True, **options)
            try:
                page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
                for key, event in stale.items():
                    fingerprint = input_fingerprint(event, static_dir)
                    show = {field: str(event.get(field) or "").strip() for field in FIELDS}
                    if any(not show[field] for field in ("name", "dates_display", "venue", "city", "hero_image", "logo_asset")):
                        raise ValueError(f"Missing required preview details for {key}")
                    html = env.get_template("trade_show.html").render(show=show, asset_data=asset_data)
                    page.set_content(html)
                    page.evaluate("async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => i.decode())); }")
                    overflow = page.locator('h1, p, .pill, .proof, .card, .copy').evaluate_all("els => els.some(el => { const r=el.getBoundingClientRect(); return r.left<0 || r.right>1200 || r.top<0 || r.bottom>630 || el.scrollWidth>el.clientWidth+1; })")
                    if overflow:
                        raise ValueError(f"Preview text overflows for {key}; shorten copy or adjust templates/social/trade_show.html")
                    # Key is data, not a filesystem path.
                    safe_key = ''.join(c if c.isascii() and (c.isalnum() or c=='-') else '-' for c in key)
                    relative = f"assets/social/trade-shows/{safe_key}-{fingerprint[:16]}.jpg"
                    atomic_write(static_dir / relative, page.screenshot(type="jpeg", quality=92))
                    record(key, event, relative, fingerprint)
                    print(f"Built {relative}")
            finally:
                browser.close()
    atomic_write(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if details/assets/template changed without rebuilding')
    parser.add_argument('--event', help='Build/check one event; default is all configured shows')
    parser.add_argument('--adopt-image', help='Register a visually reviewed 1200x630 JPEG under static/ for --event')
    parser.add_argument('--force', action='store_true', help='Render even if a current approved image exists')
    args = parser.parse_args()
    return build(ROOT, check=args.check, event_key=args.event, adopt=args.adopt_image, force=args.force)


if __name__ == '__main__':
    raise SystemExit(main())
