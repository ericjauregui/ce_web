from __future__ import annotations

from urllib.parse import urlsplit
from unittest.mock import patch

from itsdangerous import URLSafeTimedSerializer

import app as webapp
from domains.orders import OrderRepository
from tests.common import BaseWebTest


class CacheControlTests(BaseWebTest):
    def test_customer_specific_pages_and_cart_api_are_never_cached(self) -> None:
        for path in ("/", "/cart", "/checkout", "/api/cart/count"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.headers["Cache-Control"], "private, no-store, max-age=0")

    def test_errors_are_never_cached(self) -> None:
        for path in (
            "/download/order/not-the-session-token.csv",
            "/download/order/not-the-session-token.pdf",
            "/missing-page",
            "/static/missing-file.css?v=forged",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertGreaterEqual(response.status_code, 400)
                self.assertEqual(response.headers["Cache-Control"], "private, no-store, max-age=0")

    def test_successful_private_csv_and_pdf_downloads_are_never_cached(self) -> None:
        repository = OrderRepository(
            "sqlite+pysqlite:///:memory:",
            allow_sqlite_for_tests=True,
        )
        self.addCleanup(repository.engine.dispose)
        repository.create_schema_for_tests()
        created = repository.create_order(
            idempotency_key="cache-policy-download-test",
            customer={
                "name": "Private Customer",
                "company": "Private Company",
                "phone": "+1 2135550100",
                "email": "customer@example.com",
                "city": "Los Angeles",
                "state": "CA",
                "country": "United States",
                "country_key": "us",
            },
            items=[{"code": "101SB", "name": "Stud", "quantity": 1}],
        )
        order = repository.store_order_csv(
            created.order.id,
            "code,quantity\n101SB,1\n",
            "order.csv",
        )
        previous_repository = webapp.app.extensions.get("order_repository")
        webapp.app.extensions["order_repository"] = repository

        def restore_repository() -> None:
            if previous_repository is None:
                webapp.app.extensions.pop("order_repository", None)
            else:
                webapp.app.extensions["order_repository"] = previous_repository

        self.addCleanup(restore_repository)
        token = URLSafeTimedSerializer(
            webapp.app.secret_key,
            salt="order-download-v1",
        ).dumps({"order_id": order.id, "access_token": order.access_token})
        with self.client.session_transaction() as sess:
            sess["last_order_token"] = token
            sess["last_order_id"] = order.id

        csv_response = self.client.get(f"/download/order/{token}.csv")
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response.headers["Cache-Control"], "private, no-store, max-age=0")
        csv_response.close()

        with patch("domains.cart_routes.cart_to_pdf_bytes", return_value=b"%PDF-test"):
            pdf_response = self.client.get(f"/download/order/{token}.pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.headers["Cache-Control"], "private, no-store, max-age=0")
        pdf_response.close()

    def test_only_the_current_static_content_fingerprint_is_immutable(self) -> None:
        page = self.client.get("/")
        body = page.get_data(as_text=True)
        marker = 'href="/static/css/styles/base.css?v='
        versioned_url = "/static/css/styles/base.css?v=" + body.split(marker, 1)[1].split('"', 1)[0]

        immutable = self.client.get(versioned_url)
        self.assertEqual(immutable.status_code, 200)
        self.assertEqual(immutable.headers["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertNotIn("Set-Cookie", immutable.headers)
        immutable.close()

        for url in (urlsplit(versioned_url).path, f"{urlsplit(versioned_url).path}?v=forged"):
            with self.subTest(url=url):
                mutable = self.client.get(url)
                self.assertEqual(mutable.status_code, 200)
                self.assertEqual(mutable.headers["Cache-Control"], "public, max-age=300, must-revalidate")
                self.assertNotIn("Set-Cookie", mutable.headers)
                mutable.close()

    def test_public_metadata_and_contact_download_have_bounded_public_caching(self) -> None:
        paths = {
            "/robots.txt": "public, max-age=300, must-revalidate",
            "/sitemap.xml": "public, max-age=300, must-revalidate",
            f"/team/{self.first_member['slug']}/contact.vcf": "public, max-age=3600, must-revalidate",
        }
        for path, expected in paths.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Cache-Control"], expected)
                self.assertNotIn("Set-Cookie", response.headers)
