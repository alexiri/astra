from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from core import views_selfservice


class ProfileTimezoneDisplayTests(TestCase):
    def _add_session_and_messages(self, request: Any) -> Any:
        def get_response(_: Any) -> HttpResponse:
            return HttpResponse()

        SessionMiddleware(get_response).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_profile_prefers_freeipa_fasTimezone_for_display(self):
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
            },
        )

        with patch("core.views_selfservice.FreeIPAUser.get", autospec=True, return_value=fake_user):
            response = views_selfservice.profile(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Europe/Paris", content)
        self.assertIn("id=\"user-time\"", content)
        self.assertIn("data-timezone=\"Europe/Paris\"", content)
