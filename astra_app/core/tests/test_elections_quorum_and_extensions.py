from __future__ import annotations

import datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import (
    AuditLogEntry,
    Candidate,
    Election,
    FreeIPAPermissionGrant,
    Membership,
    MembershipType,
    VotingCredential,
)
from core.permissions import ASTRA_ADD_ELECTION


class ElectionQuorumAuditTests(TestCase):
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def _grant_manage_permission(self, username: str) -> None:
        FreeIPAPermissionGrant.objects.create(
            principal_type=FreeIPAPermissionGrant.PrincipalType.user,
            principal_name=username,
            permission=ASTRA_ADD_ELECTION,
        )

    def test_quorum_reached_logged_once_when_threshold_met(self) -> None:
        now = timezone.now()
        election = Election.objects.create(
            name="Quorum test",
            description="",
            start_datetime=now - datetime.timedelta(days=1),
            end_datetime=now + datetime.timedelta(days=1),
            number_of_seats=1,
            quorum=100,
            status=Election.Status.open,
        )
        Candidate.objects.create(election=election, freeipa_username="alice", nominated_by="nominator")

        VotingCredential.objects.create(
            election=election,
            public_id="cred-1",
            freeipa_username="voter1",
            weight=1,
        )
        VotingCredential.objects.create(
            election=election,
            public_id="cred-2",
            freeipa_username="voter2",
            weight=1,
        )

        voter_type = MembershipType.objects.create(
            code="voter",
            name="Voter",
            votes=1,
            isIndividual=True,
            enabled=True,
        )
        m1 = Membership.objects.create(target_username="voter1", membership_type=voter_type, expires_at=None)
        m2 = Membership.objects.create(target_username="voter2", membership_type=voter_type, expires_at=None)
        eligible_created_at = election.start_datetime - datetime.timedelta(days=2)
        Membership.objects.filter(pk=m1.pk).update(created_at=eligible_created_at)
        Membership.objects.filter(pk=m2.pk).update(created_at=eligible_created_at)

        self._login_as_freeipa_user("voter1")
        with patch("core.backends.FreeIPAUser.get") as mocked_get:
            mocked_get.return_value = FreeIPAUser(
                "voter1",
                {
                    "uid": ["voter1"],
                    "mail": ["voter1@example.com"],
                    "memberof_group": [],
                    "memberofindirect_group": [],
                },
            )
            resp = self.client.post(
                reverse("election-vote-submit", args=[election.id]),
                {"credential_public_id": "cred-1", "ranking_usernames": "alice"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(AuditLogEntry.objects.filter(election=election, event_type="quorum_reached").exists())

        self._login_as_freeipa_user("voter2")
        with patch("core.backends.FreeIPAUser.get") as mocked_get:
            mocked_get.return_value = FreeIPAUser(
                "voter2",
                {
                    "uid": ["voter2"],
                    "mail": ["voter2@example.com"],
                    "memberof_group": [],
                    "memberofindirect_group": [],
                },
            )
            resp = self.client.post(
                reverse("election-vote-submit", args=[election.id]),
                {"credential_public_id": "cred-2", "ranking_usernames": "alice"},
            )
        self.assertEqual(resp.status_code, 200)

        reached = list(AuditLogEntry.objects.filter(election=election, event_type="quorum_reached"))
        self.assertEqual(len(reached), 1)
        self.assertTrue(reached[0].is_public)

        # Submitting again should not create duplicates.
        self._login_as_freeipa_user("voter2")
        with patch("core.backends.FreeIPAUser.get") as mocked_get:
            mocked_get.return_value = FreeIPAUser(
                "voter2",
                {
                    "uid": ["voter2"],
                    "mail": ["voter2@example.com"],
                    "memberof_group": [],
                    "memberofindirect_group": [],
                },
            )
            resp = self.client.post(
                reverse("election-vote-submit", args=[election.id]),
                {"credential_public_id": "cred-2", "ranking_usernames": "alice"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AuditLogEntry.objects.filter(election=election, event_type="quorum_reached").count(), 1)

    def test_open_election_end_extension_logs_audit_event(self) -> None:
        now = timezone.now()
        election = Election.objects.create(
            name="Extend test",
            description="",
            start_datetime=now - datetime.timedelta(days=1),
            end_datetime=now + datetime.timedelta(days=1),
            number_of_seats=1,
            quorum=50,
            status=Election.Status.open,
        )

        self._login_as_freeipa_user("admin")
        self._grant_manage_permission("admin")

        with patch("core.backends.FreeIPAUser.get") as mocked_get:
            mocked_get.return_value = FreeIPAUser(
                "admin",
                {
                    "uid": ["admin"],
                    "mail": ["admin@example.com"],
                    "memberof_group": [],
                    "memberofindirect_group": [],
                },
            )

            new_end = now + datetime.timedelta(days=2)
            resp = self.client.post(
                reverse("election-edit", args=[election.id]),
                {"action": "extend_end", "end_datetime": new_end.strftime("%Y-%m-%dT%H:%M")},
            )
        self.assertEqual(resp.status_code, 302)

        election.refresh_from_db()
        self.assertGreater(election.end_datetime, now + datetime.timedelta(days=1))

        entries = list(AuditLogEntry.objects.filter(election=election, event_type="election_end_extended"))
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].is_public)
        payload = entries[0].payload if isinstance(entries[0].payload, dict) else {}
        self.assertIn("previous_end_datetime", payload)
        self.assertIn("new_end_datetime", payload)
        self.assertIn("quorum_percent", payload)
