from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase


class GroupDetailInfoRowsHiddenTests(TestCase):
    def _login_as_freeipa(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_group_detail_hides_empty_info_rows(self) -> None:
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
        self.assertNotContains(resp, "Mailing list")
        self.assertNotContains(resp, "IRC channels")
        self.assertNotContains(resp, "Discussion URL")
        self.assertNotContains(resp, "URL")
