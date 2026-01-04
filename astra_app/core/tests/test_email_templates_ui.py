from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.backends import FreeIPAUser
from core.models import FreeIPAPermissionGrant
from core.permissions import ASTRA_ADD_MAILMERGE


class EmailTemplatesUiTests(TestCase):
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def setUp(self) -> None:
        super().setUp()
        FreeIPAPermissionGrant.objects.get_or_create(
            permission=ASTRA_ADD_MAILMERGE,
            principal_type=FreeIPAPermissionGrant.PrincipalType.group,
            principal_name="membership-committee",
        )

    def test_requires_permission(self) -> None:
        self._login_as_freeipa_user("alice")
        alice = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": []})

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp = self.client.get(reverse("email-templates"))

        self.assertEqual(resp.status_code, 302)

    def test_list_shows_templates(self) -> None:
        from post_office.models import EmailTemplate

        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        EmailTemplate.objects.create(
            name="t-1",
            description="First",
            subject="Subj",
            content="Text",
            html_content="<p>Hi</p>",
        )

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp = self.client.get(reverse("email-templates"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Templates")
        self.assertContains(resp, "t-1")
        self.assertContains(resp, "First")

    def test_create_edit_delete_template(self) -> None:
        from post_office.models import EmailTemplate

        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            create_resp = self.client.post(
                reverse("email-template-create"),
                data={
                    "name": "created-1",
                    "description": "Created",
                    "subject": "Hello",
                    "html_content": "<p>Hello</p>",
                    "text_content": "Hello",
                },
                follow=True,
            )

        self.assertEqual(create_resp.status_code, 200)
        tpl = EmailTemplate.objects.get(name="created-1")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            edit_resp = self.client.post(
                reverse("email-template-edit", kwargs={"template_id": tpl.pk}),
                data={
                    "name": "created-1",
                    "description": "Updated",
                    "subject": "Updated subj",
                    "html_content": "<p>Updated</p>",
                    "text_content": "Updated",
                },
                follow=True,
            )

        self.assertEqual(edit_resp.status_code, 200)
        tpl.refresh_from_db()
        self.assertEqual(tpl.description, "Updated")
        self.assertEqual(tpl.subject, "Updated subj")
        self.assertEqual(tpl.content, "Updated")
        self.assertEqual(tpl.html_content, "<p>Updated</p>")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            delete_resp = self.client.post(
                reverse("email-template-delete", kwargs={"template_id": tpl.pk}),
                follow=True,
            )

        self.assertEqual(delete_resp.status_code, 200)
        self.assertFalse(EmailTemplate.objects.filter(pk=tpl.pk).exists())

    def test_template_render_preview_endpoint(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp = self.client.post(
                reverse("email-template-render-preview"),
                data={
                    "subject": "Hi {{ name }}",
                    "html_content": "<p>{{ name }}</p>",
                    "text_content": "{{ name }}",
                },
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["subject"], "Hi -name-")
        self.assertEqual(payload["html"], "<p>-name-</p>")
        self.assertEqual(payload["text"], "-name-")
