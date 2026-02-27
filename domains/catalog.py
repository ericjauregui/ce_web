from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Section:
    key: str
    title: str
    items: list[dict[str, Any]]


def normalize_product(product: dict[str, Any]) -> dict[str, Any]:
    code = (product.get("code") or "").strip()
    name = (product.get("name") or "").strip() or code
    description = (product.get("description") or "").strip()
    collection = (product.get("collection") or "other").strip() or "other"
    image = (product.get("image") or "").strip()
    tags = product.get("tags") or []
    if not isinstance(tags, list):
        tags = []

    output = dict(product)
    output.update(
        {
            "id": code.lower(),
            "code": code,
            "name": name,
            "description": description,
            "collection": collection,
            "image": image,
            "tags": tags,
        }
    )
    return output


def load_products(catalog_path: Path) -> list[dict[str, Any]]:
    with open(catalog_path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    return [normalize_product(item) for item in (raw or [])]


def products_by_code(products: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_code: dict[str, dict[str, Any]] = {}
    for product in products:
        code = product.get("code")
        if isinstance(code, str) and code:
            by_code[code] = product
    return by_code


def find_product_by_code(products: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
    target = (code or "").strip().lower()
    if not target:
        return None

    for product in products:
        product_code = str(product.get("code") or "").strip().lower()
        if product_code == target:
            return product

    return None


def load_social(social_path: Path) -> dict[str, Any]:
    if social_path.exists():
        with open(social_path, "r", encoding="utf-8") as file:
            return json.load(file)
    return {"tiktok": {"profile_url": "", "videos": []}, "instagram": {"profile_url": "", "reels_url": ""}}


def load_collections_cfg(collections_path: Path) -> dict[str, Any]:
    if collections_path.exists():
        with open(collections_path, "r", encoding="utf-8") as file:
            return json.load(file)
    return {"order": [], "labels": {}}


def filter_products(products: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return products

    output: list[dict[str, Any]] = []
    for product in products:
        haystack = " ".join(
            [
                str(product.get("code", "")),
                str(product.get("name", "")),
                str(product.get("collection", "")),
                str(product.get("description", "")),
                " ".join(product.get("tags", []) or []),
            ]
        ).lower()
        if normalized_query in haystack:
            output.append(product)
    return output


def build_sections(products: list[dict[str, Any]], cfg: dict[str, Any]) -> list[Section]:
    order: list[str] = cfg.get("order") or []
    labels: dict[str, str] = cfg.get("labels") or {}

    by_collection: dict[str, list[dict[str, Any]]] = {}
    for product in products:
        by_collection.setdefault(product.get("collection", "other"), []).append(product)

    sections: list[Section] = []
    for key in order:
        items = by_collection.get(key, [])
        if items:
            sections.append(Section(key=key, title=labels.get(key, key.replace("-", " ").title()), items=items))

    for key, items in by_collection.items():
        if key in set(order):
            continue
        sections.append(Section(key=key, title=labels.get(key, key.replace("-", " ").title()), items=items))

    return sections
