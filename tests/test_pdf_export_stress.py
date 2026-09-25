"""Isolation check for a PDF failure mode that a small checkout cannot trigger.

Repeated product images can make a large order export impractically large even
when its short browser checkout and PDF download both succeed.
"""

from __future__ import annotations

import unittest

import app as webapp
from domains.cart import cart_to_pdf_bytes


class PDFExportStressTests(unittest.TestCase):
    def test_repeated_images_keep_large_order_download_compact(self) -> None:
        rows = [
            {
                "code": f"IMG{i:03d}",
                "name": f"Image Item {i}",
                "quantity": 1,
                "notes": "",
                "image": "102SB.jpg",
            }
            for i in range(80)
        ]
        image_dir = webapp.BASE_DIR / "static" / "product_images"

        pdf_bytes = cart_to_pdf_bytes(rows, image_dir)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertLess(len(pdf_bytes), 2_000_000)
