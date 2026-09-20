"""Build lossless originals and proportional product sizes; sync CSS asset URLs.

Run with `.venv/bin/python -m scripts.optimize_images` after changing source
images or fonts. Originals remain authoritative; runtime falls back to them
when a generated copy is missing or stale. Hero copies stay full-resolution.
Product thumbnails use Lanczos resizing followed by lossless encoding.
"""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
HEROES = (
    "assets/hero_bg.png",
    "assets/hero_bg_mobile_compact.png",
    "assets/hero_bg_wide.png",
)
PRODUCT_WIDTHS = (160, 320, 480, 640, 960)


def product_image_files() -> list[str]:
    products = json.loads((ROOT / "catalog/products.json").read_text())
    filenames = {f"product_images/{product['image']}" for product in products}
    shows = json.loads((ROOT / "catalog/trade_shows.json").read_text())
    filenames.update(item["image"] for event in shows["events"].values()
                     for item in event.get("curated_products", [])
                     if item.get("image") and (STATIC / item["image"]).is_file())
    return sorted(filenames)


def fingerprint(data: bytes) -> str:
    return sha256(data).hexdigest()[:16]


def encode_lossless(source: bytes) -> bytes:
    with Image.open(BytesIO(source)) as image:
        pixels = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        output = BytesIO()
        metadata = {key: image.info[key] for key in ("icc_profile", "exif") if image.info.get(key)}
        pixels.save(output, "WEBP", lossless=True, exact=True, method=6, **metadata)
        data = output.getvalue()
        with Image.open(BytesIO(data)) as decoded:
            if decoded.size != pixels.size or decoded.convert(pixels.mode).tobytes() != pixels.tobytes():
                raise ValueError("Lossless image verification failed")
        return data


def build_image(filename: str, previous: dict | None = None) -> tuple[str, dict | None, int, int]:
    source = (STATIC / filename).read_bytes()
    if previous and previous["source_version"] == fingerprint(source):
        target = STATIC / previous["path"]
        if target.exists() and fingerprint(target.read_bytes()) == previous["version"]:
            return filename, previous, len(source), target.stat().st_size
    optimized = encode_lossless(source)
    if len(optimized) >= len(source):
        return filename, None, len(source), len(source)
    destination = f"optimized/{filename}.webp"
    target = STATIC / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(optimized)
    return filename, {
        "source_version": fingerprint(source),
        "path": destination,
        "version": fingerprint(optimized),
    }, len(source), len(optimized)


def build_product_sizes(filename: str) -> tuple[str, dict]:
    source = (STATIC / filename).read_bytes()
    candidates = []
    with Image.open(BytesIO(source)) as image:
        oriented = ImageOps.exif_transpose(image)
        mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
        pixels = oriented.convert(mode)
        source_width, source_height = pixels.size
        for width in PRODUCT_WIDTHS:
            if width >= source_width:
                continue  # Never upscale; the full-resolution source is the last candidate.
            height = max(1, round(source_height * width / source_width))
            resized = pixels.resize((width, height), Image.Resampling.LANCZOS)
            output = BytesIO()
            metadata = {"icc_profile": image.info["icc_profile"]} if image.info.get("icc_profile") else {}
            # EXIF stays on originals. Thumbnails have orientation baked in and
            # omit stale dimensions/embedded previews from source EXIF.
            resized.save(output, "WEBP", lossless=True, exact=True, method=6, **metadata)
            data = output.getvalue()
            with Image.open(BytesIO(data)) as decoded:
                if decoded.convert(mode).tobytes() != resized.tobytes():
                    raise ValueError(f"Lossless thumbnail verification failed: {filename}")
            if len(data) >= len(source):
                continue
            destination = f"optimized/responsive/{filename}/{width}.webp"
            target = STATIC / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            candidates.append({"path": destination, "width": width, "height": height, "version": fingerprint(data)})
    return filename, {
        "source_version": fingerprint(source),
        "width": source_width,
        "height": source_height,
        "candidates": candidates,
    }


def write_manifest(filename: str, manifest: dict) -> None:
    destination = STATIC / "optimized" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


def sync_css_asset_versions() -> None:
    # Keep the CSS URLs identical to asset_url() in HTML (including preloads).
    pattern = re.compile(r"(/static/(?:vendor/fonts/[^'\"?]+\.woff2|assets/ce_logo_shape\.png))(?:\?v=[a-f0-9]+)?")
    for filename in ("css/styles/fonts.css", "css/styles/base.css"):
        path = STATIC / filename
        source = path.read_text()

        def versioned(match: re.Match) -> str:
            asset = STATIC / match[1].removeprefix("/static/")
            return f"{match[1]}?v={fingerprint(asset.read_bytes())}"

        updated = pattern.sub(versioned, source)
        if updated != source:
            path.write_text(updated)


def main() -> None:
    products = json.loads((ROOT / "catalog/products.json").read_text())
    filenames = sorted(set(HEROES) | {f"product_images/{p['image']}" for p in products})
    manifest = {}
    previous_path = STATIC / "optimized/manifest.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    original_bytes = optimized_bytes = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        for filename, entry, before, after in executor.map(lambda name: build_image(name, previous.get(name)), filenames):
            original_bytes += before
            optimized_bytes += after
            if entry:
                manifest[filename] = entry
    write_manifest("manifest.json", manifest)
    product_files = product_image_files()
    with ThreadPoolExecutor(max_workers=4) as executor:
        responsive = dict(executor.map(build_product_sizes, product_files))
    write_manifest("responsive-manifest.json", responsive)
    sync_css_asset_versions()
    print(f"Verified {len(filenames)} images; {len(manifest)} smaller lossless alternatives. "
          f"{original_bytes:,} -> {optimized_bytes:,} bytes "
          f"({100 * (1 - optimized_bytes / original_bytes):.1f}% reduction).")
    print(f"Verified {sum(len(entry['candidates']) for entry in responsive.values())} "
          f"proportional sizes for all {len(responsive)} product images.")


if __name__ == "__main__":
    main()
