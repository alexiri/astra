from __future__ import annotations

import io
import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.backends import FreeIPAUser
from core.models import FreeIPAPermissionGrant
from core.permissions import ASTRA_ADD_MAILMERGE


class MailMergeTests(TestCase):
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
            resp = self.client.get(reverse("mail-merge"))

        self.assertEqual(resp.status_code, 302)

    def test_group_recipients_show_variables_and_count(self) -> None:
        self._login_as_freeipa_user("reviewer")

        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _FakeGroup:
            cn = "example-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return {"alice", "bob"}

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "givenname": ["Alice"],
                "sn": ["User"],
                "displayname": ["Alice User"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )
        bob = FreeIPAUser(
            "bob",
            {
                "uid": ["bob"],
                "givenname": ["Bob"],
                "sn": ["User"],
                "displayname": ["Bob User"],
                "mail": ["bob@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            if username == "bob":
                return bob
            return None

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAGroup.get", return_value=_FakeGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_FakeGroup()]),
        ):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "group",
                    "group_cn": "example-group",
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Mail Merge")
        self.assertContains(resp, "Recipients")
        self.assertContains(resp, "2")
        self.assertContains(resp, "{{ full_name }}")
        self.assertContains(resp, "Alice User")

    def test_csv_recipients_show_header_variables(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        csv_bytes = b"Email,Display Name,Company\nalice@example.com,Alice User,Acme\n"
        csv_file = io.BytesIO(csv_bytes)
        csv_file.name = "recipients.csv"

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "csv",
                    "csv_file": csv_file,
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "{{ email }}")
        self.assertContains(resp, "{{ display_name }}")
        self.assertContains(resp, "{{ company }}")
        self.assertContains(resp, "alice@example.com")

    def test_manual_recipients_show_variables_and_count(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        with (
            patch("core.backends.FreeIPAUser.get", return_value=reviewer),
            patch("core.backends.FreeIPAGroup.all", return_value=[]),
        ):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "manual",
                    "manual_to": "jim@example.com, bob@example.com",
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recipient count")
        self.assertContains(resp, "2")
        self.assertContains(resp, "{{ email }}")
        self.assertContains(resp, "jim@example.com")

    def test_get_prefills_group_recipients_from_query_params(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _FakeGroup:
            cn = "example-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return {"alice", "bob"}

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "givenname": ["Alice"],
                "sn": ["User"],
                "displayname": ["Alice User"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )
        bob = FreeIPAUser(
            "bob",
            {
                "uid": ["bob"],
                "givenname": ["Bob"],
                "sn": ["User"],
                "displayname": ["Bob User"],
                "mail": ["bob@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            if username == "bob":
                return bob
            return None

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAGroup.get", return_value=_FakeGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_FakeGroup()]),
        ):
            resp = self.client.get(reverse("mail-merge") + "?type=group&to=example-group")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="mailmerge-recipient-mode" value="group"')
        # Deep-link should auto-load recipients on GET.
        self.assertContains(resp, "Recipient count")
        self.assertContains(resp, "2")
        self.assertContains(resp, "{{ full_name }}")
        self.assertContains(resp, "alice@example.com")

    def test_empty_group_still_shows_placeholder_variable_examples(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _EmptyGroup:
            cn = "empty-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return set()

        with (
            patch("core.backends.FreeIPAUser.get", return_value=reviewer),
            patch("core.backends.FreeIPAGroup.get", return_value=_EmptyGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_EmptyGroup()]),
        ):
            resp = self.client.get(reverse("mail-merge") + "?type=group&to=empty-group")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recipient count")
        self.assertContains(resp, ">0<")

        # Even with no recipients, show useful example placeholders.
        self.assertContains(resp, "{{ username }}")
        self.assertContains(resp, "{{ first_name }}")
        self.assertContains(resp, "{{ last_name }}")
        self.assertContains(resp, "{{ email }}")
        self.assertContains(resp, "{{ full_name }}")
        self.assertContains(resp, "-username-")
        self.assertContains(resp, "-first_name-")
        self.assertContains(resp, "-last_name-")
        self.assertContains(resp, "-email-")
        self.assertContains(resp, "-full_name-")

    def test_get_prefills_manual_recipients_from_query_params(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        with (
            patch("core.backends.FreeIPAUser.get", return_value=reviewer),
            patch("core.backends.FreeIPAGroup.all", return_value=[]),
        ):
            resp = self.client.get(reverse("mail-merge") + "?type=manual&to=jim@example.com")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="mailmerge-recipient-mode" value="manual"')
        self.assertContains(resp, 'name="manual_to"')
        # Deep-link should auto-load recipients on GET.
        self.assertContains(resp, "Recipient count")
        self.assertContains(resp, "1")
        self.assertContains(resp, "{{ email }}")
        self.assertContains(resp, "jim@example.com")

    def test_get_extra_query_params_are_added_to_context(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        with (
            patch("core.backends.FreeIPAUser.get", return_value=reviewer),
            patch("core.backends.FreeIPAGroup.all", return_value=[]),
        ):
            resp = self.client.get(
                reverse("mail-merge") + "?type=manual&to=jim@example.com&foo=bar&project-name=Atomic+SIG"
            )

        self.assertEqual(resp.status_code, 200)
        # Extra params become template variables.
        self.assertContains(resp, "{{ foo }}")
        self.assertContains(resp, "bar")
        self.assertContains(resp, "{{ project_name }}")
        self.assertContains(resp, "Atomic SIG")

    def test_get_prefills_users_recipients_from_query_params(self) -> None:
        self._login_as_freeipa_user("reviewer")

        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "memberof_group": ["membership-committee"],
            },
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "givenname": ["Alice"],
                "sn": ["User"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )
        # Make Bob intentionally less complete so Alice wins the "best example" selection.
        bob = FreeIPAUser(
            "bob",
            {
                "uid": ["bob"],
                "sn": ["User"],
                "mail": ["bob@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            if username == "bob":
                return bob
            return None

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.all", return_value=[alice, bob]),
            patch("core.backends.FreeIPAGroup.all", return_value=[]),
        ):
            resp = self.client.get(reverse("mail-merge") + "?type=users&to=alice,bob")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="mailmerge-recipient-mode" value="users"')
        # Deep-link should auto-load recipients on GET.
        self.assertContains(resp, "Recipient count")
        self.assertContains(resp, "2")
        self.assertContains(resp, "{{ email }}")
        self.assertContains(resp, "alice@example.com")
        # Should preselect the users in the multi-select.
        self.assertContains(resp, '<option value="alice" selected>')
        self.assertContains(resp, '<option value="bob" selected>')

    def test_variable_examples_choose_best_context_and_placeholder_missing(self) -> None:
        self._login_as_freeipa_user("reviewer")

        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _FakeGroup:
            cn = "example-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return {"alice", "bob"}

        # Alice is first in sorted order but has fewer filled vars.
        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )
        # Bob is more complete but intentionally missing last_name to trigger placeholder.
        bob = FreeIPAUser(
            "bob",
            {
                "uid": ["bob"],
                "givenname": ["Bob"],
                "mail": ["bob@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            if username == "bob":
                return bob
            return None

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAGroup.get", return_value=_FakeGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_FakeGroup()]),
        ):
            resp = self.client.get(reverse("mail-merge") + "?type=group&to=example-group")

        self.assertEqual(resp.status_code, 200)
        # Examples should be taken from Bob (more fields filled) rather than Alice.
        self.assertContains(resp, "{{ first_name }}")
        self.assertContains(resp, "Bob")
        # Missing values in the chosen example context should use a placeholder.
        self.assertContains(resp, "{{ last_name }}")
        self.assertContains(resp, "-last_name-")

    def test_get_prefills_email_template_from_query_param(self) -> None:
        from post_office.models import EmailTemplate

        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        tpl = EmailTemplate.objects.create(
            name="mailmerge-prefill",
            subject="Hello {{ email }}",
            content="Text body for {{ email }}",
            html_content="<p>HTML body for {{ email }}</p>",
        )

        with (
            patch("core.backends.FreeIPAUser.get", return_value=reviewer),
            patch("core.backends.FreeIPAGroup.all", return_value=[]),
        ):
            resp = self.client.get(reverse("mail-merge") + "?type=manual&to=jim@example.com&template=mailmerge-prefill")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'<option value="{tpl.pk}" selected>')
        self.assertContains(resp, 'value="Hello {{ email }}"')
        self.assertContains(resp, "Text body for {{ email }}")
        # HTML bodies are shown in a textarea, so they appear HTML-escaped in the page source.
        self.assertContains(resp, "&lt;p&gt;HTML body for {{ email }}&lt;/p&gt;")

    def test_compose_shows_html_to_text_button_and_variables_card(self) -> None:
        self._login_as_freeipa_user("reviewer")

        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _FakeGroup:
            cn = "example-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return {"alice"}

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "givenname": ["Alice"],
                "sn": ["User"],
                "displayname": ["Alice User"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAGroup.get", return_value=_FakeGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_FakeGroup()]),
        ):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "group",
                    "group_cn": "example-group",
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Available variables")
        self.assertContains(resp, 'data-compose-action="copy-html-to-text"')

    def test_save_as_template_appears_and_is_selected(self) -> None:
        from post_office.models import EmailTemplate

        self._login_as_freeipa_user("reviewer")

        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _FakeGroup:
            cn = "example-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return {"alice"}

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "givenname": ["Alice"],
                "sn": ["User"],
                "displayname": ["Alice User"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        original = EmailTemplate.objects.create(
            name="Original MailMerge Template",
            subject="Original subject",
            content="Original text",
            html_content="<p>Original html</p>",
        )

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAGroup.get", return_value=_FakeGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_FakeGroup()]),
        ):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "group",
                    "group_cn": "example-group",
                    "email_template_id": str(original.pk),
                    "subject": "Hello {{ full_name }}",
                    "text_content": "Hi {{ full_name }}",
                    "html_content": "<p>Hi {{ full_name }}</p>",
                    "action": "save_as",
                    "save_as_name": "New MailMerge Template",
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        tpl = EmailTemplate.objects.get(name="New MailMerge Template")
        self.assertContains(resp, "New MailMerge Template")
        self.assertContains(resp, f'<option value="{tpl.pk}" selected>')
        self.assertNotContains(resp, f'<option value="{original.pk}" selected>')
        self.assertContains(resp, f'id="mailmerge-autoload-template-id" value="{tpl.pk}"')

    def test_send_emails_renders_per_recipient(self) -> None:
        from post_office.models import EmailTemplate

        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _FakeGroup:
            cn = "example-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return {"alice"}

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "givenname": ["Alice"],
                "sn": ["User"],
                "displayname": ["Alice User"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        EmailTemplate.objects.create(
            name="mailmerge-test",
            subject="Hello {{ first_name }}",
            content="Hi {{ full_name }}",
            html_content="<p>Hi {{ full_name }}</p>",
        )

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAGroup.get", return_value=_FakeGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_FakeGroup()]),
            patch("core.views_mailmerge.mail.send", autospec=True) as send,
        ):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "group",
                    "group_cn": "example-group",
                    "subject": "Hello {{ first_name }}",
                    "text_content": "Hi {{ full_name }}",
                    "html_content": "<p>Hi {{ full_name }}</p>",
                    "action": "send",
                    "cc": "cc1@example.com, cc2@example.com",
                    "bcc": "bcc1@example.com",
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        send.assert_called_once()
        _args, kwargs = send.call_args
        self.assertEqual(kwargs["recipients"], ["alice@example.com"])
        self.assertEqual(kwargs["subject"], "Hello Alice")
        self.assertEqual(kwargs["message"], "Hi Alice User")
        self.assertEqual(kwargs["html_message"], "<p>Hi Alice User</p>")
        self.assertEqual(kwargs["cc"], ["cc1@example.com", "cc2@example.com"])
        self.assertEqual(kwargs["bcc"], ["bcc1@example.com"])

    def test_send_emails_accepts_whitespace_separated_cc_bcc(self) -> None:
        from post_office.models import EmailTemplate

        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        class _FakeGroup:
            cn = "example-group"
            description = ""

            def member_usernames_recursive(self) -> set[str]:
                return {"alice"}

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "givenname": ["Alice"],
                "sn": ["User"],
                "displayname": ["Alice User"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str):
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        EmailTemplate.objects.create(
            name="mailmerge-test",
            subject="Hello {{ first_name }}",
            content="Hi {{ full_name }}",
            html_content="<p>Hi {{ full_name }}</p>",
        )

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAGroup.get", return_value=_FakeGroup()),
            patch("core.backends.FreeIPAGroup.all", return_value=[_FakeGroup()]),
            patch("core.views_mailmerge.mail.send", autospec=True) as send,
        ):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "group",
                    "group_cn": "example-group",
                    "subject": "Hello {{ first_name }}",
                    "text_content": "Hi {{ full_name }}",
                    "html_content": "<p>Hi {{ full_name }}</p>",
                    "action": "send",
                    "cc": "cc1@example.com\ncc2@example.com; cc3@example.com",
                    "bcc": "bcc1@example.com\n bcc2@example.com",
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        send.assert_called_once()
        _args, kwargs = send.call_args
        self.assertEqual(kwargs["cc"], ["cc1@example.com", "cc2@example.com", "cc3@example.com"])
        self.assertEqual(kwargs["bcc"], ["bcc1@example.com", "bcc2@example.com"])

    def test_send_emails_renders_extra_context_vars(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        with (
            patch("core.backends.FreeIPAUser.get", return_value=reviewer),
            patch("core.backends.FreeIPAGroup.all", return_value=[]),
            patch("core.views_mailmerge.mail.send", autospec=True) as send,
        ):
            resp = self.client.post(
                reverse("mail-merge"),
                data={
                    "recipient_mode": "manual",
                    "manual_to": "jim@example.com",
                    "subject": "Hello {{ project }}",
                    "text_content": "Hi",
                    "html_content": "<p>Hi</p>",
                    "extra_context_json": json.dumps({"project": "Atomic"}),
                    "action": "send",
                },
                follow=True,
            )

        self.assertEqual(resp.status_code, 200)
        send.assert_called_once()
        _args, kwargs = send.call_args
        self.assertEqual(kwargs["subject"], "Hello Atomic")


class UnifiedEmailPreviewMailMergeTests(TestCase):
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

    def test_unified_preview_requires_loaded_recipients(self) -> None:
        self._login_as_freeipa_user("reviewer")
        reviewer = FreeIPAUser("reviewer", {"uid": ["reviewer"], "memberof_group": ["membership-committee"]})

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp = self.client.post(
                reverse("mail-merge-render-preview"),
                data={
                    "subject": "Hello {{ full_name }}",
                    "html_content": "<p>{{ full_name }}</p>",
                    "text_content": "{{ full_name }}",
                },
            )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("Load recipients", resp.json().get("error", ""))
