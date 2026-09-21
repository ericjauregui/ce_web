from unittest.mock import patch

from tests.common import BaseWebTest


class AnalyticsIntegrationTests(BaseWebTest):
    def test_cloudflare_snippet_requires_site_token_and_is_shared_across_pages(self):
        with patch.dict("os.environ", {}, clear=True):
            body = self.client.get("/").text
            self.assertIn('data-cf-beacon=\'{"token": "30e9fc0a5f4f49379c768839796e2af1"}\'', body)

        with patch.dict("os.environ", {"CLOUDFLARE_WEB_ANALYTICS_TOKEN": ""}):
            self.assertNotIn("cloudflareinsights.com/beacon.min.js", self.client.get("/").text)

        with patch.dict("os.environ", {"CLOUDFLARE_WEB_ANALYTICS_TOKEN": "test-site-token"}):
            for path in ("/", "/privacy", "/checkout"):
                with self.subTest(path=path):
                    body = self.client.get(path).text
                    self.assertEqual(body.count("cloudflareinsights.com/beacon.min.js"), 1)
                    self.assertIn('data-cf-beacon=\'{"token": "test-site-token"}\'', body)

        privacy = self.client.get("/privacy").text
        self.assertIn("Cloudflare Web Analytics", privacy)
