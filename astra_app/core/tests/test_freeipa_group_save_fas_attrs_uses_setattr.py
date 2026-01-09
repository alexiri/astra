from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase
from python_freeipa import exceptions

from core.backends import FreeIPAGroup


class FreeIPAGroupSaveFASAttrsTests(SimpleTestCase):
    def test_save_does_not_use_unknown_fas_option_kwargs(self) -> None:
        group = FreeIPAGroup(
            "fas1",
            {
                "cn": ["fas1"],
                "fasurl": ["https://old.example.org"],
                "fasmailinglist": ["old@example.org"],
                "fasdiscussionurl": ["https://discussion.example.org/c/old"],
                "fasircchannel": ["#old"],
                "description": ["Old desc"],
                "objectclass": ["fasGroup"],
            },
        )

        group.fas_url = "https://new.example.org"
        group.fas_mailing_list = "new@example.org"
        group.fas_discussion_url = "https://discussion.example.org/c/new"
        group.fas_irc_channels = ["#new", "#new-dev"]
        group.description = "New desc"

        class _FakeClient:
            def group_mod(self, cn: str, **kwargs):
                # The python_freeipa wrapper doesn't know FAS extension options, so
                # passing them as explicit keyword arguments raises UnknownOption.
                for k in kwargs:
                    if k.startswith("o_fas"):
                        raise exceptions.UnknownOption(f"Unknown option: {k}")
                return {"result": {}}

        fake_client = _FakeClient()

        with (
            patch(
                "core.backends._with_freeipa_service_client_retry",
                side_effect=lambda _get_client, fn: fn(fake_client),
            ),
            patch("core.backends._invalidate_group_cache"),
            patch("core.backends._invalidate_groups_list_cache"),
            patch("core.backends.FreeIPAGroup.get", return_value=group),
        ):
            # Should not raise UnknownOption.
            group.save()
