from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from core.backends import FreeIPAUser


class GroupSponsorNestedGroupsDisplayTests(TestCase):
    def _login_as_freeipa(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_group_detail_shows_sponsor_groups_first_sorted_then_users(self) -> None:
        self._login_as_freeipa("admin")

        group = SimpleNamespace(
            cn="parent",
            description="",
            fas_group=True,
            members=[],
            sponsors=["bob"],
            sponsor_groups=["child", "alpha"],
            member_groups=[],
            fas_url=None,
            fas_mailing_list=None,
            fas_irc_channels=[],
            fas_discussion_url=None,
        )
        alpha = SimpleNamespace(
            cn="alpha",
            description="Alpha sponsor group description",
            fas_group=True,
            members=["alice"],
            sponsors=[],
            sponsor_groups=[],
            member_groups=[],
        )
        child = SimpleNamespace(
            cn="child",
            description="Child sponsor group",
            fas_group=True,
            members=["carol"],
            sponsors=[],
            sponsor_groups=[],
            member_groups=[],
        )

        def _fake_group_get(cn: str):
            return {"parent": group, "alpha": alpha, "child": child}.get(cn)

        def _fake_user_get(username: str) -> FreeIPAUser:
            return FreeIPAUser(
                username,
                {
                    "uid": [username],
                    "givenname": [username.title()],
                    "sn": ["User"],
                    "mail": [f"{username}@example.com"],
                    "memberof_group": [],
                },
            )

        with (
            patch("core.backends.FreeIPAGroup.get", side_effect=_fake_group_get),
            patch("core.templatetags.core_user_widget.FreeIPAUser.get", side_effect=_fake_user_get),
        ):
            resp = self.client.get("/group/parent/")

        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        idx_alpha = html.find('href="/group/alpha/"')
        idx_child = html.find('href="/group/child/"')
        idx_bob = html.find('href="/user/bob/"')

        self.assertGreaterEqual(idx_alpha, 0)
        self.assertGreaterEqual(idx_child, 0)
        self.assertGreaterEqual(idx_bob, 0)

        self.assertLess(idx_alpha, idx_child)
        self.assertLess(idx_child, idx_bob)

    def test_group_detail_hides_sponsors_section_when_empty(self) -> None:
        self._login_as_freeipa("admin")

        group = SimpleNamespace(
            cn="parent",
            description="",
            fas_group=True,
            members=[],
            sponsors=[],
            sponsor_groups=[],
            member_groups=[],
            fas_url=None,
            fas_mailing_list=None,
            fas_irc_channels=[],
            fas_discussion_url=None,
        )

        with patch("core.backends.FreeIPAGroup.get", return_value=group):
            resp = self.client.get("/group/parent/")

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Sponsors")
