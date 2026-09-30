from __future__ import annotations

import json
import re
import time as clock

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

import app as webapp
from domains.connect_analytics import ConnectAnalytics, connect_event_counts
from domains.site_analytics import (
    SiteAnalytics, resolve_dashboard_range, site_analytics_events, site_request_status_daily_counts,
)
from tests.e2e.common import BaseE2ETest


class SiteAnalyticsDashboardE2ETests(BaseE2ETest):
    def setUp(self) -> None:
        super().setUp()
        # Background media can monopolize the single-threaded local test server.
        # Playback is covered separately; these tests verify tracking and storage.
        self.page.route(re.compile(r'/static/reels/[^?]+\.mp4(?:\?.*)?$', re.I),
            lambda route: route.fulfill(status=204, body=''))
        self.prior_analytics = webapp.app.extensions.get("site_analytics")
        self.prior_connect_analytics = webapp.app.extensions.get("connect_analytics")
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.analytics = SiteAnalytics(engine)
        self.analytics.create_schema_for_tests()
        self.connect_analytics = ConnectAnalytics(engine)
        self.connect_analytics.create_schema_for_tests()
        webapp.app.extensions["connect_analytics"] = self.connect_analytics
        webapp.app.extensions["site_analytics"] = self.analytics
        self.primary_session = "a" * 64
        self.secondary_session = "b" * 64
        self.long_session = "c" * 64
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
            event_type="page_view",
            page_path="/checkout",
        )
        self.analytics.record(
            session_hash=self.primary_session,
            event_type="page_duration",
            page_path="/checkout",
            duration_seconds=75,
        )
        self.analytics.record(
            session_hash=self.primary_session,
            event_type="checkout_field",
            page_path="/checkout",
            field_key="name",
        )
        self.analytics.record(
            session_hash=self.primary_session,
            event_type="checkout_field",
            page_path="/checkout",
            field_key="email",
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
        for page_path in (
            "/", "/catalog", "/product/test", "/checkout", "/connect", "/team", "/trade-shows",
        ):
            self.analytics.record(
                session_hash=self.long_session,
                event_type="page_view",
                page_path=page_path,
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
        for click_target in (
            "action:toggle-navigation",
            "action:play-video-1",
            "action:turn-video-sound-on",
        ):
            self.analytics.record(
                session_hash=self.primary_session,
                event_type="click",
                page_path="/",
                click_target=click_target,
            )
        for _ in range(4):
            self.analytics.record_request_status(page_path="/", status_code=200)
        self.analytics.record_request_status(page_path="/missing-fixture", status_code=404)
        self.fixture_date = datetime.now(ZoneInfo("America/Los_Angeles")).date() - timedelta(days=1)
        fixture_time = datetime.combine(
            self.fixture_date,
            time(hour=18),
            tzinfo=ZoneInfo("America/Los_Angeles"),
        ).astimezone(timezone.utc)
        with engine.begin() as connection:
            connection.execute(site_analytics_events.update().values(occurred_at=fixture_time))
            connection.execute(connect_event_counts.update().values(event_date=self.fixture_date))
            connection.execute(
                site_request_status_daily_counts.update().values(event_date=self.fixture_date)
            )
        self.addCleanup(self._restore_analytics_state)

    def _restore_analytics_state(self) -> None:
        if self.prior_analytics is None:
            webapp.app.extensions.pop("site_analytics", None)
        else:
            webapp.app.extensions["site_analytics"] = self.prior_analytics
        if self.prior_connect_analytics is None:
            webapp.app.extensions.pop("connect_analytics", None)
        else:
            webapp.app.extensions["connect_analytics"] = self.prior_connect_analytics
        self.analytics.engine.dispose()

    def test_request_review_separates_probes_without_hiding_other_missing_pages(self) -> None:
        """Old/new probes, unexpected 200s, pagination and filters must preserve counts.

        Unknown paths and private-download failures cannot be assumed to be bots.
        Browser evidence must also show that the report contains no private tokens.
        """
        with self.analytics.engine.begin() as connection:
            connection.execute(site_request_status_daily_counts.delete())
        client = self._playwright_context.request.new_context()
        try:
            for path in ('/.env', '/wp-login.php', '/.git/config', '/backup.sql',
                         '/phpmyadmin/', '/actuator/env', '/unknown-missing',
                         '/product/missing', '/download/order/synthetic-audit-token.pdf'):
                response = client.get(f'{self.base_url}{path}?private-query=not-recorded')
                self.assertEqual(response.status, 404, path)
            for path in ('/', '/about'):
                self.assertEqual(client.get(f'{self.base_url}{path}').status, 200)
        finally:
            client.dispose()
        with self.analytics.engine.begin() as connection:
            connection.execute(site_request_status_daily_counts.update().values(event_date=self.fixture_date))
            # Historical rows must be classified without rewriting stored counts.
            connection.execute(site_request_status_daily_counts.insert(), [
                dict(event_date=self.fixture_date, page_path=path, status_code=status, request_count=count)
                for path, status, count in [
                    ('/.env.production', 404, 20), ('/wp-login.php', 200, 2),
                    ('/config.json', 200, 3),
                    *[(f'/missing-review-{index:02}', 404, 1) for index in range(30)],
                ]
            ])
            before = list(connection.execute(select(site_request_status_daily_counts)).mappings())
        self.goto('/admin/analytics?count=7&unit=days&metric=clicks')
        card = self.page.locator('#request-status-card')
        self.assertEqual(card.get_attribute('data-all-requests'), '66')
        self.assertEqual(card.get_attribute('data-all-success'), '7')
        self.assertEqual(card.get_attribute('data-all-not-found'), '59')
        self.assertEqual(card.get_attribute('data-probe-requests'), '31')
        summary = self.page.locator('#request-status-summary')
        self.assertEqual(summary.locator('tbody tr').nth(0).locator('td').nth(1).inner_text(), '2')
        self.assertEqual(summary.locator('tbody tr').nth(1).locator('td').nth(1).inner_text(), '33')
        probes = self.page.locator('#request-probe-summary')
        self.assertIn('Sensitive-file probes', probes.inner_text())
        self.assertEqual(probes.locator('tbody tr').nth(0).locator('td').nth(1).inner_text(), '27')
        self.assertEqual(probes.locator('tbody tr').nth(1).locator('td').nth(1).inner_text(), '4')
        self.assertIn('5 probe requests returned 200', card.inner_text())
        self.assertIn('does not prove', card.inner_text())
        self.assertIn('not a count of human visitors', card.inner_text())
        other_missing = self.page.locator('#request-other-missing')
        self.assertNotIn('/wp-login.php', other_missing.inner_text())
        self.assertNotIn('/.env', other_missing.inner_text())
        self.assertIn('/download/order/file.pdf', other_missing.inner_text())
        self.assertNotIn('synthetic-audit-token', self.page.content())
        self.assertNotIn('not-recorded', self.page.content())
        self.page.locator('#request-review-details > summary').click()
        self.assertIn('Private download: denied or missing', card.inner_text())
        self.assertEqual(self.page.locator('#request-review tbody tr').count(), 25)
        first_paths = self.page.locator('#request-review tbody tr td:first-child').all_text_contents()
        self.page.locator('a[data-request-page="next"]').click()
        self.assertIn('count=7', self.page.url)
        self.assertIn('metric=clicks', self.page.url)
        self.assertIn('request_page=2', self.page.url)
        self.assertEqual(self.page.locator('#request-review tbody tr').count(), 16)
        second_paths = self.page.locator('#request-review tbody tr td:first-child').all_text_contents()
        self.assertEqual(len(set(first_paths + second_paths)), 41)
        with self.analytics.engine.connect() as connection:
            after = list(connection.execute(select(site_request_status_daily_counts)).mappings())
        self.assertEqual(before, after)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 390)
        with self.analytics.engine.begin() as connection:
            connection.execute(site_request_status_daily_counts.delete())
            connection.execute(site_request_status_daily_counts.insert(), [
                dict(event_date=self.fixture_date, page_path=path, status_code=404, request_count=1)
                for path in ('/wordpress/', '/.env.production')
            ])
        self.goto('/admin/analytics')
        self.assertEqual(self.page.locator('#request-status-card').get_attribute('data-probe-requests'), '2')
        self.assertEqual(self.page.locator('#request-status-summary').count(), 0)
        self.assertIn('All recorded requests in this range match likely probe patterns',
                      self.page.locator('#request-status-card').inner_text())
        with self.analytics.engine.begin() as connection:
            connection.execute(site_request_status_daily_counts.delete())
        self.goto('/admin/analytics')
        self.assertIn('No page response counts', self.page.locator('#request-status-card').inner_text())
        root = self._artifact_dir()
        root.mkdir(parents=True, exist_ok=True)
        (root / 'request-review.json').write_text(json.dumps({
            'all_requests': 66, 'successful': 7, 'not_found': 59,
            'likely_probes': 31, 'other_not_found': 33,
            'reviewed_paths': sorted(first_paths + second_paths),
            'stored_counts_unchanged': before == after,
        }, indent=2) + '\n')

    def test_request_review_does_not_reclassify_unrecognized_or_filtered_traffic_as_human(self) -> None:
        self.goto('/admin/analytics?page_filter=home&request_page=999999')
        card = self.page.locator('#request-status-card')
        self.assertEqual(card.get_attribute('data-all-requests'), '4')
        self.assertEqual(card.get_attribute('data-probe-requests'), '0')
        self.assertEqual(self.page.locator('#request-review tbody tr').count(), 0)
        self.assertIn('No likely scanner probes', card.inner_text())
        self.assertNotIn('human traffic', card.inner_text())
        self.goto('/admin/analytics?request_page=invalid')
        self.assertIn('Page 1 of 1', self.page.locator('#request-review-details').inner_text())
        self.assertIn('/missing-fixture', self.page.locator('#request-other-missing').inner_text())
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 390)

    def test_public_dashboard_shows_aggregates_without_session_identifiers(self) -> None:
        dashboard_query = (
            "range=rolling&count=7&unit=days&granularity=day&metric=views_sessions"
            "&page_filter=all&journey_start=filter"
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
            self.assertIn("custom date range", response.text())
            self.assertIn("complete weeks", response.text())
            self.assertIn("complete years", response.text())
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
        self.assertEqual(self.page.locator(".metric-card").nth(0).locator("strong").inner_text(), "3")
        self.assertEqual(self.page.locator(".metric-card").nth(1).locator("strong").inner_text(), "11")
        self.assertEqual(self.page.locator(".metric-card").nth(2).locator("strong").inner_text(), "5")
        self.assertIn(
            "This public report displays aggregate counts only",
            self.page.locator("main.analytics-dashboard").inner_text(),
        )
        self.assertNotIn("Shared reporting", self.page.locator("main.analytics-dashboard").inner_text())
        self.assertNotIn("Pacific", self.page.locator("main.analytics-dashboard").inner_text())
        self.assertEqual(self.page.locator("#analytics-line-chart").count(), 1)
        self.assertEqual(self.page.locator(".analytics-line--page_views").count(), 1)
        self.assertEqual(self.page.locator(".analytics-line--sessions").count(), 1)
        self.assertEqual(self.page.locator(".analytics-line--clicks").count(), 0)
        self.assertEqual(self.page.locator(".analytics-line-point").count(), 2)
        self.assertCountEqual(
            self.page.locator(".analytics-data-label").evaluate_all(
                "elements => elements.map(element => element.textContent)"
            ),
            ["11", "3"],
        )
        first_x_label = self.page.locator(".analytics-x-label").first.evaluate(
            "element => element.textContent"
        )
        self.assertRegex(first_x_label, r"^\d{1,2}/\d{1,2}$")
        self.assertIn("80%", self.page.locator("#request-status-title").locator("xpath=../../..")
                      .inner_text())
        checkout_card = self.page.locator("#checkout-insights-title").locator("xpath=../../..")
        self.assertIn("1m 15s", checkout_card.inner_text())
        self.assertIn("Name", checkout_card.inner_text())
        self.assertIn("Email", checkout_card.inner_text())
        self.assertNotIn("Synthetic Buyer", checkout_card.inner_text())
        self.assertGreater(self.page.locator("#analytics-sankey .sankey-link").count(), 0)
        pages_card = self.page.locator("#pages-title").locator("xpath=../../..")
        sources_card = self.page.locator("#sources-title").locator("xpath=../../..")
        campaigns_card = self.page.locator("#campaigns-title").locator("xpath=../../..")
        clicks_card = self.page.locator("#clicks-title").locator("xpath=../../..")
        contexts_card = self.page.locator("#context-title").locator("xpath=../../..")
        self.assertIn("/connect", pages_card.inner_text())
        self.assertIn("18%", pages_card.inner_text())
        self.assertIn("Add to order", clicks_card.inner_text())
        self.assertIn("20%", clicks_card.inner_text())
        self.assertIn("Toggle menu button", clicks_card.inner_text())
        self.assertIn("Click reel card 1", clicks_card.inner_text())
        self.assertIn("Turn video sound on", clicks_card.inner_text())
        self.assertNotIn("Toggle menu button opens or closes the navigation menu", clicks_card.inner_text())
        self.assertNotIn("Click reel card 1 records a click on that card", clicks_card.inner_text())
        self.assertNotIn("Play video 1", clicks_card.inner_text())
        self.assertIn("newsletter.example", sources_card.inner_text())
        self.assertIn("33%", sources_card.inner_text())
        self.assertIn("fall-launch", campaigns_card.inner_text())
        self.assertIn("33%", campaigns_card.inner_text())
        self.assertIn("9%", contexts_card.inner_text())
        self.assertIn("20%", contexts_card.inner_text())
        connect_actions_card = self.page.locator("#connect-actions-title").locator("xpath=../../..")
        self.assertIn("JIS Miami", connect_actions_card.inner_text())
        self.assertIn("50%", connect_actions_card.inner_text())
        self.assertIn("100%", self.page.locator("#request-status-title").locator("xpath=../../..")
                      .inner_text())
        self.assertIn("67% of filtered sessions", checkout_card.inner_text())
        self.assertIn("50%", checkout_card.inner_text())
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

        more_filters = self.page.locator("#analytics-more-filters")
        self.assertIsNone(more_filters.get_attribute("open"))
        period_unit = self.page.locator("#analytics-period-unit")
        self.assertTrue(period_unit.is_visible())
        self.assertTrue(self.page.locator("#analytics-page-filter").is_visible())
        self.assertFalse(self.page.locator("#analytics-metric").is_visible())
        period_unit.select_option("custom")
        self.assertTrue(self.page.locator("#analytics-date-from").is_visible())
        self.assertTrue(self.page.locator("#analytics-date-to").is_visible())
        self.assertFalse(self.page.locator("#analytics-period-count").is_visible())
        period_unit.select_option("days")
        self.assertTrue(self.page.locator("#analytics-period-count").is_visible())
        self.page.locator("#analytics-more-filters > summary").click()
        self.page.locator("#analytics-metric").select_option("clicks")
        self.page.locator("#analytics-more-filters > summary").click()
        self.page.wait_for_function(
            "document.querySelector('#analytics-more-filters-state').value === '0'"
        )
        with self.page.expect_navigation(wait_until="domcontentloaded") as applied_filters:
            self.page.locator(".analytics-filter-actions button").click()
        self.assertEqual(applied_filters.value.status, 200)
        self.assertIn("metric=clicks", self.page.url)
        self.assertIn("more_filters=0", self.page.url)
        self.assertEqual(self.page.locator("#analytics-metric").input_value(), "clicks")
        self.assertIsNone(self.page.locator("#analytics-more-filters").get_attribute("open"))

        filtered_response = self.goto(
            "/admin/analytics?range=rolling&count=7&unit=days&page_filter=path:/connect"
            "&journey_start=path:/team&granularity=week&metric=clicks"
        )
        self.assertEqual(filtered_response.status, 200)
        self.assertEqual(self.page.locator("#analytics-page-filter").input_value(), "path:/connect")
        self.assertEqual(self.page.locator("#analytics-granularity").input_value(), "week")
        self.assertEqual(self.page.locator("#analytics-metric").input_value(), "clicks")
        self.assertEqual(self.page.locator(".analytics-line").count(), 1)
        self.assertEqual(self.page.locator(".analytics-line--clicks").count(), 1)
        self.assertEqual(self.page.locator(".analytics-line--page_views").count(), 0)
        self.assertEqual(self.page.locator(".analytics-line--sessions").count(), 0)
        self.assertEqual(self.page.locator(".analytics-line-point--clicks").count(), 1)
        self.assertEqual(self.page.locator("#analytics-sankey .sankey-link").count(), 1)
        self.assertEqual(self.context.cookies(), [])

        journey_response = self.goto(
            "/admin/analytics?range=rolling&count=7&unit=days&granularity=day"
            "&metric=views_sessions&page_filter=all&journey_start=all&journey_depth=5"
        )
        self.assertEqual(journey_response.status, 200)
        expand_link = self.page.locator("#analytics-sankey .sankey-link[aria-label*='More pages']").first
        self.assertGreater(expand_link.count(), 0)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            expand_link.evaluate(
                "element => element.dispatchEvent(new MouseEvent('click', { bubbles: true }))"
            )
        self.assertIn("journey_depth=10", self.page.url)
        self.assertGreater(self.page.locator("#analytics-sankey .sankey-link").count(), 0)

        first_path_link = self.page.locator("#analytics-sankey .sankey-link[aria-label^='/ → /catalog']").first
        self.assertGreater(first_path_link.count(), 0)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            first_path_link.evaluate(
                "element => element.dispatchEvent(new MouseEvent('click', { bubbles: true }))"
            )
        self.assertIn("journey_page=%2F", self.page.url)
        self.assertIn("journey_page=%2Fcatalog", self.page.url)
        self.assertIn("1 of 3 starting sessions", self.page.locator(".analytics-journey-result").inner_text())

        fixture_day = self.fixture_date.isoformat()
        custom_response = self.goto(
            f"/admin/analytics?unit=custom&date_from={fixture_day}&date_to={fixture_day}"
            "&granularity=month&metric=both&page_filter=all&journey_start=all"
        )
        self.assertEqual(custom_response.status, 200)
        self.assertEqual(self.page.locator("#analytics-period-unit").input_value(), "custom")
        self.assertEqual(self.page.locator("#analytics-date-from").input_value(), fixture_day)
        self.assertEqual(self.page.locator("#analytics-date-to").input_value(), fixture_day)
        self.assertEqual(self.page.locator(".metric-card").nth(1).locator("strong").inner_text(), "11")
        self.assertEqual(self.page.locator(".metric-card").nth(2).locator("strong").inner_text(), "5")
        self.assertEqual(self.page.locator(".analytics-line-point").count(), 2)

        hourly_response = self.goto(
            "/admin/analytics?range=rolling&count=7&unit=days&granularity=hour"
            "&metric=views_sessions&page_filter=all&journey_start=filter"
        )
        self.assertEqual(hourly_response.status, 200)
        self.assertEqual(self.page.locator("#analytics-granularity").input_value(), "hour")
        self.assertEqual(self.page.locator(".analytics-line-point").count(), 48)
        self.assertEqual(
            self.page.locator(".analytics-x-label").evaluate_all(
                "elements => elements.map(element => element.textContent)"
            ),
            [f"{hour:02}h" for hour in range(24)],
        )
        self.assertIn(
            "hourly totals across selected dates",
            self.page.locator("main.analytics-dashboard").inner_text(),
        )
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertEqual(self.page.locator(".analytics-chart-scroll-hint").count(), 0)
        self.assertLessEqual(
            self.page.evaluate("document.documentElement.scrollWidth"),
            390,
            "The analytics dashboard should not overflow the mobile viewport.",
        )
        chart_scroll = self.page.locator(".analytics-chart-scroll")
        self.assertLessEqual(
            chart_scroll.evaluate("element => element.scrollWidth"),
            chart_scroll.evaluate("element => element.clientWidth") + 1,
            "The hourly chart should fit inside its card on narrow screens.",
        )
        mobile_hour_labels = self.page.locator(".analytics-x-label--hour").evaluate_all(
            "elements => elements.filter(element => getComputedStyle(element).display !== 'none')"
            ".map(element => element.textContent)"
        )
        self.assertEqual(mobile_hour_labels, ["00h", "04h", "08h", "12h", "16h", "20h", "23h"])
        chart_scroll.scroll_into_view_if_needed()
        self.page.screenshot(
            path=str(self._artifact_dir() / "analytics-chart-mobile.png"),
            animations="disabled",
        )

        chart_widths = {}
        for width in (320, 390, 767, 768, 1280):
            self.page.set_viewport_size({"width": width, "height": 844})
            chart_widths[width] = self.page.locator("#analytics-line-chart").evaluate(
                "element => element.getBoundingClientRect().width"
            )
            spacing = self.page.evaluate("""() => {
              const cart = document.querySelector('#cartLink svg');
              const toggler = document.querySelector('.navbar-toggler');
              const menu = document.querySelector('.navbar-toggler-icon');
              if (!cart || !toggler || !menu) return null;
              const cartRect = cart.getBoundingClientRect();
              const togglerRect = toggler.getBoundingClientRect();
              const menuRect = menu.getBoundingClientRect();
              const dividerX = togglerRect.left +
                parseFloat(getComputedStyle(toggler).borderLeftWidth || '0');
              return {
                cartGap: dividerX - cartRect.right,
                menuGap: menuRect.left - dividerX,
                visible: cartRect.width > 0 && menuRect.width > 0 &&
                  getComputedStyle(toggler).display !== 'none'
              };
            }""")
            self.assertIsNotNone(spacing, f"Navbar controls should exist at {width}px.")
            self.assertTrue(spacing["visible"], f"Navbar controls should be visible at {width}px.")
            self.assertAlmostEqual(
                spacing["cartGap"], spacing["menuGap"], delta=1,
                msg=f"Cart and menu icon should sit equally from the divider at {width}px: {spacing}",
            )
        self.assertGreater(
            chart_widths[1280], chart_widths[390] + 500,
            f"The chart should expand with the wider page: {chart_widths}",
        )
        self.page.set_viewport_size({"width": 390, "height": 844})

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

        self.open_checkout_with_item()
        self.page.locator('#checkoutForm [name="name"]').fill("Synthetic Buyer Name")
        self.page.locator('#checkoutForm [name="email"]').fill("buyer@example.test")
        self.page.wait_for_timeout(1200)
        self.page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        self.page.wait_for_function(
            "window.__analyticsEvents.some(event => event.event_type === 'page_duration') && "
            "window.__analyticsEvents.some(event => event.event_type === 'checkout_field' && event.field_key === 'name')"
        )
        checkout_events = self.page.evaluate(
            "window.__analyticsEvents.filter(event => ['page_duration', 'checkout_field'].includes(event.event_type))"
        )
        self.assertTrue(any(event["event_type"] == "page_duration" for event in checkout_events))
        self.assertTrue(any(event.get("field_key") == "email" for event in checkout_events))
        self.assertTrue(all("value" not in event for event in checkout_events))
        self.assertNotIn("Synthetic Buyer Name", str(checkout_events))
        self.assertNotIn("buyer@example.test", str(checkout_events))


    def _watch_analytics(self, *, fallback: bool = False) -> list[dict]:
        events = []
        self._analytics_responses = []
        self.page.expose_function("auditPayload", lambda payload: events.append({"payload": payload}))
        self.page.add_init_script("""
          const beacon = navigator.sendBeacon.bind(navigator);
          navigator.sendBeacon = (url, body) => {
            const sent = beacon(url, body);
            if (sent && url === '/api/analytics/event') body.text().then(text => window.auditPayload(JSON.parse(text)));
            return sent;
          };
          const nativeFetch = window.fetch;
          window.fetch = (url, options) => {
            if (url === '/api/analytics/event') window.auditPayload(JSON.parse(options.body));
            return nativeFetch(url, options);
          };
        """)
        if fallback:
            self.page.add_init_script("navigator.sendBeacon = () => false")
        def capture(response):
            if response.url.endswith('/api/analytics/event'):
                self._analytics_responses.append({"status": response.status, "method": response.request.method})
                self._save_tracking_evidence(events)
        self.page.on("response", capture)
        return events

    def _save_tracking_evidence(self, events: list[dict]) -> None:
        root = self._artifact_dir()
        root.mkdir(parents=True, exist_ok=True)
        (root / "analytics-network.json").write_text(json.dumps({"events": events, "responses": self._analytics_responses}, indent=2) + "\n")

    def _wait_tracking(self, events: list[dict], **expected) -> None:
        deadline = clock.monotonic() + 5
        while clock.monotonic() < deadline:
            if any(all(item["payload"].get(k) == v for k, v in expected.items()) for item in events):
                self.page.wait_for_timeout(100)
                self.assertTrue(self._analytics_responses)
                self.assertTrue(all(item["status"] == 204 for item in self._analytics_responses), self._analytics_responses)
                return
            self.page.wait_for_timeout(50)
        self.fail(f"Missing analytics event {expected}: {events}")

    def test_keyboard_and_quantity_edits_are_stored_and_grouped(self) -> None:
        """Catch missing keyboard/input events and per-product quantity labels."""
        from playwright.sync_api import expect
        events = self._watch_analytics()
        self.goto("/")
        card = self.page.locator(".product-card").first
        card.focus()
        card.press("Enter")
        self._wait_tracking(events, click_target="component:product-card")
        expect(card).to_have_attribute("aria-expanded", "true")
        card.locator(".add-to-cart-btn").click()
        expect(card.locator(".product-qty-input")).to_have_value("1")
        card.locator('[data-delta="1"]').click()
        expect(card.locator(".product-qty-input")).to_have_value("2")
        self._wait_tracking(events, click_target="action:order-quantity-plus")
        card.locator('[data-delta="-1"]').click()
        self._wait_tracking(events, click_target="action:order-quantity-minus")
        card.locator(".product-qty-input").fill("4")
        card.locator(".product-qty-input").press("Tab")
        expect(card).to_have_attribute("data-qty", "4")
        self._wait_tracking(events, click_target="action:order-quantity-edit")
        card.locator(".product-detail-link").click()
        self._wait_tracking(events, click_target=f"internal:/product/{self.valid_code}")
        self.page.locator('[data-delta="1"]').click()
        self._wait_tracking(events, page_path=f"/product/{self.valid_code}", click_target="action:order-quantity-plus")
        self.goto("/cart")
        self.page.locator(".qty-plus").first.click()
        self._wait_tracking(events, page_path="/cart", click_target="action:order-summary-quantity-plus")
        expect(self.page.locator(".qty-input").first).to_have_value("6")
        self.page.locator(".qty-input").first.fill("7")
        self.page.locator(".qty-input").first.press("Tab")
        self._wait_tracking(events, click_target="action:order-summary-quantity-edit")
        self.page.locator(".qty-remove").first.click()
        self._wait_tracking(events, click_target="action:order-summary-remove-item")
        with self.analytics.engine.connect() as connection:
            targets = set(connection.execute(select(site_analytics_events.c.click_target).where(
                site_analytics_events.c.occurred_at >= datetime.now(timezone.utc) - timedelta(minutes=2)
            )).scalars())
        self.assertIn("action:order-quantity-edit", targets)
        self.assertIn("action:order-summary-quantity-edit", targets)
        summary = self.analytics.dashboard_summary(
            page_filter="cart",
            range_values=resolve_dashboard_range({}, today=datetime.now(ZoneInfo("America/Los_Angeles")).date() + timedelta(days=1)),
        )
        self.assertIn("Increase order quantity", str(summary))
        self.assertIn("Edit quantity in Order Summary", str(summary))
        self.assertEqual(sum(item["payload"].get("click_target") == "component:product-card" for item in events), 1)

    def test_checkout_progress_survives_backgrounding_without_field_values(self) -> None:
        """Record progress while editing, deduplicate lifecycle flushes, omit option values."""
        events = self._watch_analytics()
        self.open_checkout_with_item()
        self.page.locator('#checkoutForm [name="name"]').fill("Synthetic Secret Buyer")
        self._wait_tracking(events, event_type="checkout_field", field_key="name")
        self.page.locator('#checkoutForm [name="name"]').fill("Different Secret Buyer")
        self.page.locator('#checkoutForm [name="notes"]').fill("Secret order notes")
        self.page.locator("#checkoutCountry").fill("United States")
        self.page.locator("#checkoutCountryCombobox .checkout-combobox__option").first.click()
        self._wait_tracking(events, click_target="action:checkout-select-country")
        self._wait_tracking(events, event_type="checkout_field", field_key="country")
        self.page.locator('#checkoutForm [name="name"]').press("Enter")
        self._wait_tracking(events, click_target="action:checkout-submit")
        self.page.wait_for_timeout(1100)
        self.page.evaluate("""() => {
          Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'hidden'});
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new Event('pagehide'));
        }""")
        self._wait_tracking(events, event_type="page_duration")
        self.page.wait_for_timeout(100)
        fields = [item["payload"]["field_key"] for item in events if item["payload"]["event_type"] == "checkout_field"]
        self.assertEqual(fields.count("name"), 1)
        self.assertEqual(fields.count("country"), 1)
        self.assertEqual(sum(item["payload"]["event_type"] == "page_duration" for item in events), 1)
        for value in ("Secret Buyer", "Secret order notes", "United States", "united-states"):
            self.assertNotIn(value, json.dumps(events))
        with self.analytics.engine.connect() as connection:
            stored = list(connection.execute(select(site_analytics_events.c.field_key).where(
                site_analytics_events.c.event_type == "checkout_field",
                site_analytics_events.c.occurred_at >= datetime.now(timezone.utc) - timedelta(minutes=2),
            )).scalars())
        self.assertCountEqual(stored, fields)

    def test_page_coverage_attribution_and_search_with_fetch_fallback(self) -> None:
        """Verify real accepted/stored events, shared session, query omission, and fallback."""
        events = self._watch_analytics(fallback=True)
        self.goto("/?utm_source=audit&utm_medium=local&utm_campaign=tracking&q=secret-search&gclid=secret-id")
        self._wait_tracking(events, event_type="page_view", page_path="/", utm_source="audit")
        cookie = next(cookie for cookie in self.context.cookies() if cookie["name"] == "ce_analytics_session")
        for path in ("/about", "/contact", "/team", "/trade-shows", "/connect", "/reels", "/faqs", "/privacy"):
            self.goto(path)
            self._wait_tracking(events, event_type="page_view", page_path=path)
        self.goto("/team")
        member_path = self.page.locator('a[href^="/team/"]').first.get_attribute("href")
        self.goto(member_path)
        self._wait_tracking(events, event_type="page_view", page_path=member_path)
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.locator("#contactQr summary").click()
        self._wait_tracking(events, click_target="action:toggle-contact-qr")
        self.page.set_viewport_size(self.viewport)
        self.goto("/")
        self.page.locator(".nav-search-trigger").click()
        search = self.page.locator('#navSearchForm [name="q"]')
        search.fill("private-search-phrase")
        search.press("Enter")
        self._wait_tracking(events, click_target="action:catalog-search")
        current_cookie = next(cookie for cookie in self.context.cookies() if cookie["name"] == "ce_analytics_session")
        self.assertEqual(cookie["value"], current_cookie["value"])
        self.assertTrue(cookie["httpOnly"])
        self.assertEqual(cookie["expires"], -1)
        with self.analytics.engine.connect() as connection:
            rows = list(connection.execute(select(site_analytics_events).where(
                site_analytics_events.c.occurred_at >= datetime.now(timezone.utc) - timedelta(minutes=2)
            )).mappings())
        self.assertEqual(len({row["session_id_hash"] for row in rows}), 1)
        self.assertTrue(any(row["utm_campaign"] == "tracking" for row in rows))
        for value in ("secret-search", "secret-id", "private-search-phrase", cookie["value"]):
            self.assertNotIn(value, str(rows))
            self.assertNotIn(value, json.dumps(events))

    def test_historical_download_tokens_are_redacted_before_public_reporting(self) -> None:
        """Migration must preserve counts, merge colliding daily keys, and hide old tokens."""
        import hashlib
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        migration_path = Path(webapp.BASE_DIR) / 'migrations/versions/20260930_0006_redact_analytics_downloads.py'
        spec = importlib.util.spec_from_file_location('analytics_redaction', migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with self.analytics.engine.begin() as connection:
            connection.execute(site_analytics_events.insert().values(
                occurred_at=datetime.combine(self.fixture_date, time(hour=18)),
                session_id_hash=self.primary_session,
                event_type='click', page_path='/checkout',
                click_target='internal:/download/order/synthetic-private-token.pdf',
            ))
            for path, count in (('/download/order/file.pdf', 3),
                ('/download/order/synthetic-private-token.pdf', 4),
                ('/download/order/another-private-token.pdf', 5)):
                connection.execute(site_request_status_daily_counts.insert().values(
                    event_date=self.fixture_date, page_path=path, status_code=404, request_count=count,
                ))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
        self.goto('/admin/analytics')
        html = self.page.content()
        self.assertNotIn('synthetic-private-token', html)
        self.assertNotIn('another-private-token', html)
        self.assertIn('Download order PDF', self.page.locator('main.analytics-dashboard').inner_text())
        with self.analytics.engine.connect() as connection:
            rows = list(connection.execute(select(site_request_status_daily_counts).where(
                site_request_status_daily_counts.c.page_path.like('/download/order/%')
            )).mappings())
            target = connection.execute(select(site_analytics_events.c.click_target).where(
                site_analytics_events.c.click_target == 'action:download-order-pdf'
            )).scalar_one()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['request_count'], 12)
        root = self._artifact_dir()
        root.mkdir(parents=True, exist_ok=True)
        (root / 'migration-verification.json').write_text(json.dumps({
            'migration_sha256': hashlib.sha256(migration_path.read_bytes()).hexdigest(),
            'preserved_daily_count': rows[0]['request_count'], 'click_target': target,
        }, indent=2) + '\n')
