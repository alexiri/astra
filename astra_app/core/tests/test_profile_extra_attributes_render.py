from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from core import views_selfservice


class ProfileExtraAttributesRenderTests(TestCase):
    def _add_session_and_messages(self, request: Any) -> Any:
        def get_response(_: Any) -> HttpResponse:
            return HttpResponse()

        SessionMiddleware(get_response).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_profile_renders_configured_extra_attributes(self) -> None:
        factory = RequestFactory()
        request = factory.get("/")
        self._add_session_and_messages(request)

        setattr(
            request,
            "user",
            cast(
                Any,
                SimpleNamespace(
                    is_authenticated=True,
                    get_username=lambda: "alice",
                    username="alice",
                    email="a@example.org",
                ),
            ),
        )

        fake_user = SimpleNamespace(
            username="alice",
            email="a@example.org",
            is_authenticated=True,
            get_full_name=lambda: "Alice User",
            groups_list=[],
            _user_data={
                "mail": ["a@example.org"],
                "fasTimezone": ["Europe/Paris"],
                "fasLocale": ["en_US"],
                "fasIRCNick": ["alice_irc", "matrix://example.org/alice", "irc://irc.example.org/bob", "alice_irc2"],
                "fasWebsiteUrl": ["https://example.com/blog"],
                "fasRssUrl": ["https://example.com/rss"],
                "fasRHBZEmail": ["alice@rhbz.example"],
                "fasGitHubUsername": ["alicegh"],
                "fasGitLabUsername": ["alicegl"],
                "fasGPGKeyId": ["0123456789ABCDEF"],
                "ipasshpubkey": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE... alice@laptop"],
            },
        )

        with patch("core.views_selfservice.FreeIPAUser.get", autospec=True, return_value=fake_user):
            response = views_selfservice.user_profile(request, "alice")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # Ensure common attributes render when present.
        self.assertIn("en_US", content)
        self.assertIn("alice_irc", content)
        self.assertIn("alice_irc2", content)
        self.assertIn("bob:irc.example.org", content)
        self.assertIn("https://matrix.to/#/@alice:example.org", content)
        self.assertIn("https://example.com/blog", content)
        self.assertIn("https://example.com/rss", content)
        self.assertIn("alice@rhbz.example", content)
        self.assertIn("https://github.com/alicegh", content)
        self.assertIn("https://gitlab.com/alicegl", content)
        self.assertIn("0123456789ABCDEF", content)
        self.assertIn("ssh-ed25519", content)
