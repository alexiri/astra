from __future__ import annotations

from django.test import TestCase

from core.forms_selfservice import AddressForm


class AddressFormValidationTests(TestCase):
    def test_country_code_uppercases_and_accepts_valid_alpha2(self):
        form = AddressForm(
            data={
                "street": "Main St 5",
                "l": "Springfield",
                "st": "Illinois",
                "postalcode": "62701",
                "c": "us",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["c"], "US")

    def test_country_code_rejects_invalid_alpha2(self):
        form = AddressForm(
            data={
                "street": "Main St 5",
                "l": "Springfield",
                "st": "Illinois",
                "postalcode": "62701",
                "c": "ZZ",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("c", form.errors)

    def test_country_code_is_required(self):
        form = AddressForm(data={"street": "Main St 5"})
        self.assertFalse(form.is_valid())
        self.assertIn("c", form.errors)
