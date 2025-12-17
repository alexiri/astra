from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from core.backends import FreeIPAAuthBackend


class FreeIPABackendBehaviorTests(TestCase):
    def _add_session(self, request):
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_authenticate_persists_freeipa_username_in_session(self):
        factory = RequestFactory()
        request = factory.post("/login/")
        self._add_session(request)

        backend = FreeIPAAuthBackend()

        with patch("core.backends.ClientMeta", autospec=True) as mocked_client_cls:
            mocked_client = mocked_client_cls.return_value
            mocked_client.login.return_value = None

            with patch("core.backends.FreeIPAUser._fetch_full_user", autospec=True) as mocked_fetch:
                mocked_fetch.return_value = {"uid": ["alice"], "givenname": ["Alice"], "sn": ["User"]}

                user = backend.authenticate(request, username="alice", password="pw")

        self.assertIsNotNone(user)
        self.assertEqual(request.session.get("_freeipa_username"), "alice")

    def test_authenticate_no_longer_writes_session_uid_cache_mapping(self):
        factory = RequestFactory()
        request = factory.post("/login/")
        self._add_session(request)

        backend = FreeIPAAuthBackend()

        with patch("core.backends.cache.set", autospec=True) as mocked_cache_set:
            with patch("core.backends.ClientMeta", autospec=True) as mocked_client_cls:
                mocked_client = mocked_client_cls.return_value
                mocked_client.login.return_value = None

                with patch("core.backends.FreeIPAUser._fetch_full_user", autospec=True) as mocked_fetch:
                    mocked_fetch.return_value = {"uid": ["alice"]}
                    backend.authenticate(request, username="alice", password="pw")

        # cache.set may be used elsewhere in this backend; assert it never wrote the old mapping key.
        for call in mocked_cache_set.call_args_list:
            key = call.args[0] if call.args else None
            if isinstance(key, str):
                self.assertFalse(key.startswith("freeipa_session_uid_"))

    def test_get_user_is_intentionally_disabled(self):
        backend = FreeIPAAuthBackend()
        self.assertIsNone(backend.get_user(123))
        self.assertIsNone(backend.get_user("123"))
