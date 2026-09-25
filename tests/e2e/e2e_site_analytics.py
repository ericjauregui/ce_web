from __future__ import annotations

import base64

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app as webapp
from domains.connect_analytics import ConnectAnalytics
from domains.site_analytics import SiteAnalytics
from tests.e2e.common import BaseE2ETest


class SiteAnalyticsDashboardE2ETests(BaseE2ETest):
    def setUp(self) -> None:
        super().setUp()
        self.prior_analytics = webapp.app.extensions.get("site_analytics")
        self.prior_username = webapp.app.config.get("SITE_ANALYTICS_ADMIN_USERNAME")
        self.prior_password = webapp.app.config.get("SITE_ANALYTICS_ADMIN_PASSWORD")
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.analytics = SiteAnalytics(engine)
        self.analytics.create_schema_for_tests()
        self.connect_analytics = ConnectAnalytics(engine)
        self.connect_analytics.create_schema_for_tests()
        webapp.app.extensions["site_analytics"] = self.analytics
        webapp.app.config.update(
            SITE_ANALYTICS_ADMIN_USERNAME="analytics-test",
            SITE_ANALYTICS_ADMIN_PASSWORD="synthetic-test-password",
        )
        self.primary_session = "a" * 64
        secondary_session = "b" * 64
        self.analytics.record(
            session_hash=self.primary_session,
            event_type="page_view",
            page_path="/",
            referrer_host="newsletter.example",
            utm_source="newsletter",
            utm_medium="email",
            utm_campaign="fall-launch",
        )
        self.analytics.record(
            session_hash=self.primary_session,
            event_type="page_view",
            page_path="/connect",
            page_context="jis-fall-2026",
        )
        self.analytics.record(
            session_hash=self.primary_session,
            event_type="click",
            page_path="/connect",
            page_context="jis-fall-2026",
            click_target="external:whatsapp",
        )
        self.analytics.record(
            session_hash=secondary_session,
            event_type="page_view",
            page_path="/team",
            referrer_host="google.com",
        )
        self.connect_analytics.record(
            action="visit",
            event={"key": "jis-fall-2026", "name": "JIS Miami", "booth": "117"},
        )
        self.connect_analytics.record(
            action="whatsapp",
            event={"key": "jis-fall-2026", "name": "JIS Miami", "booth": "117"},
        )
        self.dashboard_auth_header = "Basic " + base64.b64encode(
                b"analytics-test:synthetic-test-password"
            ).decode("ascii")
        self.addCleanup(self._restore_analytics_state)

    def _restore_analytics_state(self) -> None:
        if self.prior_analytics is None:
            webapp.app.extensions.pop("site_analytics", None)
        else:
            webapp.app.extensions["site_analytics"] = self.prior_analytics
        for key, value in (
            ("SITE_ANALYTICS_ADMIN_USERNAME", self.prior_username),
            ("SITE_ANALYTICS_ADMIN_PASSWORD", self.prior_password),
        ):
            if value is None:
                webapp.app.config.pop(key, None)
            else:
                webapp.app.config[key] = value
        self.analytics.engine.dispose()

    def test_private_dashboard_summarizes_and_drills_into_synthetic_journeys(self) -> None:
        anonymous_client = self._playwright_context.request.new_context()
        try:
            unauthenticated = anonymous_client.get(f"{self.base_url}/admin/analytics")
            self.assertEqual(unauthenticated.status, 401)
            self.assertIn("Basic", unauthenticated.headers.get("www-authenticate", ""))
            self.assertIn("no-store", unauthenticated.headers.get("cache-control", ""))
        finally:
            anonymous_client.dispose()

        tracked_requests: list[str] = []
        self.page.on("request", lambda request: tracked_requests.append(request.url)
                     if "/api/analytics/event" in request.url else None)
        self.page.set_extra_http_headers({"Authorization": self.dashboard_auth_header})
        response = self.goto("/admin/analytics?days=7")
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(response.headers.get("x-robots-tag"), "noindex, nofollow")
        self.assertEqual(self.page.locator("h1").inner_text(), "Site analytics")
        self.assertEqual(self.page.locator(".metric-card").nth(0).locator("strong").inner_text(), "2")
        self.assertEqual(self.page.locator(".metric-card").nth(1).locator("strong").inner_text(), "3")
        self.assertEqual(self.page.locator(".metric-card").nth(2).locator("strong").inner_text(), "1")
        pages_card = self.page.locator("#pages-title").locator("xpath=../../..")
        sources_card = self.page.locator("#sources-title").locator("xpath=../../..")
        campaigns_card = self.page.locator("#campaigns-title").locator("xpath=../../..")
        self.assertIn("/connect", pages_card.inner_text())
        self.assertIn("newsletter.example", sources_card.inner_text())
        self.assertIn("fall-launch", campaigns_card.inner_text())
        self.assertIn("JIS Miami", self.page.locator("#connect-actions-title")
                      .locator("xpath=../../..").inner_text())
        self.assertEqual(self.page.locator("script[src*='site_analytics.js']").count(), 0)
        self.assertFalse(any("cloudflareinsights.com/beacon" in url for url in tracked_requests))
        self.assertFalse(any("/api/analytics/event" in url for url in tracked_requests))
        self.assertFalse(any(cookie["name"] == "ce_analytics_session" for cookie in self.context.cookies()))

        self.page.get_by_role("button", name=f"Session ·{self.primary_session[-8:]}").click()
        self.assertNotIn(self.primary_session, self.page.url)
        self.page.get_by_role("heading", name=f"Journey ·{self.primary_session[-8:]}").wait_for()
        self.assertEqual(self.page.locator(".journey-list li").count(), 3)
        self.assertIn("external:whatsapp", self.page.locator(".journey-list").inner_text())
