from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase
from python_freeipa import exceptions

from core.backends import FreeIPAFASAgreement


class FreeIPAFASAgreementDeleteUnlinksTests(SimpleTestCase):
    def test_delete_unlinks_groups_and_users_then_retries(self):
        agreement = FreeIPAFASAgreement(
            "test_agreement",
            {
                "cn": ["test_agreement"],
                "member_group": ["g1"],
                "memberuser_user": ["u1"],
            },
        )

        calls: list[str] = []

        def rpc(_client, method: str, args, params):
            calls.append(method)
            if method == "fasagreement_del" and calls.count("fasagreement_del") == 1:
                raise exceptions.Denied(
                    "Insufficient access: Not allowed to delete User Agreement with linked groups",
                    0,
                )
            if method == "fasagreement_remove_group":
                return {"failed": {"member": {"group": []}}}
            if method == "fasagreement_remove_user":
                return {"failed": {"memberuser": {"user": []}}}
            return {}

        def retry(_get_client, fn):
            return fn(object())

        with (
            patch("core.backends._with_freeipa_service_client_retry", side_effect=retry),
            patch.object(FreeIPAFASAgreement, "_rpc", side_effect=rpc),
            patch.object(FreeIPAFASAgreement, "get", return_value=agreement),
        ):
            agreement.delete()

        self.assertEqual(
            calls,
            [
                "fasagreement_del",
                "fasagreement_remove_group",
                "fasagreement_remove_user",
                "fasagreement_del",
            ],
        )
