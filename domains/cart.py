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
    writer.writerow(["Code", "Name", "Quantity", "Notes"])

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

    writer.writerow(
        [
            f"Total Items: {total_items}",
            "",
            f"Total Quantity: {total_quantity}",
            "",
        ]
    )

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
    logo_path = product_images_dir.parent / "assets" / "ce_logo_dark.png"
    title_style = styles["Title"].clone("OrderSummaryTitle")
    title_style.alignment = 1
    title_cell = Paragraph("Order Summary", title_style)
    logo_cell: Any = ""
    if logo_path.exists():
        try:
            logo_cell = Image(str(logo_path), width=155, height=40)
            logo_cell.hAlign = "LEFT"
        except Exception:
            logo_cell = ""

    header_side_width = 180
    header_table = Table(
        [[logo_cell, title_cell, ""]],
        colWidths=[header_side_width, doc.width - (header_side_width * 2), header_side_width],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    elements: list[Any] = [header_table, Spacer(1, 10)]

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
                image_cell = Image(str(image_path), width=40, height=40)
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

    totals_row_idx = len(table_data)
    table_data.append(
        [
            f"Total Items: {total_items}",
            "",
            "",
            f"Total Quantity: {total_quantity}",
            "",
        ]
    )

    table = Table(table_data, colWidths=[64, 76, 198, 74, 128], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1e2a3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#101010")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8d7a3e")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f8f8f8")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("SPAN", (0, totals_row_idx), (2, totals_row_idx)),
                ("SPAN", (3, totals_row_idx), (4, totals_row_idx)),
                ("FONTNAME", (0, totals_row_idx), (4, totals_row_idx), "Helvetica-Bold"),
                ("ALIGN", (0, totals_row_idx), (2, totals_row_idx), "CENTER"),
                ("ALIGN", (3, totals_row_idx), (4, totals_row_idx), "CENTER"),
                ("BACKGROUND", (0, totals_row_idx), (-1, totals_row_idx), colors.HexColor("#fff8df")),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()
