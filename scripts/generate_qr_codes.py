"""Generate QR codes for product deep links.

Usage:
  python scripts/generate_qr_codes.py --base-url https://californiaearrings.com

This will create PNG QR codes under static/qr/ and also write `qr_image`
into catalog/products.json for each product.
"""

import argparse
import json
from pathlib import Path

import qrcode

BASE_DIR = Path(__file__).resolve().parents[1]
CATALOG_PATH = BASE_DIR / "catalog" / "products.json"
QR_DIR = BASE_DIR / "static" / "qr"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True, help="e.g. https://californiaearrings.com")
    args = ap.parse_args()
    base_url = args.base_url.rstrip("/")

    QR_DIR.mkdir(parents=True, exist_ok=True)

    products = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for p in products:
        slug = p["slug"]
        url = f"{base_url}/product/{slug}"
        filename = f"{p['code']}.png"

        img = qrcode.make(url)
        img.save(QR_DIR / filename)

        p["qr_image"] = filename

    CATALOG_PATH.write_text(json.dumps(products, indent=2), encoding="utf-8")
    print(f"Generated {len(products)} QR codes in {QR_DIR}")


if __name__ == "__main__":
    main()
