from __future__ import annotations

import re

from tests.common import BaseWebTest


class FrontendContractTests(BaseWebTest):
    def test_nav_search_clear_logic_uses_input_and_search_events(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("async function handleClearedSearch()", body)
        self.assertIn("input.addEventListener(\"search\", maybeClearSearch)", body)
        self.assertIn("input.addEventListener(\"input\", maybeClearSearch)", body)
        self.assertIn("setOpen(false, { restoreValue: false });", body)
        self.assertIn("window.history.replaceState(null, \"\", target.pathname);", body)

    def test_hover_rules_are_scoped_to_hover_capable_devices(self) -> None:
        css = self.load_site_css()

        self.assertIn("@media (hover: hover) and (pointer: fine)", css)
        self.assertIn(".social-brand-link:hover", css)
        self.assertIn(".team-inline-icon:hover", css)
        self.assertIn(".team-phone-link:hover", css)
        self.assertIn(".chip:hover", css)
        self.assertIn(".nav-search-trigger:hover", css)
        self.assertIn(".cart-link:hover svg", css)

    def test_touch_devices_neutralize_outline_button_hover_state(self) -> None:
        css = self.load_site_css()
        condensed = re.sub(r"\s+", " ", css)

        self.assertIn("@media (hover: none), (pointer: coarse)", condensed)
        self.assertIn(".btn-outline-gold { --bs-btn-hover-bg: transparent;", condensed)
        self.assertIn("--bs-btn-hover-color: var(--gold);", condensed)
        self.assertIn(".btn-outline-gold:hover { color: var(--gold);", condensed)

    def test_mobile_hero_and_catalog_transition_stays_flush(self) -> None:
        css = self.load_site_css()
        condensed = re.sub(r"\s+", " ", css)

        self.assertIn("@media (max-width: 767.98px)", css)
        self.assertIn("background-size: min(520px, 108vw);", css)
        self.assertIn("background-position: center 30%;", css)
        self.assertIn(
            "header.hero+section.py-5 { padding-top: 0 !important; }", condensed)
        self.assertIn("min-height: inherit;", css)
        self.assertIn("margin-top: auto !important;", css)
        self.assertIn("margin-bottom: auto !important;", css)

    def test_stylesheet_has_balanced_braces(self) -> None:
        css = self.load_site_css()

        no_comments = re.sub(r"/\*[\s\S]*?\*/", "", css)
        no_strings = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "", no_comments)

        depth = 0
        for index, char in enumerate(no_strings):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth < 0:
                    line = no_strings.count("\n", 0, index) + 1
                    self.fail(f"Unexpected closing brace in style.css near line {line}")

        self.assertEqual(depth, 0, "Unbalanced braces detected in style.css")

    def test_stylesheet_keeps_critical_ui_selectors(self) -> None:
        css = self.load_site_css()

        required_tokens = [
            "--gold-rgb:",
            ".navbar.fixed-top.border-gold",
            ".section-header-row",
            ".section-header-cats",
            ".chip",
            ".product-card",
            ".nav-search-trigger",
            ".team-inline-icon",
            "@media (max-width: 767.98px)",
            "@media (hover: none)",
        ]

        for token in required_tokens:
            self.assertIn(token, css)

    def test_product_qty_control_block_closes_before_qty_center_group(self) -> None:
        css = self.load_site_css()

        pattern = re.compile(
            r"\.product-qty-control\s*\{[\s\S]*?\}\s*\.qty-center-group\s*\{",
            re.MULTILINE,
        )
        self.assertRegex(css, pattern)

    def test_gold_theme_borders_follow_outline_tokens(self) -> None:
        css = self.load_site_css()
        condensed = re.sub(r"\s+", " ", css)

        self.assertIn("--gold-outline:", css)
        self.assertIn("--gold-outline-strong:", css)
        self.assertIn(
            ".border-gold { border-color: var(--gold-outline) !important; }", condensed)

        forbidden_full_gold_borders = re.compile(
            r"border(?:-color)?\s*:\s*[^;]*var\(--gold\)\b",
            re.IGNORECASE,
        )
        self.assertIsNone(
            forbidden_full_gold_borders.search(css),
            "Theme regression: border rules must use --gold-outline or --gold-outline-strong, not --gold.",
        )

    def test_footer_uses_shared_gold_border_class(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn(
            "<footer class=\"text-center py-4 border-top border-gold", body)

    def test_navbar_and_footer_share_border_gold_utility(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn(
            "<nav class=\"navbar navbar-dark bg-black border-bottom border-gold fixed-top\"", body)
        self.assertIn(
            "<footer class=\"text-center py-4 border-top border-gold", body)

    def test_homepage_hero_uses_full_logo_asset(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("assets/ce_logo_full.png", body)
        self.assertIn("class=\"hero-logo\"", body)

    def test_navbar_uses_shape_logo_asset(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("assets/ce_logo_shape.png", body)
