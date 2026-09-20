"""Content-addressed, prebuilt trade-show sharing images (no browser at runtime)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from domains.file_cache import get_path_version, load_json_cached

MANIFEST = "assets/social/trade-shows/manifest.json"
TEMPLATE = "templates/social/trade_show.html"
RENDERER_VERSION = 1
FIELDS = ("name", "dates_display", "start_date", "end_date", "venue", "address", "city", "booth", "hero_image", "logo_asset")
BRAND_ASSETS = ("assets/ce_logo_full.png", "vendor/fonts/lato-400-latin.woff2", "vendor/fonts/playfair-display-latin.woff2")


def static_path(static_dir: Path, relative: str) -> Path:
    path = (static_dir / relative).resolve()
    if not path.is_relative_to(static_dir.resolve()):
        raise ValueError("Social preview assets must be inside static/")
    return path


def input_fingerprint(event: dict[str, Any], static_dir: Path) -> str:
    details = {key: str(event.get(key) or "").strip() for key in FIELDS}
    assets = [*BRAND_ASSETS, details["hero_image"], details["logo_asset"]]
    versions = {asset: get_path_version(static_path(static_dir, asset)) for asset in assets}
    if any(version is None for version in versions.values()):
        raise ValueError("Missing trade-show preview source asset")
    template_version = get_path_version(static_dir.parent / TEMPLATE)
    if template_version is None:
        raise ValueError("Missing trade-show preview template")
    source = {"details": details, "assets": versions, "template": template_version, "renderer": RENDERER_VERSION}
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def current_image(event_key: str, event: dict[str, Any], static_dir: Path) -> str | None:
    """Never advertise an image containing outdated event details."""
    try:
        manifest = load_json_cached(static_dir / MANIFEST, {})
        record = manifest.get("events", {}).get(event_key, {})
        if record.get("input_fingerprint") != input_fingerprint(event, static_dir):
            return None
        image = record.get("image", "")
        if not image or get_path_version(static_path(static_dir, image)) != record.get("image_version"):
            return None
        return image
    except (ValueError, OSError, TypeError, AttributeError):
        return None
