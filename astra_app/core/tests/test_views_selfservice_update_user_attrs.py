from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import TestCase

from core import views_utils


class UpdateUserAttrsTests(TestCase):
    def test_name_changes_update_derived_name_fields_and_initials(self) -> None:
        client = Mock()

        existing = Mock()
        existing.first_name = "Alice"
        existing.last_name = "User"

        with patch("core.views_utils.FreeIPAUser.get_client", return_value=client, autospec=True):
            with patch("core.views_utils._invalidate_user_cache", autospec=True):
                with patch("core.views_utils._invalidate_users_list_cache", autospec=True):
                    with patch("core.views_utils.FreeIPAUser.get", return_value=existing, autospec=True):
                        skipped, applied = views_utils._update_user_attrs(
                            "alice",
                            direct_updates={"o_givenname": "Bob"},
                        )

        self.assertEqual(skipped, [])
        self.assertTrue(applied)

        _, kwargs = client.user_mod.call_args
        self.assertEqual(kwargs.get("o_givenname"), "Bob")
        self.assertEqual(kwargs.get("o_cn"), "Bob User")
        self.assertEqual(kwargs.get("o_gecos"), "Bob User")
        self.assertEqual(kwargs.get("o_displayname"), "Bob User")
        self.assertEqual(kwargs.get("o_initials"), "BU")

    def test_skips_not_allowed_attribute_and_retries(self):
        client = Mock()
        # First call fails due to attr not allowed, second call succeeds.
        client.user_mod.side_effect = [Exception("attribute 'fasNotAllowed' not allowed"), None]

        with patch("core.views_utils.FreeIPAUser.get_client", return_value=client, autospec=True):
            with patch("core.views_utils._invalidate_user_cache", autospec=True):
                with patch("core.views_utils._invalidate_users_list_cache", autospec=True):
                    with patch("core.views_utils.FreeIPAUser.get", autospec=True):
                        skipped, applied = views_utils._update_user_attrs(
                            "alice",
                            setattrs=["fasNotAllowed=alice:example.org", "fasLocale=en_US"],
                        )

        self.assertEqual(skipped, ["fasNotAllowed"])
        self.assertTrue(applied)
        self.assertEqual(client.user_mod.call_count, 2)

        # Second call should not include the disallowed attribute.
        _, kwargs = client.user_mod.call_args
        self.assertIn("o_setattr", kwargs)
        self.assertEqual(kwargs["o_setattr"], ["fasLocale=en_US"])

    def test_only_disallowed_attrs_returns_not_applied(self):
        client = Mock()
        client.user_mod.side_effect = [Exception("attribute fasNotAllowed not allowed")]

        with patch("core.views_utils.FreeIPAUser.get_client", return_value=client, autospec=True):
            with patch("core.views_utils._invalidate_user_cache", autospec=True):
                with patch("core.views_utils._invalidate_users_list_cache", autospec=True):
                    with patch("core.views_utils.FreeIPAUser.get", autospec=True):
                        skipped, applied = views_utils._update_user_attrs(
                            "alice",
                            setattrs=["fasNotAllowed=alice:example.org"],
                        )

        self.assertEqual(skipped, ["fasNotAllowed"])
        self.assertFalse(applied)
        self.assertEqual(client.user_mod.call_count, 1)

    def test_internal_error_clear_falls_back_to_setattr(self):
        client = Mock()
        # First call triggers internal error, second call succeeds.
        client.user_mod.side_effect = [Exception("Internal error"), None]

        with patch("core.views_utils.FreeIPAUser.get_client", return_value=client, autospec=True):
            with patch("core.views_utils._invalidate_user_cache", autospec=True):
                with patch("core.views_utils._invalidate_users_list_cache", autospec=True):
                    with patch("core.views_utils.FreeIPAUser.get", autospec=True):
                        skipped, applied = views_utils._update_user_attrs(
                            "alice",
                            delattrs=["fasNotAllowed="],
                        )

        self.assertEqual(skipped, [])
        self.assertTrue(applied)
        self.assertEqual(client.user_mod.call_count, 2)

        # Second call should have converted delattr clears into setattr clears.
        _, kwargs = client.user_mod.call_args
        self.assertNotIn("o_delattr", kwargs)
        self.assertEqual(kwargs.get("o_setattr"), ["fasNotAllowed="])
