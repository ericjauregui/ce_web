from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from domains.file_cache import load_json_cached
from domains.trade_show_social import current_image


def load_trade_show(
    trade_shows_path: Path,
    products: list[dict[str, Any]],
    static_dir: Path,
) -> dict[str, Any]:
    """Return the active, normalized trade-show page configuration."""
    if not trade_shows_path.exists():
        return {}

    raw = load_json_cached(trade_shows_path, {})
    if not isinstance(raw, dict):
        return {}

    events = raw.get("events") or {}
    if not isinstance(events, dict):
        return {}

    active_event = str(raw.get("active_event") or "").strip()
    source = events.get(active_event)
    if not isinstance(source, dict):
        return {}

    event = dict(source)
    event["key"] = active_event

    for key in (
        "name",
        "season",
        "dates_display",
        "start_date",
        "end_date",
        "venue",
        "address",
        "city",
        "booth",
        "official_url",
        "logo_asset",
        "hero_image",
    ):
        event[key] = str(event.get(key) or "").strip()

    required = ("name", "dates_display", "venue", "city", "logo_asset", "hero_image")
    if any(not event.get(key) for key in required):
        return {}

    event["attendance_url"] = (
        "https://wa.me/18183319292?text="
        + quote_plus(
            f"Hi California Earrings, I plan to visit you at {event['name']}. "
            "Please send me your booth details."
        )
    )
    event["updates_url"] = (
        "https://wa.me/18183319292?text="
        + quote_plus(
            f"Hi California Earrings, please keep me updated about your booth at {event['name']}."
        )
    )
    event["maps_url"] = (
        "https://www.google.com/maps/search/?api=1&query="
        + quote_plus(
            " ".join(
                part
                for part in (event["venue"], event["address"], event["city"])
                if part
            )
        )
    )

    product_index = {
        str(product.get("code") or "").strip(): product
        for product in products
        if str(product.get("code") or "").strip()
    }
    curated_products: list[dict[str, str]] = []
    raw_products = event.get("curated_products") or []
    if isinstance(raw_products, list):
        for entry in raw_products:
            item = entry if isinstance(entry, dict) else {}
            code = str(item.get("code") or "").strip()
            product = product_index.get(code)
            image = str(item.get("image") or "").strip()
            if not product or not image or not (static_dir / image).is_file():
                continue
            curated_products.append(
                {
                    "code": code,
                    "name": str(item.get("label") or product.get("name") or code).strip(),
                    "image": image,
                    "collection": str(product.get("collection") or "studs"),
                }
            )
    event["curated_products"] = curated_products

    video = event.get("video") if isinstance(event.get("video"), dict) else {}
    video_asset = str(video.get("asset") or "").strip()
    if video_asset and (static_dir / video_asset).is_file():
        event["video"] = {
            "asset": video_asset,
            "eyebrow": str(video.get("eyebrow") or "From the show floor").strip(),
            "title": str(video.get("title") or "See California Earrings at the show").strip(),
            "description": str(video.get("description") or "").strip(),
        }
    else:
        event["video"] = None

    event["social_image"] = current_image(active_event, event, static_dir) or event["hero_image"]
    return event
