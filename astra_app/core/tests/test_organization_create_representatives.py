from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.backends import FreeIPAUser
from core.models import FreeIPAPermissionGrant, Organization
from core.permissions import ASTRA_ADD_MEMBERSHIP, ASTRA_CHANGE_MEMBERSHIP


class OrganizationCreateRepresentativesTests(TestCase):
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def _valid_create_payload(self, *, name: str) -> dict[str, str]:
        return {
            "name": name,
            "business_contact_name": "Biz",
            "business_contact_email": "biz@example.com",
            "business_contact_phone": "",
            "pr_marketing_contact_name": "PR",
            "pr_marketing_contact_email": "pr@example.com",
            "pr_marketing_contact_phone": "",
            "technical_contact_name": "Tech",
            "technical_contact_email": "tech@example.com",
            "technical_contact_phone": "",
            "website_logo": "https://example.com/logo",
            "website": "https://example.com/",
            "additional_information": "",
        }

    def test_create_defaults_representative_to_creator(self) -> None:
        self._login_as_freeipa_user("alice")

        def get_user(username: str):
            return FreeIPAUser(username, {"uid": [username], "memberof_group": []})

        with patch("core.backends.FreeIPAUser.get", side_effect=get_user):
            resp = self.client.get(reverse("organization-create"))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Only create an organization")
            self.assertNotContains(resp, 'name="representatives"')

            payload = self._valid_create_payload(name="AliceCo")
            payload["representatives"] = ["bob"]
            resp = self.client.post(reverse("organization-create"), data=payload)
            self.assertEqual(resp.status_code, 302)

        created = Organization.objects.get(name="AliceCo")
        self.assertEqual(created.representatives, ["alice"])

    def test_create_allows_representatives_selection_for_membership_admins(self) -> None:
        FreeIPAPermissionGrant.objects.create(
            permission=ASTRA_ADD_MEMBERSHIP,
            principal_type=FreeIPAPermissionGrant.PrincipalType.user,
            principal_name="reviewer",
        )

        self._login_as_freeipa_user("reviewer")

        def get_user(username: str):
            return FreeIPAUser(username, {"uid": [username], "memberof_group": []})

        with patch("core.backends.FreeIPAUser.get", side_effect=get_user):
            resp = self.client.get(reverse("organization-create"))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Only create an organization")
            self.assertContains(resp, 'name="representatives"')
            # User-facing pages should load Select2 assets so the reps picker works and
            # matches the admin UI styling.
            self.assertContains(resp, "select2.full")
            self.assertContains(resp, "select2.css")

            payload = self._valid_create_payload(name="ReviewCo")
            payload["representatives"] = ["bob", "carol"]
            resp = self.client.post(reverse("organization-create"), data=payload)
            self.assertEqual(resp.status_code, 302)

        created = Organization.objects.get(name="ReviewCo")
        self.assertEqual(created.representatives, ["bob", "carol", "reviewer"])

    def test_representatives_search_requires_membership_add_or_change_permission(self) -> None:
        url = reverse("organization-representatives-search")

        self._login_as_freeipa_user("alice")

        def get_user(username: str):
            return FreeIPAUser(username, {"uid": [username], "memberof_group": []})

        with patch("core.backends.FreeIPAUser.get", side_effect=get_user):
            resp = self.client.get(url, {"q": "bo"})
            self.assertEqual(resp.status_code, 302)

        FreeIPAPermissionGrant.objects.create(
            permission=ASTRA_CHANGE_MEMBERSHIP,
            principal_type=FreeIPAPermissionGrant.PrincipalType.user,
            principal_name="reviewer",
        )
        self._login_as_freeipa_user("reviewer")

        bob = FreeIPAUser("bob", {"uid": ["bob"], "memberof_group": []})
        bobby = FreeIPAUser("bobby", {"uid": ["bobby"], "memberof_group": []})

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=get_user),
            patch("core.backends.FreeIPAUser.all", return_value=[bobby, bob]),
        ):
            resp = self.client.get(url, {"q": "bo"})
            self.assertEqual(resp.status_code, 200)
            self.assertIn("results", resp.json())
            ids = [r.get("id") for r in resp.json().get("results")]
            self.assertEqual(ids, ["bob", "bobby"])
