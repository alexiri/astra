from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core import views_selfservice


class SelfServiceSettingsPagesTests(TestCase):
    def _add_session_and_messages(self, request):
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def _auth_user(self, username: str = "alice"):
        return SimpleNamespace(is_authenticated=True, get_username=lambda: username)

    def test_settings_profile_get_accepts_boolean_fasisprivate(self):
        factory = RequestFactory()

        fake_user = SimpleNamespace(
            username="alice",
            first_name="Alice",
            last_name="User",
            email="a@example.org",
            is_authenticated=True,
            _user_data={
                "givenname": ["Alice"],
                "sn": ["User"],
                "cn": ["Alice User"],
                # Reproduces the real-world crash: value comes back as a bool.
                "fasIsPrivate": [True],
            },
        )

        request = factory.get("/settings/profile/")
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        captured: dict[str, object] = {}

        def fake_render(_request, template, context):
            captured["template"] = template
            captured["context"] = context
            return HttpResponse("ok")

        with patch("core.views_selfservice._get_full_user", autospec=True, return_value=fake_user):
            with patch("core.views_selfservice.render", autospec=True, side_effect=fake_render):
                response = views_selfservice.settings_profile(request)

        self.assertEqual(response.status_code, 200)
        ctx = captured.get("context")
        self.assertIsNotNone(ctx)
        form = ctx["form"]
        self.assertTrue(form.initial.get("fasIsPrivate"))

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
        FREEIPA_SERVICE_USER="svc",
        FREEIPA_SERVICE_PASSWORD="pw",
    )
    def test_settings_profile_post_no_changes_short_circuits(self):
        factory = RequestFactory()

        fake_user = SimpleNamespace(
            username="alice",
            first_name="Alice",
            last_name="User",
            email="a@example.org",
            is_authenticated=True,
            _user_data={
                "givenname": ["Alice"],
                "sn": ["User"],
                "cn": ["Alice User"],
                "fasLocale": ["en_US"],
                "fasTimezone": ["UTC"],
                "fasIsPrivate": ["FALSE"],
            },
        )

        request = factory.post(
            "/settings/profile/",
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasPronoun": "",
                "fasLocale": "en_US",
                "fasTimezone": "UTC",
                "fasWebsiteUrl": "",
                "fasRssUrl": "",
                "fasIRCNick": "",
                "fasGitHubUsername": "",
                "fasGitLabUsername": "",
                "fasIsPrivate": "",  # unchecked
            },
        )
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        with patch("core.views_selfservice.FreeIPAUser.get", autospec=True) as mocked_get:
            mocked_get.return_value = fake_user
            with patch("core.views_selfservice._update_user_attrs", autospec=True) as mocked_update:
                response = views_selfservice.settings_profile(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("settings-profile"))
        msgs = [m.message for m in get_messages(request)]
        self.assertIn("No changes to save.", msgs)
        mocked_update.assert_not_called()

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
        FREEIPA_SERVICE_USER="svc",
        FREEIPA_SERVICE_PASSWORD="pw",
    )
    def test_settings_emails_post_no_changes_short_circuits(self):
        factory = RequestFactory()

        fake_user = SimpleNamespace(
            username="alice",
            email="a@example.org",
            is_authenticated=True,
            _user_data={"mail": ["a@example.org"], "fasRHBZEmail": ["a@example.org"]},
        )

        request = factory.post(
            "/settings/emails/",
            data={
                "mail": "a@example.org",
                "fasRHBZEmail": "a@example.org",
            },
        )
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        with patch("core.views_selfservice.FreeIPAUser.get", autospec=True) as mocked_get:
            mocked_get.return_value = fake_user
            with patch("core.views_selfservice._update_user_attrs", autospec=True) as mocked_update:
                response = views_selfservice.settings_emails(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("settings-emails"))
        msgs = [m.message for m in get_messages(request)]
        self.assertIn("No changes to save.", msgs)
        mocked_update.assert_not_called()

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
        FREEIPA_SERVICE_USER="svc",
        FREEIPA_SERVICE_PASSWORD="pw",
    )
    def test_settings_keys_post_no_changes_short_circuits(self):
        factory = RequestFactory()

        fake_user = SimpleNamespace(
            username="alice",
            is_authenticated=True,
            _user_data={
                "fasGPGKeyId": ["0123456789ABCDEF"],
                "ipasshpubkey": ["ssh-ed25519 AAAA... alice@example"],
            },
        )

        request = factory.post(
            "/settings/keys/",
            data={
                "fasGPGKeyId": "0123456789ABCDEF",
                "ipasshpubkey": "ssh-ed25519 AAAA... alice@example",
            },
        )
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        with patch("core.views_selfservice.FreeIPAUser.get", autospec=True) as mocked_get:
            mocked_get.return_value = fake_user
            with patch("core.views_selfservice._update_user_attrs", autospec=True) as mocked_update:
                response = views_selfservice.settings_keys(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("settings-keys"))
        msgs = [m.message for m in get_messages(request)]
        self.assertIn("No changes to save.", msgs)
        mocked_update.assert_not_called()

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
    )
    def test_settings_password_uses_passwd_when_available(self):
        factory = RequestFactory()
        request = factory.post(
            "/settings/password/",
            data={
                "current_password": "oldpw",
                "new_password": "newpw",
                "confirm_new_password": "newpw",
            },
        )
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        with patch("core.views_selfservice.ClientMeta", autospec=True) as mocked_client_cls:
            mocked_client = mocked_client_cls.return_value
            mocked_client.login.return_value = None
            mocked_client.passwd.return_value = None

            response = views_selfservice.settings_password(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("settings-password"))
        mocked_client.login.assert_called_once_with("alice", "oldpw")
        mocked_client.passwd.assert_called_once_with("alice", "oldpw", "newpw")

    @override_settings(
        FREEIPA_HOST="ipa.test",
        FREEIPA_VERIFY_SSL=False,
    )
    def test_settings_password_falls_back_to_user_mod_when_no_passwd(self):
        factory = RequestFactory()
        request = factory.post(
            "/settings/password/",
            data={
                "current_password": "oldpw",
                "new_password": "newpw",
                "confirm_new_password": "newpw",
            },
        )
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        with patch("core.views_selfservice.ClientMeta", autospec=True) as mocked_client_cls:
            mocked_client = mocked_client_cls.return_value
            mocked_client.login.return_value = None
            # Simulate no passwd attribute in this client version.
            if hasattr(mocked_client, "passwd"):
                delattr(mocked_client, "passwd")
            mocked_client.user_mod.return_value = None

            response = views_selfservice.settings_password(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("settings-password"))
        mocked_client.login.assert_called_once_with("alice", "oldpw")
        mocked_client.user_mod.assert_called_once_with("alice", o_userpassword="newpw")
