from __future__ import annotations

from urllib.parse import urlparse

from tests.e2e.common import BaseE2ETest


class CatalogJourneyE2ETests(BaseE2ETest):
    """Exercise the catalog a buyer actually sees in a live browser."""

    browser_name = "chromium"

    def search_for(self, query: str) -> None:
        trigger = self.page.locator(".nav-search-trigger")
        trigger.click()
        search = self.page.locator("#navSearchForm .nav-search-input")
        search.fill(query)
        search.press("Enter")
        self.page.wait_for_url(f"**/?q={query}")

    def test_search_recovers_real_products_and_clears_back_to_catalog(self) -> None:
        self.goto("/")
        self.assertGreater(self.page.locator(".catalog-collection-section").count(), 1)

        self.search_for("tortuga")
        results = self.page.locator("#section-search-results .product-card")
        self.assertGreater(results.count(), 0)
        self.assertEqual(self.page.locator(".catalog-collection-section").count(), 1)
        self.assertTrue(all("Turtle" in text for text in results.all_inner_texts()))
        self.assertEqual(self.page.locator(".product-card [data-tags]").count(), 0)

        self.page.locator(".nav-search-trigger").click()
        self.page.locator("#navSearchForm .nav-search-input").fill("")
        self.page.wait_for_url(self.base_url + "/")
        self.page.wait_for_function(
            "() => document.querySelectorAll('.catalog-collection-section').length > 1"
        )
        self.assertEqual(self.page.locator("#section-search-results").count(), 0)

        self.search_for("buterfly")
        self.assertGreater(self.page.locator("#section-search-results .product-card").count(), 0)
        self.assertIn(
            "Butterfly",
            self.page.locator("#section-search-results .product-card").first.inner_text(),
        )

        self.search_for("1072lsb")
        first = self.page.locator("#section-search-results .product-card").first
        self.assertEqual(first.locator(".product-detail-link").inner_text().strip(), "1072LSB")
        first.locator(".product-detail-link").click()
        self.page.wait_for_url("**/product/1072LSB")
        self.assertIn("Turtle", self.page.locator("h1.product-detail-title").inner_text())

        response = self.page.goto(
            self.base_url + "/product/does-not-exist", wait_until="domcontentloaded"
        )
        self.assertEqual(response.status, 404)
        self.assertIn("404", self.page.locator("main").inner_text())
        self.page.get_by_role("link", name="Browse Our Catalog").click()
        self.assertEqual(urlparse(self.page.url).path, "/")
        self.assertGreater(self.page.locator(".catalog-collection-section").count(), 1)

    def test_product_detail_and_order_flow_keep_real_product_image(self) -> None:
        self.goto("/")
        images = self.page.locator("img.product-img")
        self.assertGreater(images.count(), 0)
        self.assertEqual(self.page.locator('img.product-img[loading="lazy"][decoding="async"]').count(), images.count())
        self.page.wait_for_function(
            "() => [...document.querySelectorAll('.hero-logo, .brand-logo')].every(image => image.complete && image.naturalWidth > 0)"
        )
        card = self.page.locator(".product-card:has(.product-detail-link:text-is('101SB'))")
        self.assertEqual(card.count(), 1)
        thumbnail = card.locator("img.product-img").first
        thumbnail.scroll_into_view_if_needed()
        self.page.wait_for_function(
            "() => { const image = document.querySelector('.product-card img.product-img'); return image?.complete && image.naturalWidth > 0; }"
        )
        self.assertTrue(thumbnail.get_attribute("alt"))
        self.assertIn("/optimized/responsive/", thumbnail.evaluate("image => image.currentSrc"))

        card.locator(".product-detail-link").click()
        self.page.wait_for_url("**/product/101SB")
        self.assertIn("Micro Round CZ", self.page.locator("h1.product-detail-title").inner_text())
        self.page.wait_for_function(
            "() => { const image = document.querySelector('.product-detail-image'); return image?.complete && image.naturalWidth > 0; }"
        )
        detail_image = self.page.locator(".product-detail-image")
        self.assertIn("/static/product_images/101SB.jpg", detail_image.get_attribute("src"))
        self.assertIsNone(detail_image.get_attribute("srcset"))

        self.page.locator(".product-detail-top-add-btn").click()
        self.page.wait_for_function(
            "() => Number(document.getElementById('cartCountBadge')?.textContent || 0) === 1"
        )
        self.goto("/cart")
        self.assertIn("101SB", self.page.locator("main").inner_text())
        self.assertEqual(self.page.locator(".minimal-items-table tbody tr").count(), 1)
