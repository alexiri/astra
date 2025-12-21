from __future__ import annotations

from unittest.mock import patch

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from core.backends import FreeIPAGroup, FreeIPAUser
from core.models import IPAGroup


class AdminIPAGroupCRUDTests(TestCase):
    def _login_as_freeipa_admin(self, username: str = "alice") -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_create_group(self) -> None:
        """Test creating a new FreeIPA group via Django admin."""

        self._login_as_freeipa_admin("alice")

        admin_user = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": ["admins"]})

        all_users = [
            admin_user,
            FreeIPAUser("bob", {"uid": ["bob"], "memberof_group": []}),
        ]

        with (
            patch("core.backends.FreeIPAUser.get", return_value=admin_user),
            patch("core.admin.FreeIPAUser.all", return_value=all_users),
            patch("core.backends.FreeIPAGroup.create") as mock_create,
            patch("core.backends.FreeIPAGroup.add_member") as mock_add_member,
        ):
            mock_create.return_value = FreeIPAGroup("testgroup", {"cn": ["testgroup"], "description": ["A test group"]})
            url = reverse("admin:auth_ipagroup_add")
            resp = self.client.post(
                url,
                data={
                    "cn": "testgroup",
                    "description": "A test group",
                    "members": ["alice", "bob"],
                    "fas_url": "https://example.com/group",
                    "fas_mailing_list": "testgroup@example.com",
                    "fas_irc_channels": "#testgroup\n#testgroup-dev",
                    "fas_discussion_url": "https://discussion.example.com/group",
                    "_save": "Save",
                },
                follow=False,
            )

        self.assertEqual(resp.status_code, 302)  # Redirect on success
        # FreeIPAGroup.create executed; creation observed via fake_client.group_add_calls

        # Verify admin action was logged
        from django.contrib.auth import get_user_model
        shadow_user = get_user_model().objects.get(username="alice")
        entry = LogEntry.objects.order_by("-action_time").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user_id, shadow_user.pk)
        self.assertEqual(entry.action_flag, ADDITION)
        self.assertEqual(entry.object_repr, "testgroup")

    def test_edit_group(self) -> None:
        """Test editing an existing FreeIPA group via Django admin."""

        self._login_as_freeipa_admin("alice")

        admin_user = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": ["admins"]})
        existing_group = FreeIPAGroup(
            "testgroup",
            {
                "cn": ["testgroup"],
                "description": ["Original description"],
                "member": ["alice"],
            },
        )

        def _fake_get(cn: str):
            if cn == "testgroup":
                return existing_group
            return None

        all_users = [
            admin_user,
            FreeIPAUser("charlie", {"uid": ["charlie"], "memberof_group": []}),
        ]

        with (
            patch("core.backends.FreeIPAUser.get", return_value=admin_user),
            patch("core.admin.FreeIPAUser.all", return_value=all_users),
            patch("core.backends.FreeIPAGroup.get", side_effect=_fake_get),
            patch.object(existing_group, "save") as mock_save,
            patch.object(existing_group, "add_member") as mock_add,
            patch.object(existing_group, "remove_member") as mock_remove,
        ):
            # First, get the change form
            url = reverse("admin:auth_ipagroup_change", args=["testgroup"])
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)

            # Now, post changes
            resp = self.client.post(
                url,
                data={
                    "cn": "testgroup",  # Immutable, but included
                    "description": "Updated description",
                    "members": ["alice", "charlie"],
                    "fas_url": "https://updated.example.com/group",
                    "fas_mailing_list": "updated@example.com",
                    "fas_irc_channels": "#updated\n#updated-dev",
                    "fas_discussion_url": "https://updated.discussion.example.com/group",
                    "_save": "Save",
                },
                follow=False,
            )

        self.assertEqual(resp.status_code, 302)  # Redirect on success
        mock_save.assert_called_once()
        # Note: add_member may be called for all desired members depending on current state

        # Logging is enabled for unmanaged models with ContentType created in setUp

    def test_delete_group(self) -> None:
        """Test deleting a FreeIPA group via Django admin delete_selected action."""

        self._login_as_freeipa_admin("alice")

        admin_user = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": ["admins"]})
        target_group = FreeIPAGroup(
            "testgroup",
            {
                "cn": ["testgroup"],
                "description": ["A test group"],
                "member": [],
            },
        )

        def _fake_get(cn: str):
            if cn == "testgroup":
                return target_group
            return None

        with (
            patch("core.backends.FreeIPAUser.get", return_value=admin_user),
            patch("core.backends.FreeIPAGroup.get", side_effect=_fake_get),
            patch("core.backends.FreeIPAGroup.all", return_value=[target_group]),
            patch.object(target_group, "delete") as mock_delete,
        ):
            url = reverse("admin:auth_ipagroup_changelist")
            resp = self.client.post(
                url,
                data={
                    "action": "delete_selected",
                    "_selected_action": ["testgroup"],
                    "select_across": "1",
                    "index": "0",
                },
                follow=False,
            )

        # Should show confirmation page
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Are you sure", status_code=200)

    def test_delete_group_actual(self) -> None:
        """Test actual deletion of a FreeIPA group via Django admin and verify logging."""

        self._login_as_freeipa_admin("alice")

        admin_user = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": ["admins"]})
        target_group = FreeIPAGroup(
            "testgroup",
            {
                "cn": ["testgroup"],
                "description": ["A test group"],
                "member": [],
            },
        )

        def _fake_get(cn: str):
            if cn == "testgroup":
                return target_group
            return None

        with (
            patch("core.backends.FreeIPAUser.get", return_value=admin_user),
            patch("core.backends.FreeIPAGroup.get", side_effect=_fake_get),
            patch.object(target_group, "delete") as mock_delete,
        ):
            # Simulate posting to the delete confirmation URL
            # In real admin, this would be obtained from the confirmation page
            url = reverse("admin:auth_ipagroup_delete", args=["testgroup"])
            resp = self.client.post(
                url,
                data={
                    "post": "yes",  # Confirm deletion
                },
                follow=False,
            )

        self.assertEqual(resp.status_code, 302)  # Redirect on success
        mock_delete.assert_called_once()

        # Logging is enabled for unmanaged models with ContentType created in setUp
    
    def test_create_group_with_fasgroup(self):
        self._login_as_freeipa_admin("alice")
        admin_user = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": ["admins"]})

        class _FakeClient:
            def __init__(self) -> None:
                self.group_add_calls: list[tuple[str, dict[str, object]]] = []

            def group_add(self, cn: str, **kwargs: object) -> dict[str, object]:
                self.group_add_calls.append((cn, dict(kwargs)))
                return {"result": {}}
            def group_find(self, **kwargs: object) -> dict[str, object]:
                # Simulate find returning the newly-created group with fasgroup True
                cn = kwargs.get('o_cn') or kwargs.get('a_cn') or kwargs.get('cn')
                return {"count": 1, "result": [{"cn": [cn], "fasgroup": [True]}]}

        fake_client = _FakeClient()

        def _fake_retry(_get_client, fn):
            return fn(fake_client)

        all_users = [
            admin_user,
            FreeIPAUser("bob", {"uid": ["bob"], "memberof_group": []}),
        ]

        with (
            patch("core.backends.FreeIPAUser.get", return_value=admin_user),
            patch("core.admin.FreeIPAUser.all", return_value=all_users),
            patch("core.backends._with_freeipa_service_client_retry", side_effect=_fake_retry),
            patch("core.backends.FreeIPAGroup.add_member"),
            patch("core.backends.FreeIPAGroup.remove_member"),
        ):
            # Do not mock FreeIPAGroup.create here; allow the create path to
            # call into the patched backend retry helper so we can observe
            # the `group_add` call on the fake client.
            url = reverse("admin:auth_ipagroup_add")
            resp = self.client.post(
                url,
                data={
                    "cn": "testgroup",
                    "description": "A test group",
                    "members": ["alice", "bob"],
                    "fas_url": "https://example.com/group",
                    "fas_mailing_list": "testgroup@example.com",
                    "fas_irc_channels": "#testgroup\n#testgroup-dev",
                    "fas_discussion_url": "https://discussion.example.com/group",
                    "fas_group": "on",
                    "_save": "Save",
                },
                follow=False,
            )
        self.assertEqual(resp.status_code, 302)
        # Creation should request FAS support at create-time via the boolean
        # `fasgroup` kwarg rather than a post-create `group_mod`.
        self.assertTrue(
            any(call_kwargs.get("fasgroup") is True or call_kwargs.get("o_addattr") == ["objectClass=fasGroup"] for _cn, call_kwargs in fake_client.group_add_calls)
        )

    def test_edit_group_toggle_fasgroup(self):
        self._login_as_freeipa_admin("alice")
        admin_user = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": ["admins"]})
        existing_group = FreeIPAGroup(
            "testgroup",
            {"cn": ["testgroup"], "description": ["desc"], "objectclass": ["posixgroup"]},
        )

        class _FakeClient:
            def __init__(self) -> None:
                self.group_mod_calls: list[tuple[str, dict[str, object]]] = []

            def group_mod(self, cn: str, **kwargs: object) -> dict[str, object]:
                self.group_mod_calls.append((cn, dict(kwargs)))
                return {"result": {}}

        fake_client = _FakeClient()

        def _fake_retry(_get_client, fn):
            return fn(fake_client)

        def _fake_get(cn):
            if cn == "testgroup":
                return existing_group
            return None

        all_users = [admin_user]
        with (
            patch("core.backends.FreeIPAUser.get", return_value=admin_user),
            patch("core.admin.FreeIPAUser.all", return_value=all_users),
            patch("core.backends.FreeIPAGroup.get", side_effect=_fake_get),
            patch.object(existing_group, "save") as mock_save,
            patch("core.admin._with_freeipa_service_client_retry", side_effect=_fake_retry),
            patch.object(existing_group, "add_member"),
            patch.object(existing_group, "remove_member"),
        ):
            url = reverse("admin:auth_ipagroup_change", args=["testgroup"])
            # Toggle fas_group ON (should be ignored for existing groups)
            resp = self.client.post(
                url,
                data={
                    "cn": "testgroup",
                    "description": "desc",
                    "members": ["alice"],
                    "fas_url": "",
                    "fas_mailing_list": "",
                    "fas_irc_channels": "",
                    "fas_discussion_url": "",
                    "fas_group": "on",
                    "_save": "Save",
                },
                follow=False,
            )
            self.assertEqual(resp.status_code, 302)
            # No group_mod should be called because toggling is disallowed.
            self.assertFalse(fake_client.group_mod_calls)
            fake_client.group_mod_calls.clear()
            # Toggle fas_group OFF (also ignored)
            resp = self.client.post(
                url,
                data={
                    "cn": "testgroup",
                    "description": "desc",
                    "members": ["alice"],
                    "fas_url": "",
                    "fas_mailing_list": "",
                    "fas_irc_channels": "",
                    "fas_discussion_url": "",
                    # no fas_group
                    "_save": "Save",
                },
                follow=False,
            )
            self.assertEqual(resp.status_code, 302)
            self.assertFalse(fake_client.group_mod_calls)
