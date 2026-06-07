from __future__ import annotations

from tests.e2e.common import BaseE2ETest


def _is_known_reel_abort(message: str) -> bool:
    normalized = message.lower()
    return "err_aborted" in normalized and "/static/reels/" in normalized


class MobileCheckoutE2ETests(BaseE2ETest):
    browser_name = "webkit"
    viewport = {"width": 390, "height": 844}
    enforce_clean_browser = True

    @staticmethod
    def is_ignored_request_failure(message: str) -> bool:
        return _is_known_reel_abort(message)

    def test_checkout_mobile_comboboxes_filter_and_select(self) -> None:
        self.open_checkout_with_item()

        phone_country = self.page.locator("#checkoutPhoneCountry")
        phone_country_code = self.page.locator("#checkoutPhoneCountryCode")
        country = self.page.locator("#checkoutCountry")
        country_key = self.page.locator("#checkoutCountryKey")
        state = self.page.locator("#checkoutState")
        state_options = self.page.locator("#checkoutStateCombobox .checkout-combobox__option")
        phone_options = self.page.locator("#checkoutPhoneCountryCombobox .checkout-combobox__option")

        self.assertEqual(phone_country.input_value(), "")
        self.assertEqual(phone_country_code.input_value(), "")
        self.assertEqual(country.input_value(), "")
        self.assertEqual(country_key.input_value(), "")
        self.assertEqual(state.input_value(), "")

        state.fill("cal")
        self.assertIn("California", state_options.first.inner_text())
        self.assertIn("United States", state_options.first.inner_text())
        state_options.first.click()

        self.page.wait_for_function(
            "() => document.getElementById('checkoutCountryKey')?.value === 'us'"
        )
        self.assertEqual(country.input_value(), "United States")
        self.assertEqual(country_key.input_value(), "us")
        self.assertEqual(state.input_value(), "California")

        phone_country.fill("uni")
        option_texts = phone_options.evaluate_all(
            "nodes => nodes.slice(0, 3).map((node) => node.textContent.trim())"
        )
        self.assertTrue(option_texts)
        self.assertIn("United States", option_texts[0])
        phone_options.first.click()
        self.page.wait_for_function(
            "() => document.getElementById('checkoutPhoneCountryCode')?.value !== ''"
        )
        self.assertEqual(phone_country_code.input_value(), "us")
        self.assertEqual(phone_country.input_value(), "United States (+1)")

class DesktopCheckoutE2ETests(BaseE2ETest):
    browser_name = "chromium"
    viewport = {"width": 1280, "height": 900}
    enforce_clean_browser = True

    @staticmethod
    def is_ignored_request_failure(message: str) -> bool:
        return _is_known_reel_abort(message)

    def test_checkout_desktop_comboboxes_filter_and_select(self) -> None:
        self.open_checkout_with_item()

        country = self.page.locator("#checkoutCountry")
        country_key = self.page.locator("#checkoutCountryKey")
        state = self.page.locator("#checkoutState")
        phone_country = self.page.locator("#checkoutPhoneCountry")
        phone_country_code = self.page.locator("#checkoutPhoneCountryCode")

        country_options = self.page.locator("#checkoutCountryCombobox .checkout-combobox__option")
        state_options = self.page.locator("#checkoutStateCombobox .checkout-combobox__option")
        phone_options = self.page.locator("#checkoutPhoneCountryCombobox .checkout-combobox__option")

        country.fill("uni")
        country_texts = country_options.evaluate_all(
            "nodes => nodes.slice(0, 3).map((node) => node.textContent.trim())"
        )
        self.assertTrue(country_texts)
        self.assertIn("United States", country_texts[0])
        self.assertTrue(any("United Arab Emirates" in text for text in country_texts))
        self.assertTrue(any("United Kingdom" in text for text in country_texts))
        country_options.first.click()

        self.page.wait_for_function(
            "expectedKey => document.getElementById('checkoutCountryKey')?.value === expectedKey",
            arg="us",
        )
        self.assertEqual(country_key.input_value(), "us")
        self.assertEqual(country.input_value(), "United States")

        state.fill("new")
        first_state_text = state_options.first.inner_text()
        self.assertIn("New", first_state_text)
        state_options.first.click()
        self.assertIn("New", state.input_value())

        phone_country.fill("uni")
        phone_texts = phone_options.evaluate_all(
            "nodes => nodes.slice(0, 3).map((node) => node.textContent.trim())"
        )
        self.assertTrue(phone_texts)
        self.assertIn("United States", phone_texts[0])
        phone_options.first.click()
        self.assertEqual(phone_country_code.input_value(), "us")
        self.assertEqual(phone_country.input_value(), "United States (+1)")