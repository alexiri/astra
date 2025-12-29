from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from core.backends import FreeIPAUser


class FreeIPAUserSetStatusNoteFallbackTests(TestCase):
    def test_uses_setattr_for_custom_attribute(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

            def user_mod(self, *args: object, **kwargs: object) -> object:
                self.calls.append((args, kwargs))
                return {"result": "ok"}

        fake_client = FakeClient()

        def _no_retry(get_client, fn):
            return fn(fake_client)

        with (
            patch("core.backends._with_freeipa_service_client_retry", _no_retry),
            patch("core.backends._invalidate_user_cache"),
            patch("core.backends._invalidate_users_list_cache"),
            patch("core.backends.FreeIPAUser.get", return_value=None),
        ):
            FreeIPAUser.set_status_note("alice", "Hello")

        self.assertEqual(len(fake_client.calls), 1)
        _, last_kwargs = fake_client.calls[0]
        self.assertIn("o_setattr", last_kwargs)
        self.assertEqual(last_kwargs["o_setattr"], ["fasstatusnote=Hello"])
        self.assertNotIn("o_fasstatusnote", last_kwargs)

    def test_clears_note_prefers_setattr_empty_value(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

            def user_mod(self, *args: object, **kwargs: object) -> object:
                self.calls.append((args, kwargs))
                return {"result": "ok"}

        fake_client = FakeClient()

        def _no_retry(get_client, fn):
            return fn(fake_client)

        with (
            patch("core.backends._with_freeipa_service_client_retry", _no_retry),
            patch("core.backends._invalidate_user_cache"),
            patch("core.backends._invalidate_users_list_cache"),
            patch("core.backends.FreeIPAUser.get", return_value=None),
        ):
            FreeIPAUser.set_status_note("alice", "")

        self.assertEqual(len(fake_client.calls), 1)
        _, last_kwargs = fake_client.calls[0]
        self.assertIn("o_setattr", last_kwargs)
        self.assertEqual(last_kwargs["o_setattr"], ["fasstatusnote="])

    def test_clear_note_falls_back_to_delattr_when_setattr_rejected(self) -> None:
        from python_freeipa import exceptions

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

            def user_mod(self, *args: object, **kwargs: object) -> object:
                self.calls.append((args, kwargs))
                if kwargs.get("o_setattr") == ["fasstatusnote="]:
                    raise exceptions.BadRequest("an internal error has occurred", 400)
                return {"result": "ok"}

        fake_client = FakeClient()

        def _no_retry(get_client, fn):
            return fn(fake_client)

        with (
            patch("core.backends._with_freeipa_service_client_retry", _no_retry),
            patch("core.backends._invalidate_user_cache"),
            patch("core.backends._invalidate_users_list_cache"),
            patch("core.backends.FreeIPAUser.get", return_value=None),
        ):
            FreeIPAUser.set_status_note("alice", "")

        self.assertGreaterEqual(len(fake_client.calls), 2)
        _, first_kwargs = fake_client.calls[0]
        _, second_kwargs = fake_client.calls[1]
        self.assertEqual(first_kwargs.get("o_setattr"), ["fasstatusnote="])
        self.assertEqual(second_kwargs.get("o_delattr"), ["fasstatusnote="])
