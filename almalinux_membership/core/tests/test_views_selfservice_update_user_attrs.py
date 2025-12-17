from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import TestCase

from core import views_selfservice


class UpdateUserAttrsTests(TestCase):
    def test_skips_not_allowed_attribute_and_retries(self):
        client = Mock()
        # First call fails due to attr not allowed, second call succeeds.
        client.user_mod.side_effect = [Exception("attribute 'fasMatrix' not allowed"), None]

        with patch("core.views_selfservice.FreeIPAUser.get_client", return_value=client, autospec=True):
            with patch("core.views_selfservice._invalidate_user_cache", autospec=True):
                with patch("core.views_selfservice._invalidate_users_list_cache", autospec=True):
                    with patch("core.views_selfservice.FreeIPAUser.get", autospec=True):
                        skipped, applied = views_selfservice._update_user_attrs(
                            "alice",
                            setattrs=["fasMatrix=alice:example.org", "fasLocale=en_US"],
                        )

        self.assertEqual(skipped, ["fasMatrix"])
        self.assertTrue(applied)
        self.assertEqual(client.user_mod.call_count, 2)

        # Second call should not include the disallowed attribute.
        _, kwargs = client.user_mod.call_args
        self.assertIn("o_setattr", kwargs)
        self.assertEqual(kwargs["o_setattr"], ["fasLocale=en_US"])

    def test_only_disallowed_attrs_returns_not_applied(self):
        client = Mock()
        client.user_mod.side_effect = [Exception("attribute fasMatrix not allowed")]

        with patch("core.views_selfservice.FreeIPAUser.get_client", return_value=client, autospec=True):
            with patch("core.views_selfservice._invalidate_user_cache", autospec=True):
                with patch("core.views_selfservice._invalidate_users_list_cache", autospec=True):
                    with patch("core.views_selfservice.FreeIPAUser.get", autospec=True):
                        skipped, applied = views_selfservice._update_user_attrs(
                            "alice",
                            setattrs=["fasMatrix=alice:example.org"],
                        )

        self.assertEqual(skipped, ["fasMatrix"])
        self.assertFalse(applied)
        self.assertEqual(client.user_mod.call_count, 1)

    def test_internal_error_clear_falls_back_to_setattr(self):
        client = Mock()
        # First call triggers internal error, second call succeeds.
        client.user_mod.side_effect = [Exception("Internal error"), None]

        with patch("core.views_selfservice.FreeIPAUser.get_client", return_value=client, autospec=True):
            with patch("core.views_selfservice._invalidate_user_cache", autospec=True):
                with patch("core.views_selfservice._invalidate_users_list_cache", autospec=True):
                    with patch("core.views_selfservice.FreeIPAUser.get", autospec=True):
                        skipped, applied = views_selfservice._update_user_attrs(
                            "alice",
                            delattrs=["fasMatrix="],
                        )

        self.assertEqual(skipped, [])
        self.assertTrue(applied)
        self.assertEqual(client.user_mod.call_count, 2)

        # Second call should have converted delattr clears into setattr clears.
        _, kwargs = client.user_mod.call_args
        self.assertNotIn("o_delattr", kwargs)
        self.assertEqual(kwargs.get("o_setattr"), ["fasMatrix="])
