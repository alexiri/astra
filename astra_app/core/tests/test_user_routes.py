from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from core.backends import FreeIPAUser
from core.views_auth import FreeIPALoginView


class UserRoutesTests(TestCase):
    def _login_as_freeipa(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_user_profile_route_renders(self) -> None:
        username = "admin"
        self._login_as_freeipa(username)

        fu = FreeIPAUser(username, {"uid": [username], "givenname": ["A"], "sn": ["Dmin"], "mail": ["a@example.org"]})

        with patch("core.backends.FreeIPAUser.get", return_value=fu):
            resp = self.client.get(f"/user/{username}/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(username, resp.content.decode("utf-8"))

    def test_users_list_route_renders(self) -> None:
        self._login_as_freeipa("admin")

        users = [
            SimpleNamespace(username="alice", get_full_name=lambda: "Alice User"),
            SimpleNamespace(username="bob", get_full_name=lambda: "Bob User"),
        ]

        with patch("core.backends.FreeIPAUser.all", return_value=users):
            resp = self.client.get("/users/")

        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("alice", content)
        self.assertIn("bob", content)


class LoginRedirectTests(TestCase):
    def test_freeipa_login_view_redirects_to_canonical_user_profile_url(self) -> None:
        factory = RequestFactory()
        request = factory.get("/login/")
        setattr(request, "user", cast(Any, SimpleNamespace(get_username=lambda: "alice")))

        view = FreeIPALoginView()
        view.request = request

        self.assertEqual(view.get_success_url(), "/user/alice/")
