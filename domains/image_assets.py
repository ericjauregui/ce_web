from pathlib import Path

from domains.file_cache import get_path_version, load_json_cached


# `auto` uses the measured slot for lazy images. Fallbacks cover browsers without
# auto-sizes; catalog values follow Bootstrap's container/column/gutter widths.
PRODUCT_IMAGE_SIZES = {
    "catalog": "auto, (min-width: 1400px) calc(330px - 1.5rem), "
               "(min-width: 1200px) calc(285px - 1.5rem), "
               "(min-width: 992px) calc(320px - 1.5rem), "
               "(min-width: 768px) calc(240px - 1.5rem), "
               "(min-width: 576px) calc(270px - 1.5rem), calc(50vw - 1.5rem)",
    "collection": "auto, (max-width: 767.98px) 50px, 58px",
    "cart": "auto, 56px",
    "trade": "auto, (min-width: 992px) 220px, (min-width: 768px) 240px, calc(50vw - 24px)",
}


def optimized_image_path(static_root: Path, filename: str) -> str:
    """Use a smaller lossless copy only while it matches the current original."""
    manifest = load_json_cached(static_root / "optimized" / "manifest.json", {})
    entry = manifest.get(filename)
    if not entry or entry["source_version"] != get_path_version(static_root / filename):
        return filename
    optimized = entry["path"]
    if get_path_version(static_root / optimized) != entry["version"]:
        return filename
    return optimized


def responsive_image_candidates(static_root: Path, filename: str) -> list[dict]:
    """Return current proportional sizes plus a full-resolution fallback."""
    manifest = load_json_cached(static_root / "optimized" / "responsive-manifest.json", {})
    entry = manifest.get(filename)
    if not entry or entry["source_version"] != get_path_version(static_root / filename):
        return []
    candidates = [candidate for candidate in entry["candidates"]
                  if get_path_version(static_root / candidate["path"]) == candidate["version"]]
    if not candidates:
        return []
    full_path = optimized_image_path(static_root, filename)
    candidates.append({"path": full_path, "width": entry["width"], "height": entry["height"],
                       "version": get_path_version(static_root / full_path)})
    return candidates


def hero_image_path(static_root: Path, filename: str) -> str:
    """Use the reviewed full-resolution hero; retain lossless/original fallback."""
    manifest = load_json_cached(static_root / 'optimized/hero-manifest.json', {})
    entry = manifest.get(filename)
    if (entry and entry['source_version'] == get_path_version(static_root / filename)
            and get_path_version(static_root / entry['path']) == entry['version']):
        return entry['path']
    return optimized_image_path(static_root, filename)
