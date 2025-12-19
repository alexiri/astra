from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.backends import FreeIPAUser


class AdminDeleteSelectedIPAUserTests(TestCase):
    def _login_as_freeipa_admin(self, username: str = "alice") -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_delete_selected_action_does_not_crash(self) -> None:
        """Regression test for Django admin bulk-delete on unmanaged IPAUser.

        Django's built-in delete action calls admin utils like model_ngettext()
        with the queryset object itself. Our changelist uses a lightweight
        QuerySet-like wrapper, so it must provide enough model metadata for the
        admin action to render its confirmation page.
        """

        self._login_as_freeipa_admin("alice")

        admin_user = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": ["admins"]})
        target_user = FreeIPAUser(
            "bob",
            {
                "uid": ["bob"],
                "givenname": ["Bob"],
                "sn": ["Example"],
                "mail": ["bob@example.org"],
                "memberof_group": [],
            },
        )

        def _fake_get(username: str):
            if username == "alice":
                return admin_user
            if username == "bob":
                return target_user
            return None

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_fake_get),
            patch("core.backends.FreeIPAUser.all", return_value=[target_user]),
        ):
            url = reverse("admin:auth_ipauser_changelist")
            resp = self.client.post(
                url,
                data={
                    "action": "delete_selected",
                    "_selected_action": ["bob"],
                    "select_across": "1",
                    "index": "0",
                },
                follow=False,
            )

        # Before the fix, this endpoint 500s with:
        # AttributeError: '_ListBackedQuerySet' object has no attribute 'verbose_name'
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Are you sure", status_code=200)
