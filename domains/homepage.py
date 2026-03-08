from __future__ import annotations

from pathlib import Path
from typing import Any

from domains.catalog import build_sections, filter_products
from domains.reels import load_random_reels


def load_latest_reels(reels_path: Path, limit: int = 15) -> list[dict[str, str]]:
    return load_random_reels(reels_path, limit=limit)


def _strip_section_item_tags_for_render(sections: list[Any]) -> list[Any]:
    sanitized_sections: list[Any] = []
    for section in sections:
        sanitized_items: list[dict[str, Any]] = []
        for product in section.items:
            if not isinstance(product, dict):
                sanitized_items.append(product)
                continue
            sanitized_items.append({k: v for k, v in product.items() if k != "tags"})

        sanitized_sections.append(
            type(section)(
                key=section.key,
                title=section.title,
                items=sanitized_items,
            )
        )

    return sanitized_sections


def build_homepage_context(
    products: list[dict[str, Any]],
    query: str,
    collections_cfg: dict[str, Any],
    reels_path: Path,
) -> dict[str, Any]:
    filtered_products = filter_products(products, query)
    sections = build_sections(filtered_products, collections_cfg)
    render_sections = _strip_section_item_tags_for_render(sections)
    latest_reels = load_latest_reels(reels_path)
    return {
        "q": query,
        "sections": render_sections,
        "latest_reels": latest_reels,
    }
