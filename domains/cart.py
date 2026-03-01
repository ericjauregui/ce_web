from __future__ import annotations

import csv
import io
from pathlib import Path
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


def order_rows_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in items:
        product = row.get("product") or {}
        rows.append(
            {
                "code": str(product.get("code") or ""),
                "name": str(product.get("name") or ""),
                "quantity": int(row.get("qty") or 0),
                "notes": str(row.get("note") or ""),
                "image": str(product.get("image") or ""),
            }
        )
    return rows


def cart_to_csv_bytes(order_rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["code", "name", "quantity", "notes"])

    total_items = len(order_rows)
    total_quantity = sum(int(row.get("quantity") or 0) for row in order_rows)

    for row in order_rows:
        writer.writerow(
            [
                row.get("code", ""),
                row.get("name", ""),
                row.get("quantity", 0),
                row.get("notes", ""),
            ]
        )

    writer.writerow([])
    writer.writerow(["", "Total items:", total_items, ""])
    writer.writerow(["", "Total quantity:", total_quantity, ""])

    return buffer.getvalue().encode("utf-8")


def cart_to_pdf_bytes(order_rows: list[dict[str, Any]], product_images_dir: Path) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    elements: list[Any] = [
        Paragraph("California Earrings Order", styles["Title"]),
        Spacer(1, 10),
    ]

    table_data: list[list[Any]] = [
        ["Image", "Code", "Name", "Quantity", "Notes"]]

    total_items = len(order_rows)
    total_quantity = sum(int(row.get("quantity") or 0) for row in order_rows)

    for row in order_rows:
        image_cell: Any = ""
        image_name = str(row.get("image") or "").strip()
        image_path = product_images_dir / image_name if image_name else None
        if image_path and image_path.exists():
            try:
                image_cell = Image(str(image_path), width=34, height=34)
                image_cell.hAlign = "CENTER"
            except Exception:
                image_cell = ""

        table_data.append(
            [
                image_cell,
                row.get("code", ""),
                row.get("name", ""),
                str(row.get("quantity", 0)),
                row.get("notes", "") or "—",
            ]
        )

    table_data.append(["", "", "Total items:", str(total_items), ""])
    table_data.append(["", "", "Total quantity:", str(total_quantity), ""])

    table = Table(table_data, colWidths=[52, 76, 210, 70, 132], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1e2a3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#101010")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8d7a3e")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f8f8f8")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("FONTNAME", (2, -2), (3, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#fff8df")),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()
