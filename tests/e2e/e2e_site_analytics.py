from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app as webapp
from domains.connect_analytics import ConnectAnalytics, connect_event_counts
from domains.site_analytics import SiteAnalytics, site_analytics_events
from tests.e2e.common import BaseE2ETest


class SiteAnalyticsDashboardE2ETests(BaseE2ETest):
    def setUp(self) -> None:
        super().setUp()
        self.prior_analytics = webapp.app.extensions.get("site_analytics")
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
        self.primary_session = "a" * 64
        self.secondary_session = "b" * 64
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
            session_hash=self.secondary_session,
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
        self.analytics.record(
            session_hash=self.primary_session,
            event_type="click",
            page_path="/catalog",
            click_target="action:add-to-order",
        )
        self.fixture_date = datetime.now(ZoneInfo("America/Los_Angeles")).date() - timedelta(days=1)
        fixture_time = datetime.combine(
            self.fixture_date,
            time(hour=18),
            tzinfo=ZoneInfo("America/Los_Angeles"),
        ).astimezone(timezone.utc)
        with engine.begin() as connection:
            connection.execute(site_analytics_events.update().values(occurred_at=fixture_time))
            connection.execute(connect_event_counts.update().values(event_date=self.fixture_date))
        self.addCleanup(self._restore_analytics_state)

    def _restore_analytics_state(self) -> None:
        if self.prior_analytics is None:
            webapp.app.extensions.pop("site_analytics", None)
        else:
            webapp.app.extensions["site_analytics"] = self.prior_analytics
        self.analytics.engine.dispose()

    def test_public_dashboard_shows_aggregates_without_session_identifiers(self) -> None:
        dashboard_query = (
            "range=rolling&count=7&unit=days&granularity=day&metric=both"
            "&page_filter=all&journey_start=all"
        )
        anonymous_client = self._playwright_context.request.new_context()
        try:
            response = anonymous_client.get(f"{self.base_url}/admin/analytics?{dashboard_query}")
            self.assertEqual(response.status, 200)
            self.assertNotIn("www-authenticate", response.headers)
            self.assertIn("no-store", response.headers.get("cache-control", ""))
            self.assertNotIn("set-cookie", response.headers)
            self.assertEqual(response.headers.get("x-robots-tag"), "noindex, nofollow")
            self.assertNotIn(self.primary_session, response.text())
            self.assertNotIn(self.primary_session[-8:], response.text())
            self.assertNotIn(self.secondary_session, response.text())
            self.assertNotIn(self.secondary_session[-8:], response.text())
            self.assertNotIn("Recent sessions", response.text())
            self.assertNotIn("session_id_hash", response.text())
            self.assertIn("This public report displays aggregate counts only", response.text())
            self.assertNotIn("Shared reporting", response.text())
            self.assertNotIn("UTC", response.text())
            self.assertIn("Previous calendar month", response.text())
            self.assertIn("complete weeks", response.text())
            self.assertIn("Team pages", response.text())
            self.assertIn("/team", response.text())
            robots = anonymous_client.get(f"{self.base_url}/robots.txt")
            self.assertEqual(robots.status, 200)
            self.assertIn("Disallow: /admin/analytics", robots.text())
            sitemap = anonymous_client.get(f"{self.base_url}/sitemap.xml")
            self.assertEqual(sitemap.status, 200)
            self.assertNotIn("/admin/analytics", sitemap.text())
            post_response = anonymous_client.post(
                f"{self.base_url}/admin/analytics",
                data={"session": self.primary_session},
            )
            self.assertEqual(post_response.status, 405)
        finally:
            anonymous_client.dispose()

        tracked_requests: list[str] = []
        self.page.on("request", lambda request: tracked_requests.append(request.url)
                     if "/api/analytics/event" in request.url else None)
        response = self.goto(f"/admin/analytics?{dashboard_query}")
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(response.headers.get("x-robots-tag"), "noindex, nofollow")
        self.assertEqual(self.page.locator("h1").inner_text(), "Site analytics")
        self.assertEqual(self.page.locator(".metric-card").nth(0).locator("strong").inner_text(), "2")
        self.assertEqual(self.page.locator(".metric-card").nth(1).locator("strong").inner_text(), "3")
        self.assertEqual(self.page.locator(".metric-card").nth(2).locator("strong").inner_text(), "2")
        self.assertIn(
            "This public report displays aggregate counts only",
            self.page.locator("main.analytics-dashboard").inner_text(),
        )
        self.assertNotIn("Shared reporting", self.page.locator("main.analytics-dashboard").inner_text())
        self.assertIn("Pacific Time (PT)", self.page.locator("main.analytics-dashboard").inner_text())
        self.assertEqual(self.page.locator(".analytics-bucket").count(), 1)
        self.assertRegex(self.page.locator(".analytics-bucket small").inner_text(), r"^\d{1,2}/\d{1,2}$")
        self.assertGreater(self.page.locator("#analytics-sankey .sankey-link").count(), 0)
        pages_card = self.page.locator("#pages-title").locator("xpath=../../..")
        sources_card = self.page.locator("#sources-title").locator("xpath=../../..")
        campaigns_card = self.page.locator("#campaigns-title").locator("xpath=../../..")
        clicks_card = self.page.locator("#clicks-title").locator("xpath=../../..")
        self.assertIn("/connect", pages_card.inner_text())
        self.assertIn("Add to order", clicks_card.inner_text())
        self.assertIn("newsletter.example", sources_card.inner_text())
        self.assertIn("fall-launch", campaigns_card.inner_text())
        self.assertIn("JIS Miami", self.page.locator("#connect-actions-title")
                      .locator("xpath=../../..").inner_text())
        self.assertEqual(self.page.locator("script[src*='site_analytics.js']").count(), 0)
        self.assertEqual(self.page.locator("script[src*='cloudflareinsights.com']").count(), 0)
        self.assertFalse(any("cloudflareinsights.com/beacon" in url for url in tracked_requests))
        self.assertFalse(any("/api/analytics/event" in url for url in tracked_requests))
        self.assertEqual(self.context.cookies(), [])
        self.assertFalse(any(cookie["name"] == "ce_analytics_session" for cookie in self.context.cookies()))
        self.assertNotIn(self.primary_session, self.page.content())
        self.assertNotIn(self.primary_session[-8:], self.page.content())
        self.assertNotIn(self.secondary_session, self.page.content())
        self.assertNotIn(self.secondary_session[-8:], self.page.content())
        self.assertNotIn("Recent sessions", self.page.content())
        self.assertNotIn("session_id_hash", self.page.content())

        filtered_response = self.goto(
            "/admin/analytics?range=rolling&count=7&unit=days&page_filter=path:/connect"
            "&journey_start=path:/&granularity=week&metric=clicks"
        )
        self.assertEqual(filtered_response.status, 200)
        self.assertEqual(self.page.locator("#analytics-page-filter").input_value(), "path:/connect")
        self.assertEqual(self.page.locator("#analytics-granularity").input_value(), "week")
        self.assertEqual(self.page.locator("#analytics-metric").input_value(), "clicks")
        self.assertEqual(self.page.locator(".analytics-bucket").count(), 1)
        self.assertEqual(self.page.locator(".bar-views").count(), 0)
        self.assertGreater(self.page.locator(".bar-clicks").count(), 0)
        self.assertEqual(self.page.locator("#analytics-sankey .sankey-link").count(), 2)
        self.assertEqual(self.context.cookies(), [])

        fixture_day = self.fixture_date.isoformat()
        custom_response = self.goto(
            f"/admin/analytics?range=custom&date_from={fixture_day}&date_to={fixture_day}"
            "&granularity=month&metric=both&page_filter=all&journey_start=all"
        )
        self.assertEqual(custom_response.status, 200)
        self.assertEqual(self.page.locator("#analytics-range-mode").input_value(), "custom")
        self.assertEqual(self.page.locator("#analytics-date-from").input_value(), fixture_day)
        self.assertEqual(self.page.locator("#analytics-date-to").input_value(), fixture_day)
        self.assertEqual(self.page.locator(".metric-card").nth(1).locator("strong").inner_text(), "3")
        self.assertEqual(self.page.locator(".metric-card").nth(2).locator("strong").inner_text(), "2")
        self.assertEqual(self.page.locator(".analytics-bucket").count(), 1)

    def test_click_tracking_uses_action_and_product_card_labels(self) -> None:
        self.page.add_init_script("""
          window.__analyticsEvents = [];
          const nativeSendBeacon = navigator.sendBeacon.bind(navigator);
          navigator.sendBeacon = (url, body) => {
            if (url === '/api/analytics/event' && body instanceof Blob) {
              body.text().then(text => {
                try { window.__analyticsEvents.push(JSON.parse(text)); } catch (_) {}
              });
            }
            return nativeSendBeacon(url, body);
          };
        """)
        self.goto("/")

        def click_and_assert(selector: str, target: str) -> None:
            self.page.locator(selector).first.click()
            self.page.wait_for_function(
                "expected => window.__analyticsEvents.some(event => "
                "event.event_type === 'click' && event.click_target === expected)",
                arg=target,
                timeout=8000,
            )

        click_and_assert(".product-card", "component:product-card")
        click_and_assert(".product-card .add-to-cart-btn", "action:add-to-order")
