from __future__ import annotations

import tempfile
import re
from pathlib import Path

import app as webapp
from tests.common import BaseWebTest


class FrontendContractTests(BaseWebTest):
    def test_homepage_renders_latest_videos_strip_with_inline_expand_and_lazy_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reels_dir = Path(temp_dir)
            for idx in range(22):
                (reels_dir / f"clip_{idx:02d}.mp4").write_bytes(b"")

            original_path = webapp.REELS_PATH
            webapp.REELS_PATH = reels_dir
            try:
                response = self.client.get("/")
            finally:
                webapp.REELS_PATH = original_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("latest-videos-section", body)
        self.assertIn("latest-videos-shell scroll-cue-shell", body)
        self.assertIn("latest-videos-track inline-reel-track scroll-cue-track", body)
        self.assertIn("Inventory Reels", body)
        self.assertEqual(body.count("class=\"latest-video-card inline-reel-card\""), 15)
        self.assertIn("sticky-section-header", body)
        self.assertIn(">View All</a>", body)
        self.assertIn("/static/js/scroll_cue.js", body)
        self.assertIn("/static/js/inline_reels.js", body)
        self.assertIn("/static/js/home_reels.js", body)
        self.assertIn("href=\"/reels\"", body)
        self.assertIn("/static/reels/", body)
        self.assertIn("muted", body)
        self.assertIn("loop", body)
        self.assertIn("playsinline", body)
        self.assertIn("data-src=", body)
        self.assertIn("preload=\"none\"", body)
        self.assertIn("inline-reel-placeholder", body)
        self.assertNotIn("inline-reel-hitbox", body)
        self.assertNotIn("data-reel-name=", body)
        self.assertNotIn("latestVideoModal", body)
        self.assertNotIn("tiktok-embed", body)

    def test_homepage_hides_latest_videos_strip_when_no_reels_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reels_dir = Path(temp_dir)
            (reels_dir / "readme.txt").write_text("none", encoding="utf-8")

            original_path = webapp.REELS_PATH
            webapp.REELS_PATH = reels_dir
            try:
                response = self.client.get("/")
            finally:
                webapp.REELS_PATH = original_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertNotIn("latest-videos-section", body)
        self.assertIn("/static/js/scroll_cue.js", body)
        self.assertNotIn("/static/js/home_reels.js", body)

    def test_homepage_includes_flower_studs_section(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        body = response.get_data(as_text=True)
        self.assertIn("section-flower-studs", body)
        self.assertIn("Flower Studs", body)

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
        self.assertIn(
            "margin-top: clamp(.78rem, 2.8vw, 1.2rem) !important;", css)
        self.assertIn("margin-bottom: 0 !important;", css)
        self.assertIn("padding-bottom: clamp(.2rem, 1.4vw, .42rem);", css)

    def test_nav_search_centering_and_form_expansion_contracts(self) -> None:
        css = self.load_site_css()
        body = self.client.get("/").get_data(as_text=True)

        self.assertIn(".nav-search-center {", css)
        self.assertIn("position: absolute;", css)
        self.assertIn("top: 50%;", css)
        self.assertIn("transform: translate(-50%, -50%);", css)
        self.assertIn("width: min(52rem, calc(100vw - .9rem));", css)
        self.assertIn("function syncNavMetrics()", body)
        self.assertRegex(
            body,
            r'window\.addEventListener\("resize",\s*queueSyncNavMetrics,\s*\{\s*passive:\s*true\s*,?\s*\}\);',
        )
        self.assertNotIn(
            "window.addEventListener(\"scroll\", syncSearchCenter", body)

    def test_section_chip_row_and_cta_button_stay_vertically_centered(self) -> None:
        css = self.load_site_css()
        condensed = re.sub(r"\s+", " ", css)
        body = self.client.get("/").get_data(as_text=True)

        self.assertIn(".scroll-cue-shell {", css)
        self.assertIn(".scroll-cue-shell::after {", css)
        self.assertIn("pointer-events: none;", css)
        self.assertIn(".scroll-cue-shell.is-overflowing.can-scroll-right::after {", css)
        self.assertIn(".section-header-cats {", css)
        self.assertIn("width: 100%;", css)
        self.assertIn("align-items: center;", css)
        self.assertIn("min-height: 2.15rem;", css)
        self.assertIn(".section-header-cats-scroll {", css)
        self.assertIn("justify-content: flex-start;", css)
        self.assertIn("overflow-x: auto;", css)
        self.assertIn(".section-header-jump {", css)
        self.assertIn("align-self: center;", css)
        self.assertIn(".hero-actions {", css)
        self.assertIn(
            "margin-top: clamp(1.35rem, 2.9vw, 2rem) !important;", css)
        self.assertIn("padding-bottom: clamp(.18rem, .7vw, .42rem);", css)
        self.assertIn(".hero-action-btn {", css)
        self.assertIn("display: inline-flex;", css)
        self.assertIn("align-items: center;", css)
        self.assertIn("justify-content: center;", css)
        self.assertIn("text-align: center;", css)
        self.assertIn(
            "padding-block: max(var(--cta-btn-pad-y), calc((var(--cta-btn-min-height) - 1em) / 2));",
            css,
        )
        self.assertIn("class=\"section-header-cats scroll-cue-shell scroll-cue-shell--chips\"", body)
        self.assertIn("class=\"section-header-cats-scroll scroll-cue-track\"", body)
        self.assertIn(".hero-action-btn__label {", css)
        self.assertIn("line-height: 1;", css)
        self.assertIn(".hero-action-btn { flex: 0 1", condensed)
        self.assertIn("class=\"hero-action-btn__label\"", body)

    def test_main_and_background_layers_follow_actual_nav_height(self) -> None:
        css = self.load_site_css()
        body = self.client.get("/").get_data(as_text=True)
        condensed = re.sub(r"\s+", " ", css)

        self.assertIn("--nav-height: 66px;", css)
        self.assertIn("top: var(--nav-actual-height, var(--nav-height));", css)
        self.assertIn(
            "main { margin-top: 0 !important; padding-top: var(--nav-actual-height, var(--nav-height)) !important; }",
            condensed,
        )
        self.assertIn("<main>", body)
        self.assertNotIn("<main class=\"mt-5 pt-4\">", body)

    def test_page_titles_keep_centered_grid_layout_and_centered_back_button(self) -> None:
        css = self.load_site_css()
        condensed = re.sub(r"\s+", " ", css)
        about_body = self.client.get("/about").get_data(as_text=True)
        contact_body = self.client.get("/contact").get_data(as_text=True)
        reels_body = self.client.get("/reels").get_data(as_text=True)
        faqs_body = self.client.get("/faqs").get_data(as_text=True)
        team_body = self.client.get("/team").get_data(as_text=True)
        self.client.post("/api/cart/add", json={"code": self.valid_code, "qty": 1})
        cart_body = self.client.get("/cart").get_data(as_text=True)
        checkout_body = self.client.get("/checkout").get_data(as_text=True)
        order_submitted_response = self.client.post(
            "/checkout",
            data={
                "name": "Test Buyer",
                "company": "Sample Co",
                "phone_country": "United States (+1)",
                "phone_country_code": "us",
                "phone": "555-0101",
                "city": "Los Angeles",
                "state": "California",
                "country": "United States",
                "country_key": "us",
                "notes": "frontend contract",
            },
        )
        self.assertEqual(order_submitted_response.status_code, 200)
        order_submitted_body = order_submitted_response.get_data(as_text=True)

        self.assertIn(".page-title-row {", css)
        self.assertIn("display: grid;", css)
        self.assertIn("container-type: inline-size;", css)
        self.assertIn(
            "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);",
            css,
        )
        self.assertIn(".page-title-row .page-title-back {", css)
        self.assertIn(".page-title-row .page-title-action {", css)
        self.assertIn(".page-title-row .page-title-spacer {", css)
        self.assertIn("display: inline-flex;", css)
        self.assertIn("justify-content: center;", css)
        self.assertIn("text-align: center;", css)
        self.assertIn("white-space: nowrap;", css)
        self.assertIn("width: fit-content;", css)
        self.assertIn(".about-page .btn-outline-gold,", css)
        self.assertIn(".contact-page .btn-outline-gold,", css)
        self.assertIn(".reels-page .btn-outline-gold,", css)
        self.assertIn(".faqs-page .btn-outline-gold,", css)
        self.assertIn(".team-page .btn-outline-gold,", css)
        self.assertIn(".cart-page .btn-outline-gold {", css)
        self.assertIn("background: rgba(13, 13, 13, 0.88) !important;", css)
        self.assertIn("backdrop-filter: blur(2px);", css)
        self.assertIn(".cart-page .cart-summary-bar,", css)
        self.assertIn(".checkout-page .checkout-summary-bar {", css)
        self.assertIn(".cart-page .cart-summary-bar__center,", css)
        self.assertIn(".checkout-page .checkout-summary-bar__center {", css)
        self.assertIn(".cart-page .cart-summary-bar__right,", css)
        self.assertIn(".checkout-page .checkout-summary-bar__right {", css)
        self.assertIn(".checkout-page .checkout-phone-group {", css)
        self.assertIn("grid-template-columns: minmax(13rem, 16.5rem) minmax(0, 1fr);", css)
        self.assertIn(".page-title-row > h1 {", css)
        self.assertIn("grid-column: 2;", css)
        self.assertIn("justify-self: center;", css)
        self.assertIn("font-size: clamp(1.75rem, 3.3vw, 2.5rem);", css)
        self.assertIn("white-space: nowrap;", css)
        self.assertIn("text-align: center;", condensed)
        self.assertIn("font-size: clamp(1.45rem, 5.1cqw, 2.05rem);", css)
        self.assertIn("letter-spacing: -.015em;", css)
        self.assertIn("class=\"page-title-row mb-4\"", about_body)
        self.assertIn("class=\"container py-5 about-page\"", about_body)
        self.assertIn("href=\"/contact\"", about_body)
        self.assertIn(">Contact Us</a>", about_body)
        self.assertIn("class=\"page-title-row mb-4\"", contact_body)
        self.assertIn("href=\"/team\"", contact_body)
        self.assertIn(">Meet our Team</a>", contact_body)
        self.assertIn("class=\"container py-5 reels-page\"", reels_body)
        self.assertIn("class=\"page-title-row mb-4\"", reels_body)
        self.assertIn("class=\"btn btn-outline-gold page-title-back\"", reels_body)
        self.assertIn("class=\"page-title-spacer btn btn-outline-gold\" aria-hidden=\"true\"", reels_body)
        self.assertIn(">Inventory Reels</h1>", reels_body)
        self.assertIn("class=\"container py-5 faqs-page\"", faqs_body)
        self.assertIn("id=\"faqsAccordion\"", faqs_body)
        self.assertIn("class=\"accordion faqs-accordion mt-3\"", faqs_body)
        self.assertIn("data-bs-toggle=\"collapse\"", faqs_body)
        self.assertIn("How do I place an order?", faqs_body)
        self.assertIn("class=\"container py-5 team-page\"", team_body)
        self.assertIn("class=\"page-title-row mb-4\"", team_body)
        self.assertIn("class=\"btn btn-outline-gold page-back-btn page-title-back\"", team_body)
        self.assertIn("class=\"page-title-spacer btn btn-outline-gold page-back-btn\" aria-hidden=\"true\"", team_body)
        self.assertIn("class=\"page-title-row mb-3\"", cart_body)
        self.assertIn("class=\"btn btn-outline-gold cart-back-btn page-title-back\"", cart_body)
        self.assertIn("class=\"cart-summary-bar mt-3\" id=\"cartSummaryBar\"", cart_body)
        self.assertIn("class=\"cart-summary-bar__left\"", cart_body)
        self.assertIn("class=\"cart-summary-bar__center\"", cart_body)
        self.assertIn("class=\"cart-summary-bar__right\"", cart_body)
        self.assertIn("class=\"page-title-row mb-3\"", checkout_body)
        self.assertIn("href=\"/cart\"", checkout_body)
        self.assertIn("class=\"btn btn-outline-gold page-title-back\"", checkout_body)
        self.assertIn("class=\"page-title-spacer btn btn-outline-gold\" aria-hidden=\"true\"", checkout_body)
        self.assertIn(">Submit Inquiry</h1>", checkout_body)
        self.assertIn("class=\"checkout-summary-bar mt-3\"", checkout_body)
        self.assertIn("name=\"phone_country_code\"", checkout_body)
        self.assertIn("id=\"checkoutPhoneCountry\"", checkout_body)
        self.assertIn("list=\"checkoutPhoneCountryList\"", checkout_body)
        self.assertIn("name=\"city\"", checkout_body)
        self.assertIn("name=\"state\"", checkout_body)
        self.assertIn("name=\"country\"", checkout_body)
        self.assertIn("name=\"country_key\"", checkout_body)
        self.assertIn("list=\"checkoutCountryList\"", checkout_body)
        self.assertIn("list=\"checkoutStateList\"", checkout_body)
        self.assertIn("value=\"United States (+1)\"", checkout_body)
        self.assertIn("value=\"Mexico (+52)\"", checkout_body)
        self.assertIn("class=\"checkout-summary-bar__left\" aria-hidden=\"true\"", checkout_body)
        self.assertIn("class=\"checkout-summary-bar__center\"", checkout_body)
        self.assertIn("class=\"d-flex align-items-center flex-wrap gap-2 checkout-summary-metrics\"", checkout_body)
        self.assertIn("class=\"checkout-summary-bar__right\"", checkout_body)
        self.assertIn("type=\"submit\">Submit Inquiry</button>", checkout_body)
        self.assertIn("class=\"page-title-row mb-3\"", order_submitted_body)
        self.assertIn("href=\"/#section-studs\"", order_submitted_body)
        self.assertIn(">Order Submitted</h1>", order_submitted_body)
        self.assertIn("class=\"d-flex flex-wrap gap-2 align-items-center justify-content-center mt-2 order-submitted-download-actions\"", order_submitted_body)
        self.assertIn(">Download CSV</a>", order_submitted_body)
        self.assertIn(">Download PDF</a>", order_submitted_body)
        self.assertIn("href=\"/contact\"", cart_body)
        self.assertIn(">Contact Us</a>", cart_body)
        self.assertIn(">Shopping Cart</h1>", cart_body)

    def test_faqs_page_and_nav_drawer_keep_gold_accordion_contract(self) -> None:
        css = self.load_site_css()
        home_body = self.client.get("/").get_data(as_text=True)
        faqs_body = self.client.get("/faqs").get_data(as_text=True)

        self.assertIn("href=\"/faqs\"", home_body)
        self.assertIn("FAQs</a>", home_body)
        self.assertIn(".navbar .navbar-collapse .navbar-nav {", css)
        self.assertRegex(
            home_body,
            r'<li class="nav-item">\s*<a class="nav-link" href="/faqs">FAQs</a>\s*</li>',
        )
        self.assertIn(".faqs-page .faqs-accordion {", css)
        self.assertIn(".faqs-page .faqs-accordion .accordion-button {", css)
        self.assertIn(".faqs-page .faqs-accordion .accordion-body {", css)
        self.assertIn("class=\"accordion-button collapsed\"", faqs_body)
        self.assertIn("aria-expanded=\"false\"", faqs_body)
        self.assertNotIn("accordion-collapse collapse show", faqs_body)
        self.assertIn("We want you to be happy.", faqs_body)
        self.assertIn("The minimum order is $1000.", faqs_body)

    def test_sticky_category_row_stays_flush_under_navbar(self) -> None:
        css = self.load_site_css()
        condensed = re.sub(r"\s+", " ", css)

        self.assertIn(
            ".sticky-section-header { position: sticky; top: var(--nav-actual-height, var(--nav-height));",
            condensed,
        )
        self.assertIn(
            ".section-anchor { scroll-margin-top: var(--nav-actual-height, var(--nav-height)); }",
            condensed,
        )
        self.assertNotIn(
            "top: calc(var(--nav-actual-height, var(--nav-height)) + 5px);",
            css,
        )
        self.assertNotIn(
            "scroll-margin-top: calc(var(--nav-actual-height, var(--nav-height)) + 5px);",
            css,
        )

    def test_catalog_card_images_are_lazy_loaded(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("class=\"card-img-top product-img\"", body)
        self.assertIn("loading=\"lazy\"", body)
        self.assertIn("decoding=\"async\"", body)
        self.assertIn("fetchpriority=\"low\"", body)

    def test_catalog_resize_logic_is_raf_throttled(self) -> None:
        script = (Path(webapp.BASE_DIR) / "static" / "js" /
                  "catalog.js").read_text(encoding="utf-8")

        self.assertIn("let resizeRafId = 0;", script)
        self.assertIn(
            "resizeRafId = window.requestAnimationFrame(() => {", script)
        self.assertIn("window.addEventListener(\"resize\", () => {", script)
        self.assertIn("}, { passive: true });", script)

    def test_catalog_supports_expanded_long_press_and_detail_link(self) -> None:
        script = (Path(webapp.BASE_DIR) / "static" / "js" /
                  "catalog.js").read_text(encoding="utf-8")
        body = self.client.get("/").get_data(as_text=True)

        self.assertIn("const LONG_PRESS_MS = 520;", script)
        self.assertIn(
            "if (!card.classList.contains(\"is-open\")) return;", script)
        self.assertIn("window.location.assign(detailUrl);", script)
        self.assertIn(".product-detail-link", script)
        self.assertIn("data-detail-url=", body)
        self.assertIn("class=\"small code-badge product-detail-link", body)

    def test_inline_reels_leave_active_video_controls_to_native_ui(self) -> None:
        script = (Path(webapp.BASE_DIR) / "static" / "js" /
                  "inline_reels.js").read_text(encoding="utf-8")
        css = self.load_site_css()

        self.assertNotIn("function toggleCardAudio(card)", script)
        self.assertNotIn("video.muted = !video.muted;", script)
        self.assertNotIn("if (target.closest(\"video\")) {", script)
        self.assertNotIn(".inline-reel-hitbox {", css)
        self.assertNotIn(".inline-reel-card.is-active .inline-reel-hitbox {", css)
        self.assertIn("function revealControlsForCard(card, options = {})", script)
        self.assertIn("setControlsVisibility(video, false);", script)
        self.assertIn("playMuted(firstVideo);", script)
        self.assertNotIn("playMuted(firstVideo, true);", script)
        self.assertIn('void activateCard(card, { scrollAlignment: "start" });', script)
        self.assertIn('void activateCard(nextCard, { scrollAlignment: "start" });', script)
        self.assertIn("track.addEventListener(\"focusin\", (event) => {", script)
        self.assertIn('"touchstart"', script)
        self.assertIn("if (card === activeCard) {", script)
        self.assertIn("return;", script)

    def test_inline_reels_pause_out_of_view_and_autoplay_next_preserves_audio_state_without_scroll_jump(self) -> None:
        script = (Path(webapp.BASE_DIR) / "static" / "js" /
                  "inline_reels.js").read_text(encoding="utf-8")

        self.assertIn("let preferredMutedState = true;", script)
        self.assertIn("let preferredVolumeLevel = 1;", script)
        self.assertIn("let viewportPausedPlayback = false;", script)
        self.assertIn("let keepFullscreenOnAdvance = false;", script)
        self.assertIn("let fullscreenHostCard = null;", script)
        self.assertIn("let fullscreenPlaybackIndex = -1;", script)
        self.assertIn("function rememberPreferredPlaybackState(video)", script)
        self.assertIn("function pauseActiveCardPlaybackForViewport()", script)
        self.assertIn("function resumeViewportPausedPlayback()", script)
        self.assertIn("async function continueFullscreenPlayback(", script)
        self.assertIn("async function transferWebkitFullscreenPlayback(currentVideo, nextCard)", script)
        self.assertIn("nextVideo.webkitEnterFullscreen();", script)
        self.assertIn("void syncInlineCardFromFullscreenExit();", script)
        self.assertIn("function alignCardToTrackStart(card, behavior = \"smooth\")", script)
        self.assertIn("function settleCardAtTrackStart(card, behavior = \"smooth\")", script)
        self.assertIn("function isVideoPresentingFullscreen(video)", script)
        self.assertIn("video.webkitEnterFullscreen();", script)
        self.assertIn("let trackInViewport = true;", script)
        self.assertIn("function setupViewportPauseGuard()", script)
        self.assertIn("resumeViewportPausedPlayback();", script)
        self.assertIn("if (pauseWhenOutOfView && !trackInViewport)", script)
        self.assertIn("video.volume = preferredVolumeLevel;", script)
        self.assertIn("video.muted = preferredMutedState;", script)
        self.assertIn("rememberPreferredPlaybackState(currentVideo);", script)
        self.assertIn("scrollAlignment: \"start\"", script)
        self.assertIn("preserveFullscreen: keepFullscreen", script)
        self.assertNotIn("function isVideoAudible(video)", script)
        self.assertIn("video.addEventListener(\"volumechange\", () => {", script)
        self.assertIn("const volumeChangeRequestedWhileMuted =", script)
        self.assertIn("window.triggerScrollCueAttention(track);", script)
        self.assertIn("void playNextReel(card);", script)

    def test_homepage_reels_enable_out_of_view_pause_guard(self) -> None:
        script = (Path(webapp.BASE_DIR) / "static" / "js" /
                  "home_reels.js").read_text(encoding="utf-8")

        self.assertIn("pauseWhenOutOfView: true", script)

    def test_reels_scroll_cue_uses_triple_arrow_attention_style(self) -> None:
        css = self.load_site_css()
        script = (Path(webapp.BASE_DIR) / "static" / "js" /
                  "scroll_cue.js").read_text(encoding="utf-8")

        self.assertIn(".scroll-cue-shell--reels::after {", css)
        self.assertIn('content: \">\";', css)
        self.assertIn(".scroll-cue-shell--reels.is-attentioning::after {", css)
        self.assertIn("@keyframes scrollCueReelsAttention", css)
        self.assertNotIn("rightButton.click();", script)

    def test_inline_reels_hover_keeps_autoplay_muted(self) -> None:
        script = (Path(webapp.BASE_DIR) / "static" / "js" /
                  "inline_reels.js").read_text(encoding="utf-8")

        self.assertNotIn("requestAudiblePlayback", script)
        self.assertIn("scrollIntoView: false", script)
        self.assertIn('track.addEventListener("ce:scroll-cue-activate-visible", (event) => {', script)
        self.assertIn('void activateCard(nextCard, { scrollAlignment: "start" });', script)

    def test_active_reels_use_full_frame_sizing(self) -> None:
        css = self.load_site_css()

        self.assertIn(".reels-page .reel-card.is-active .inline-reel-video {", css)
        self.assertIn("object-fit: contain;", css)
        self.assertIn("--inline-reel-active-width: calc(var(--inline-reel-height) * 9 / 16);", css)
        self.assertIn("--inline-reel-mobile-active-width: calc(var(--inline-reel-mobile-height) * 9 / 16);", css)
        self.assertIn("--inline-reel-active-width: clamp(304px, 34vw, 354px);", css)
        self.assertIn("--inline-reel-mobile-active-width: clamp(234px, 62vw, 272px);", css)

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
            'class="navbar navbar-dark bg-black border-bottom border-gold fixed-top"', body)
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

    def test_visual_polish_contracts_for_hero_header_and_cards(self) -> None:
        css = self.load_site_css()
        condensed = re.sub(r"\s+", " ", css)

        self.assertIn("width: clamp(172px, 41vw, 352px);", css)
        self.assertIn("width: clamp(148px, 51vw, 262px);", css)
        self.assertIn("min-height: clamp(220px, 31vh, 360px);", css)
        self.assertIn("min-height: clamp(196px, 27vh, 286px);", css)
        self.assertIn("--hero-pad-y: clamp(1.65rem, 3.2vw, 2.3rem);", css)
        self.assertIn("--hero-pad-y: clamp(1.1rem, 3.8vw, 1.55rem);", css)
        self.assertIn("padding-top: var(--hero-pad-y);", css)
        self.assertIn("padding-bottom: var(--hero-pad-y);", css)
        self.assertIn("opacity: 0.62;", css)
        self.assertIn("opacity: 0.70;", css)
        self.assertIn(
            ".catalog-section-title-rule { display: none; }", condensed)
        self.assertIn(".section-header-row::after", css)
        self.assertIn("box-shadow: 0 15px 40px rgba(0, 0, 0, 0.45);", css)
        self.assertIn(".code-badge", css)
        self.assertIn("padding: .18rem .62rem;", css)
        self.assertIn("rgb(var(--gold-rgb) / 0.84)", css)
