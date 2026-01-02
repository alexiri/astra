from __future__ import annotations

import datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import Candidate, Election, FreeIPAPermissionGrant, Membership, MembershipType, VotingCredential
from core.permissions import ASTRA_ADD_ELECTION


class ElectionEditLifecycleTests(TestCase):
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def _grant_manage_elections(self, username: str) -> None:
        FreeIPAPermissionGrant.objects.create(
            principal_type=FreeIPAPermissionGrant.PrincipalType.user,
            principal_name=username,
            permission=ASTRA_ADD_ELECTION,
        )

    def test_edit_start_election_opens_issues_and_emails(self) -> None:
        now = timezone.now()
        started_at = now + datetime.timedelta(hours=3)
        election = Election.objects.create(
            name="Draft election",
            description="",
            url="",
            start_datetime=now + datetime.timedelta(days=1),
            end_datetime=now + datetime.timedelta(days=2),
            number_of_seats=1,
            status=Election.Status.draft,
            voting_email_subject="Hello {{ username }}",
            voting_email_html="<p>Hi {{ username }}</p>",
            voting_email_text="Hi {{ username }}",
        )
        Candidate.objects.create(election=election, freeipa_username="alice", nominated_by="nominator", ordering=1)

        mt = MembershipType.objects.create(
            code="voter",
            name="Voter",
            description="",
            isIndividual=True,
            isOrganization=False,
            sort_order=1,
            enabled=True,
            votes=1,
        )
        m = Membership.objects.create(target_username="voter1", membership_type=mt, expires_at=None)
        Membership.objects.filter(pk=m.pk).update(created_at=now - datetime.timedelta(days=200))

        self._login_as_freeipa_user("admin")
        self._grant_manage_elections("admin")

        admin_user = FreeIPAUser("admin", {"uid": ["admin"], "memberof_group": []})
        voter_user = FreeIPAUser(
            "voter1",
            {"uid": ["voter1"], "memberof_group": [], "mail": ["voter1@example.com"]},
        )

        def get_user(username: str):
            if username == "admin":
                return admin_user
            if username == "voter1":
                return voter_user
            return None

        start_str = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        end_str = (now + datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")

        with (
            patch("core.backends.FreeIPAUser.get", side_effect=get_user),
            patch("core.views_elections.timezone.now", return_value=started_at),
            patch("post_office.mail.send", autospec=True) as post_office_send_mock,
        ):
            resp = self.client.post(
                reverse("election-edit", args=[election.id]),
                data={
                    "action": "start_election",
                    "name": election.name,
                    "description": election.description,
                    "url": election.url,
                    "start_datetime": start_str,
                    "end_datetime": end_str,
                    "number_of_seats": str(election.number_of_seats),
                    "email_template_id": "",
                    "subject": election.voting_email_subject,
                    "html_content": election.voting_email_html,
                    "text_content": election.voting_email_text,
                },
                follow=False,
            )

        self.assertEqual(resp.status_code, 302)
        election.refresh_from_db()
        self.assertEqual(election.status, Election.Status.open)
        self.assertEqual(election.start_datetime, started_at)
        self.assertEqual(election.start_datetime.tzinfo, timezone.UTC)
        self.assertTrue(VotingCredential.objects.filter(election=election, freeipa_username="voter1").exists())

        # Snapshot templates should be rendered into explicit subject/body sends.
        self.assertEqual(post_office_send_mock.call_count, 1)
        self.assertEqual(post_office_send_mock.call_args.kwargs.get("recipients"), ["voter1@example.com"])
        self.assertEqual(post_office_send_mock.call_args.kwargs.get("subject"), "Hello voter1")
        self.assertNotIn("template", post_office_send_mock.call_args.kwargs)

    def test_edit_rejects_end_election_action(self) -> None:
        now = timezone.now()
        election = Election.objects.create(
            name="Open election",
            description="",
            url="",
            start_datetime=now - datetime.timedelta(days=1),
            end_datetime=now + datetime.timedelta(days=1),
            number_of_seats=1,
            status=Election.Status.open,
        )
        VotingCredential.objects.create(
            election=election,
            public_id="cred-1",
            freeipa_username="voter1",
            weight=1,
        )

        self._login_as_freeipa_user("admin")
        self._grant_manage_elections("admin")

        admin_user = FreeIPAUser("admin", {"uid": ["admin"], "memberof_group": []})

        with patch("core.backends.FreeIPAUser.get", return_value=admin_user):
            resp = self.client.post(
                reverse("election-edit", args=[election.id]),
                data={
                    "action": "end_election",
                    "name": election.name,
                    "description": election.description,
                    "url": election.url,
                    "start_datetime": (now - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                    "end_datetime": (now + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                    "number_of_seats": str(election.number_of_seats),
                    "email_template_id": "",
                    "subject": "",
                    "html_content": "",
                    "text_content": "",
                },
                follow=False,
            )

        self.assertEqual(resp.status_code, 400)
        election.refresh_from_db()
        self.assertEqual(election.status, Election.Status.open)
        self.assertEqual(VotingCredential.objects.get(election=election).freeipa_username, "voter1")
