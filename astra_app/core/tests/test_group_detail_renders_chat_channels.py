from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase


class GroupDetailRendersChatChannelsTests(TestCase):
    def _login_as_freeipa(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_group_detail_renders_chat_channels_links(self) -> None:
        self._login_as_freeipa("admin")

        group = SimpleNamespace(
            cn="fas1",
            description="FAS Group 1",
            fas_group=True,
            members=[],
            sponsors=[],
            sponsor_groups=[],
            member_groups=[],
            fas_url=None,
            fas_mailing_list=None,
            fas_discussion_url=None,
            fas_irc_channels=[
                "irc:/#dev",
                "matrix://matrix.org/#almalinux",
                "mattermost://chat.almalinux.org/almalinux/channels/general",
            ],
        )

        with patch("core.backends.FreeIPAGroup.get", return_value=group):
            resp = self.client.get("/group/fas1/")

        self.assertEqual(resp.status_code, 200)

        self.assertContains(resp, 'href="ircs://irc.libera.chat/#dev"')
        self.assertContains(resp, ">#dev</a>")

        self.assertContains(resp, 'href="https://matrix.to/#/#almalinux:matrix.org')
        self.assertContains(resp, ">#almalinux</a>")

        self.assertContains(resp, 'href="mattermost://chat.almalinux.org/almalinux/channels/general"')
        self.assertContains(resp, ">~general</a>")
