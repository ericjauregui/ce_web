from __future__ import annotations

import csv
import io
from typing import Any


MAX_ITEM_NOTE_LENGTH = 500


def get_cart(session_obj: Any) -> dict[str, int]:
    cart = session_obj.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
    clean: dict[str, int] = {}
    for code, qty in cart.items():
        try:
            parsed_qty = int(qty)
        except Exception:
            parsed_qty = 0
        if parsed_qty > 0:
            clean[code] = max(1, min(999, parsed_qty))
    session_obj["cart"] = clean
    return clean


def cart_total_items(cart: dict[str, int]) -> int:
    return int(sum(cart.values()))


def normalize_item_note(note: Any) -> str:
    text = str(note or "").strip()
    return text[:MAX_ITEM_NOTE_LENGTH]


def get_cart_notes(session_obj: Any, cart: dict[str, int]) -> dict[str, str]:
    raw_notes = session_obj.get("cart_notes", {})
    if not isinstance(raw_notes, dict):
        raw_notes = {}

    clean: dict[str, str] = {}
    for code, note in raw_notes.items():
        if code not in cart:
            continue
        normalized = normalize_item_note(note)
        if normalized:
            clean[code] = normalized

    session_obj["cart_notes"] = clean
    return clean


def cart_items(product_map: dict[str, dict[str, Any]], cart: dict[str, int], notes: dict[str, str] | None = None) -> list[dict[str, Any]]:
    notes = notes or {}
    items: list[dict[str, Any]] = []
    for code, qty in cart.items():
        product = product_map.get(code)
        if product:
            items.append({"product": product, "qty": qty, "note": notes.get(code, "")})
    return items


def cart_to_csv_bytes(meta: dict[str, str], items: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", meta.get("name", "")])
    writer.writerow(["company", meta.get("company", "")])
    writer.writerow(["phone", meta.get("phone", "")])
    writer.writerow(["notes", meta.get("notes", "")])
    writer.writerow([])
    writer.writerow(["code", "name", "qty", "notes", "collection", "material", "stone", "size_mm"])

    for row in items:
        product = row["product"]
        writer.writerow(
            [
                product.get("code", ""),
                product.get("name", ""),
                row["qty"],
                row.get("note", ""),
                product.get("collection", ""),
                product.get("material", ""),
                product.get("stone", ""),
                product.get("size_mm", ""),
            ]
        )

    return buffer.getvalue().encode("utf-8")
