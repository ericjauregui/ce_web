from __future__ import annotations

from tests.e2e.common import BaseE2ETest


class MobileCheckoutE2ETests(BaseE2ETest):
    browser_name = "webkit"
    viewport = {"width": 390, "height": 844}
    enforce_clean_browser = True

    def test_checkout_mobile_uses_native_selects_without_prefill(self) -> None:
        self.open_checkout_with_item()

        phone_country = self.page.locator("#checkoutPhoneCountry")
        phone_country_code = self.page.locator("#checkoutPhoneCountryCode")
        country = self.page.locator("#checkoutCountry")
        country_key = self.page.locator("#checkoutCountryKey")
        state_value = self.page.locator("#checkoutState")
        state_select = self.page.locator("#checkoutStateSelect")
        state_text = self.page.locator("#checkoutStateText")

        self.assertEqual(phone_country.input_value(), "")
        self.assertEqual(phone_country_code.input_value(), "")
        self.assertEqual(country.input_value(), "")
        self.assertEqual(country_key.input_value(), "")
        self.assertEqual(state_value.input_value(), "")
        self.assertTrue(state_select.is_hidden())
        self.assertTrue(state_text.is_visible())

        state_text.fill("California")
        state_text.blur()
        self.assertEqual(state_value.input_value(), "California")

        phone_country.select_option(index=1)
        self.page.wait_for_function(
            "() => document.getElementById('checkoutPhoneCountryCode')?.value !== ''"
        )
        self.assertNotEqual(phone_country_code.input_value(), "")

        country.select_option(label=self.us_country_label)
        self.page.wait_for_function(
            "expectedKey => document.getElementById('checkoutCountryKey')?.value === expectedKey",
            arg="us",
        )
        self.assertEqual(country_key.input_value(), "us")
        self.assertTrue(state_select.is_visible())
        self.assertTrue(state_text.is_hidden())
        self.assertEqual(state_select.input_value(), "California")
        self.assertEqual(state_value.input_value(), "California")
        self.assertGreater(state_select.locator("option").count(), 2)

        first_state = self.page.evaluate(
            """
            () => {
              const select = document.getElementById('checkoutStateSelect');
              const option = Array.from(select?.options || []).find((entry) => entry.value);
              return option ? option.value : '';
            }
            """
        )
        self.assertTrue(first_state)
        state_select.select_option(value=first_state)
        self.assertEqual(state_value.input_value(), first_state)

        self.assertTrue(self.country_without_subdivisions_label)
        self.assertTrue(self.country_without_subdivisions_key)
        country.select_option(label=self.country_without_subdivisions_label)
        self.page.wait_for_function(
            "expectedKey => document.getElementById('checkoutCountryKey')?.value === expectedKey",
            arg=self.country_without_subdivisions_key,
        )

        self.assertEqual(country_key.input_value(), self.country_without_subdivisions_key)
        self.assertEqual(state_value.input_value(), "")
        self.assertTrue(state_text.is_visible())
        self.assertTrue(state_select.is_hidden())

        state_text.fill("Freeform Region")
        state_text.blur()
        self.assertEqual(state_value.input_value(), "Freeform Region")