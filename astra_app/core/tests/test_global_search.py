from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase


class GlobalSearchTests(TestCase):
    def _login_as_freeipa(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_search_requires_login(self) -> None:
        resp = self.client.get("/search/?q=a")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.headers.get("Location", ""))

    def test_search_returns_users_and_groups(self) -> None:
        self._login_as_freeipa("admin")

        users = [
            SimpleNamespace(username="jim", get_full_name=lambda: "Jim Jones"),
            SimpleNamespace(username="jimbo", get_full_name=lambda: "Jimbo Jones"),
            SimpleNamespace(username="bob", get_full_name=lambda: "Bob User"),
        ]

        groups = [
            SimpleNamespace(cn="example-jin", description="", fas_group=True),
            SimpleNamespace(cn="gitdocker-example", description="", fas_group=True),
            SimpleNamespace(cn="ipa_only", description="", fas_group=False),
        ]

        with (
            patch("core.backends.FreeIPAUser.all", return_value=users),
            patch("core.backends.FreeIPAGroup.all", return_value=groups),
        ):
            resp = self.client.get("/search/?q=ji")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual([u["username"] for u in data["users"]], ["jim", "jimbo"])
        self.assertNotIn("bob", {u["username"] for u in data["users"]})
        self.assertEqual([g["cn"] for g in data["groups"]], ["example-jin"])
        self.assertNotIn("ipa_only", {g["cn"] for g in data["groups"]})

    def test_search_empty_query_returns_empty_results(self) -> None:
        self._login_as_freeipa("admin")

        with (
            patch("core.backends.FreeIPAUser.all", return_value=[SimpleNamespace(username="alice", get_full_name=lambda: "")]),
            patch("core.backends.FreeIPAGroup.all", return_value=[SimpleNamespace(cn="fas1", description="", fas_group=True)]),
        ):
            resp = self.client.get("/search/?q=")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"users": [], "groups": []})
