from __future__ import annotations

from pathlib import Path
from typing import Any

from domains.catalog import Section, build_sections, filter_products
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
            sanitized_items.append({k: v for k, v in product.items() if k not in {"tags", "aliases"}})

        sanitized_sections.append(
            type(section)(
                key=section.key,
                title=section.title,
                items=sanitized_items,
            )
        )

    return sanitized_sections


def _inject_section_item_cart_qty(sections: list[Any], cart_data: dict[str, int]) -> list[Any]:
    cart_by_code = {
        str(code or "").strip(): max(0, min(999, int(qty or 0)))
        for code, qty in cart_data.items()
    }

    hydrated_sections: list[Any] = []
    for section in sections:
        hydrated_items: list[dict[str, Any]] = []
        for product in section.items:
            if not isinstance(product, dict):
                hydrated_items.append(product)
                continue

            code = str(product.get("code") or "").strip()
            hydrated_product = dict(product)
            hydrated_product["initial_qty"] = cart_by_code.get(code, 0)
            hydrated_items.append(hydrated_product)

        hydrated_sections.append(
            type(section)(
                key=section.key,
                title=section.title,
                items=hydrated_items,
            )
        )

    return hydrated_sections


def build_homepage_context(
    products: list[dict[str, Any]],
    query: str,
    collections_cfg: dict[str, Any],
    reels_path: Path,
    cart_data: dict[str, int] | None = None,
) -> dict[str, Any]:
    filtered_products = filter_products(products, query)
    if query.strip():
        sections = [Section(key="search-results", title="Search Results", items=filtered_products)]
    else:
        sections = build_sections(
            filtered_products,
            collections_cfg,
            preserve_input_order=False,
        )
    render_sections = _strip_section_item_tags_for_render(sections)
    render_sections = _inject_section_item_cart_qty(render_sections, cart_data or {})
    latest_reels = load_latest_reels(reels_path)
    return {
        "q": query,
        "sections": render_sections,
        "latest_reels": latest_reels,
    }
