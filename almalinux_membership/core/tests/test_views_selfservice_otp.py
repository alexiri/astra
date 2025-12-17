from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from core.views_selfservice import settings_otp


class SettingsOTPViewTests(TestCase):
    def _add_session_and_messages(self, request):
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def _auth_user(self, username: str = "alice"):
        return SimpleNamespace(is_authenticated=True, get_username=lambda: username)

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
        FREEIPA_SERVICE_USER="svc",
        FREEIPA_SERVICE_PASSWORD="pw",
    )
    def test_get_without_otptoken_api_renders_empty(self):
        factory = RequestFactory()
        request = factory.get("/settings/otp/")
        self._add_session_and_messages(request)
        request.user = self._auth_user()

        captured = {}

        def fake_render(req, template, context):
            captured["context"] = context
            return HttpResponse("ok")

        with patch("core.views_selfservice.render", side_effect=fake_render, autospec=True):
            with patch("core.views_selfservice.ClientMeta", autospec=True) as mocked_client_cls:
                mocked_client = mocked_client_cls.return_value
                mocked_client.login.return_value = None
                # No otptoken_find attribute -> no tokens.
                if hasattr(mocked_client, "otptoken_find"):
                    delattr(mocked_client, "otptoken_find")

                response = settings_otp(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["context"]["tokens"], [])

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
        FREEIPA_SERVICE_USER="svc",
        FREEIPA_SERVICE_PASSWORD="pw",
    )
    def test_get_with_otptoken_find_populates_tokens(self):
        factory = RequestFactory()
        request = factory.get("/settings/otp/")
        self._add_session_and_messages(request)
        request.user = self._auth_user()

        captured = {}

        def fake_render(req, template, context):
            captured["context"] = context
            return HttpResponse("ok")

        with patch("core.views_selfservice.render", side_effect=fake_render, autospec=True):
            with patch("core.views_selfservice.ClientMeta", autospec=True) as mocked_client_cls:
                mocked_client = mocked_client_cls.return_value
                mocked_client.login.return_value = None
                mocked_client.otptoken_find.return_value = {"result": [{"ipatokenuniqueid": ["t1"]}]}

                response = settings_otp(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured["context"]["tokens"]), 1)

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
        FREEIPA_SERVICE_USER="svc",
        FREEIPA_SERVICE_PASSWORD="pw",
    )
    def test_post_without_otptoken_add_shows_error(self):
        factory = RequestFactory()
        request = factory.post("/settings/otp/", data={"description": "My token"})
        self._add_session_and_messages(request)
        request.user = self._auth_user()

        captured = {}

        def fake_render(req, template, context):
            captured["context"] = context
            return HttpResponse("ok")

        with patch("core.views_selfservice.render", side_effect=fake_render, autospec=True):
            with patch("core.views_selfservice.ClientMeta", autospec=True) as mocked_client_cls:
                mocked_client = mocked_client_cls.return_value
                mocked_client.login.return_value = None
                # otptoken_add missing triggers capability-mismatch messaging.
                if hasattr(mocked_client, "otptoken_add"):
                    delattr(mocked_client, "otptoken_add")

                response = settings_otp(request)

        self.assertEqual(response.status_code, 200)
        msgs = [m.message for m in get_messages(request)]
        self.assertTrue(any("OTP token creation is not available" in m for m in msgs))

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
        FREEIPA_SERVICE_USER="svc",
        FREEIPA_SERVICE_PASSWORD="pw",
    )
    def test_post_with_otptoken_add_shows_success(self):
        factory = RequestFactory()
        request = factory.post("/settings/otp/", data={"description": "My token"})
        self._add_session_and_messages(request)
        request.user = self._auth_user()

        captured = {}

        def fake_render(req, template, context):
            captured["context"] = context
            return HttpResponse("ok")

        with patch("core.views_selfservice.render", side_effect=fake_render, autospec=True):
            with patch("core.views_selfservice.ClientMeta", autospec=True) as mocked_client_cls:
                mocked_client = mocked_client_cls.return_value
                mocked_client.login.return_value = None
                mocked_client.otptoken_add.return_value = {"result": {"ipatokenuniqueid": ["t1"]}}

                response = settings_otp(request)

        self.assertEqual(response.status_code, 200)
        msgs = [m.message for m in get_messages(request)]
        self.assertTrue(any("OTP token created" in m for m in msgs))
