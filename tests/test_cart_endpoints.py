from __future__ import annotations

import re
import sys
import types
from unittest.mock import patch

import app as webapp
from domains import cart as cart_domain
from tests.common import BaseWebTest


class CartEndpointTests(BaseWebTest):
    def test_index_renders_catalog_and_script(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("product-grid-row", body)
        self.assertIn("/static/js/catalog.js", body)

    def test_add_set_and_count_flow(self) -> None:
        add_response = self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 2})
        self.assertEqual(add_response.status_code, 200)
        add_data = add_response.get_json()
        self.assertTrue(add_data["ok"])
        self.assertEqual(add_data["total_items"], 2)
        self.assertEqual(add_data["distinct_items"], 1)

        set_response = self.client.post("/api/cart/set", json={"code": self.valid_code, "qty": 5})
        self.assertEqual(set_response.status_code, 200)
        set_data = set_response.get_json()
        self.assertEqual(set_data["total_items"], 5)
        self.assertEqual(set_data["distinct_items"], 1)

        count_response = self.client.get("/api/cart/count")
        self.assertEqual(count_response.status_code, 200)
        count_data = count_response.get_json()
        self.assertEqual(count_data["total_items"], 5)
        self.assertEqual(count_data["distinct_items"], 1)

    def test_set_zero_clears_item_in_single_request(self) -> None:
        self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 4})

        clear_response = self.client.post("/api/cart/set", json={"code": self.valid_code, "qty": 0})
        self.assertEqual(clear_response.status_code, 200)
        clear_data = clear_response.get_json()
        self.assertEqual(clear_data["total_items"], 0)
        self.assertEqual(clear_data["distinct_items"], 0)

        count_response = self.client.get("/api/cart/count")
        self.assertEqual(count_response.status_code, 200)
        count_data = count_response.get_json()
        self.assertEqual(count_data["total_items"], 0)
        self.assertEqual(count_data["distinct_items"], 0)

    def test_clear_endpoint_empties_cart(self) -> None:
        self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 3})

        clear_response = self.client.post("/api/cart/clear", json={})
        self.assertEqual(clear_response.status_code, 200)
        clear_data = clear_response.get_json()
        self.assertTrue(clear_data["ok"])
        self.assertEqual(clear_data["total_items"], 0)
        self.assertEqual(clear_data["distinct_items"], 0)

        count_response = self.client.get("/api/cart/count")
        self.assertEqual(count_response.status_code, 200)
        count_data = count_response.get_json()
        self.assertEqual(count_data["total_items"], 0)
        self.assertEqual(count_data["distinct_items"], 0)

    def test_unknown_code_is_rejected(self) -> None:
        response = self.client.post("/api/cart/add", json={"code": "NOT_A_CODE", "qty": 1})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "unknown_code")

    def test_item_note_round_trip_in_cart_view(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 1})

        note_response = self.client.post(
            "/api/cart/note",
            json={"code": self.valid_code,
                  "note": "Please match screwback style"},
        )
        self.assertEqual(note_response.status_code, 200)
        note_data = note_response.get_json()
        self.assertTrue(note_data["ok"])
        self.assertEqual(note_data["note"], "Please match screwback style")

        cart_response = self.client.get("/cart")
        self.assertEqual(cart_response.status_code, 200)
        cart_body = cart_response.get_data(as_text=True)
        self.assertIn("item-note-input", cart_body)
        self.assertIn("Please match screwback style", cart_body)

    def test_item_note_requires_item_in_cart(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 1})
        self.client.post("/api/cart/remove", json={"code": self.valid_code})

        response = self.client.post(
            "/api/cart/note",
            json={"code": self.valid_code, "note": "should fail"},
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "item_not_in_cart")

    def test_checkout_csv_includes_per_item_note_column(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 2})
        self.client.post(
            "/api/cart/note",
            json={"code": self.valid_code, "note": "Need matching pair"},
        )

        checkout_response = self.client.post(
            "/checkout",
            data={
                "name": "Test Buyer",
                "company": "Sample Co",
                "phone": "555-0101",
                "notes": "general order note",
            },
        )
        self.assertEqual(checkout_response.status_code, 200)

        with self.client.session_transaction() as sess:
            token = sess.get("last_order_token")

        self.assertTrue(token)
        csv_response = self.client.get(f"/download/order/{token}.csv")
        self.assertEqual(csv_response.status_code, 200)
        csv_text = csv_response.get_data(as_text=True)

        self.assertIn("Notes", csv_text)
        self.assertIn("Need matching pair", csv_text)
        self.assertIn("Code,Name,Quantity,Notes", csv_text)
        self.assertNotIn("collection", csv_text)
        self.assertNotIn("material", csv_text)
        self.assertNotIn("size_mm", csv_text)

    def test_checkout_pdf_download_endpoint_returns_pdf(self) -> None:
        self.client.post(
            "/api/cart/add", json={"code": self.valid_code, "qty": 1})

        checkout_response = self.client.post(
            "/checkout",
            data={
                "name": "Test Buyer",
                "company": "Sample Co",
                "phone": "555-0101",
                "notes": "general order note",
            },
        )
        self.assertEqual(checkout_response.status_code, 200)

        with self.client.session_transaction() as sess:
            token = sess.get("last_order_token")

        self.assertTrue(token)
        pdf_response = self.client.get(f"/download/order/{token}.pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertTrue(pdf_response.get_data().startswith(b"%PDF"))

    def test_cart_pdf_layout_centers_title_and_all_table_cells(self) -> None:
        class FakeStyle:
            def __init__(self, name: str) -> None:
                self.name = name
                self.alignment: int | None = None

            def clone(self, name: str) -> "FakeStyle":
                cloned = FakeStyle(name)
                cloned.alignment = self.alignment
                return cloned

        class FakeParagraph:
            def __init__(self, text: str, style: FakeStyle) -> None:
                self.text = text
                self.style = style

        class FakeImage:
            def __init__(self, path: str, width: int, height: int) -> None:
                self.path = path
                self.width = width
                self.height = height
                self.hAlign: str | None = None

        class FakeTableStyle:
            def __init__(self, commands: list[tuple[object, ...]]) -> None:
                self.commands = commands

        class FakeTable:
            instances: list["FakeTable"] = []

            def __init__(self, data: list[list[object]], colWidths: list[float] | None = None, repeatRows: int = 0) -> None:
                self.data = data
                self.colWidths = colWidths
                self.repeatRows = repeatRows
                self.styles: list[tuple[object, ...]] = []
                FakeTable.instances.append(self)

            def setStyle(self, style: FakeTableStyle) -> None:
                self.styles.extend(style.commands)

        class FakeSimpleDocTemplate:
            def __init__(
                self,
                buffer: object,
                pagesize: tuple[int, int],
                leftMargin: int,
                rightMargin: int,
                topMargin: int,
                bottomMargin: int,
            ) -> None:
                self.buffer = buffer
                self.width = pagesize[0] - leftMargin - rightMargin

            def build(self, elements: list[object]) -> None:
                self.buffer.write(b"%PDF-test")

        def fake_styles() -> dict[str, FakeStyle]:
            return {"Title": FakeStyle("Title")}

        fake_colors = types.ModuleType("reportlab.lib.colors")
        fake_colors.white = "white"
        fake_colors.HexColor = lambda value: value

        fake_pagesizes = types.ModuleType("reportlab.lib.pagesizes")
        fake_pagesizes.letter = (612, 792)

        fake_styles_module = types.ModuleType("reportlab.lib.styles")
        fake_styles_module.getSampleStyleSheet = fake_styles

        fake_platypus = types.ModuleType("reportlab.platypus")
        fake_platypus.Image = FakeImage
        fake_platypus.Paragraph = FakeParagraph
        fake_platypus.SimpleDocTemplate = FakeSimpleDocTemplate
        fake_platypus.Spacer = lambda width, height: (width, height)
        fake_platypus.Table = FakeTable
        fake_platypus.TableStyle = FakeTableStyle

        fake_reportlab = types.ModuleType("reportlab")
        fake_reportlab_lib = types.ModuleType("reportlab.lib")
        fake_reportlab_lib.colors = fake_colors
        fake_reportlab_lib.pagesizes = fake_pagesizes
        fake_reportlab_lib.styles = fake_styles_module

        FakeTable.instances.clear()
        order_rows = [{"code": "102SB", "name": "Classic Gold Diamond Studs", "quantity": 4, "notes": "", "image": ""}]
        product_images_dir = webapp.BASE_DIR / "static" / "product_images"

        with patch.dict(
            sys.modules,
            {
                "reportlab": fake_reportlab,
                "reportlab.lib": fake_reportlab_lib,
                "reportlab.lib.colors": fake_colors,
                "reportlab.lib.pagesizes": fake_pagesizes,
                "reportlab.lib.styles": fake_styles_module,
                "reportlab.platypus": fake_platypus,
            },
        ):
            pdf_bytes = cart_domain.cart_to_pdf_bytes(order_rows, product_images_dir)

        self.assertEqual(pdf_bytes, b"%PDF-test")
        self.assertEqual(len(FakeTable.instances), 2)

        header_table = FakeTable.instances[0]
        order_table = FakeTable.instances[1]

        self.assertEqual(header_table.colWidths, [180, 192, 180])
        title_cell = header_table.data[0][1]
        self.assertEqual(title_cell.text, "Order Summary")
        self.assertEqual(title_cell.style.alignment, 1)
        self.assertIn(("ALIGN", (1, 0), (1, 0), "CENTER"), header_table.styles)

        self.assertEqual(order_table.colWidths, [64, 76, 198, 74, 128])
        self.assertIn(("ALIGN", (0, 0), (-1, -1), "CENTER"), order_table.styles)
        totals_row_idx = len(order_table.data) - 1
        self.assertEqual(totals_row_idx, len(order_rows) + 1)
        self.assertEqual(order_table.data[totals_row_idx], ["Total Items: 1", "", "", "Total Quantity: 4", ""])
        self.assertIn(("SPAN", (0, totals_row_idx), (2, totals_row_idx)), order_table.styles)
        self.assertIn(("SPAN", (3, totals_row_idx), (4, totals_row_idx)), order_table.styles)
        self.assertIn(("ALIGN", (0, totals_row_idx), (2, totals_row_idx), "CENTER"), order_table.styles)
        self.assertIn(("ALIGN", (3, totals_row_idx), (4, totals_row_idx), "CENTER"), order_table.styles)

    def test_default_catalog_state_has_more_cards_than_filtered_query(self) -> None:
        full_response = self.client.get("/")
        self.assertEqual(full_response.status_code, 200)
        full_body = full_response.get_data(as_text=True)
        full_count = len(re.findall(r'class=\"[^\"]*product-card', full_body))
        self.assertGreater(full_count, 0)

        filtered_response = self.client.get(f"/?q={self.valid_code}")
        self.assertEqual(filtered_response.status_code, 200)
        filtered_body = filtered_response.get_data(as_text=True)
        filtered_count = len(re.findall(r'class=\"[^\"]*product-card', filtered_body))

        self.assertGreater(filtered_count, 0)
        self.assertLess(filtered_count, full_count)
