from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from python_freeipa import exceptions

from core.backends import FreeIPAUser


class FreeIPAServiceClientRetryTests(TestCase):
    def setUp(self):
        cache.delete("freeipa_users_all")
        cache.delete("freeipa_user_alice")

    def test_all_retries_on_unauthorized(self):
        first_client = Mock()
        second_client = Mock()

        first_client.user_find.side_effect = exceptions.Unauthorized()
        second_client.user_find.return_value = {"result": [{"uid": ["alice"]}]}

        with patch(
            "core.backends.FreeIPAUser.get_client",
            autospec=True,
            side_effect=[first_client, second_client],
        ) as get_client:
            users = FreeIPAUser.all()

        self.assertEqual([u.username for u in users], ["alice"])
        self.assertEqual(get_client.call_count, 2)

    def test_get_retries_on_unauthorized(self):
        first_client = Mock()
        second_client = Mock()

        first_client.user_show.side_effect = exceptions.Unauthorized()
        second_client.user_show.return_value = {"result": {"uid": ["alice"], "mail": ["a@example.com"]}}

        with patch(
            "core.backends.FreeIPAUser.get_client",
            autospec=True,
            side_effect=[first_client, second_client],
        ) as get_client:
            user = FreeIPAUser.get("alice")

        self.assertIsNotNone(user)
        assert user is not None
        self.assertEqual(user.username, "alice")
        self.assertEqual(get_client.call_count, 2)
