from __future__ import annotations

import datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import elections_services
from core.backends import FreeIPAUser
from core.models import AuditLogEntry, Ballot, Candidate, Election, FreeIPAPermissionGrant
from core.permissions import ASTRA_ADD_ELECTION
from core.tests.ballot_chain import GENESIS_CHAIN_HASH, compute_chain_hash


class ElectionAuditLogPageTests(TestCase):
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_election_detail_shows_audit_log_button_when_tallied(self) -> None:
        self._login_as_freeipa_user("viewer")

        now = timezone.now()
        election = Election.objects.create(
            name="Audit election",
            description="",
            start_datetime=now - datetime.timedelta(days=2),
            end_datetime=now - datetime.timedelta(days=1),
            number_of_seats=1,
            status=Election.Status.tallied,
            tally_result={"quota": "1", "elected": [], "eliminated": [], "forced_excluded": [], "rounds": []},
        )
        Candidate.objects.create(
            election=election,
            freeipa_username="alice",
            nominated_by="nominator",
            ordering=1,
        )

        viewer = FreeIPAUser("viewer", {"uid": ["viewer"], "memberof_group": []})
        alice = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": []})
        nominator = FreeIPAUser("nominator", {"uid": ["nominator"], "memberof_group": []})

        def _get_user(username: str):
            if username == "viewer":
                return viewer
            if username == "alice":
                return alice
            if username == "nominator":
                return nominator
            return None

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            resp = self.client.get(reverse("election-detail", args=[election.id]))

        self.assertEqual(resp.status_code, 200)

        audit_url = reverse("election-audit-log", args=[election.id])
        ballots_url = reverse("election-public-ballots", args=[election.id])
        audit_json_url = reverse("election-public-audit", args=[election.id])

        self.assertContains(resp, "View audit log")
        self.assertContains(resp, f'href="{audit_url}"')

        # Keep the Audit Log button above the existing download buttons.
        html = resp.content.decode("utf-8")
        self.assertLess(html.find(audit_url), html.find(ballots_url))
        self.assertLess(html.find(audit_url), html.find(audit_json_url))

    def test_audit_log_page_renders_timeline_with_tally_rounds(self) -> None:
        self._login_as_freeipa_user("viewer")

        now = timezone.now()
        election = Election.objects.create(
            name="Audit log timeline",
            description="",
            start_datetime=now - datetime.timedelta(days=2),
            end_datetime=now - datetime.timedelta(days=1),
            number_of_seats=1,
            status=Election.Status.closed,
        )
        c1 = Candidate.objects.create(
            election=election,
            freeipa_username="alice",
            nominated_by="nominator",
            ordering=1,
        )
        ballot_hash = Ballot.compute_hash(
            election_id=election.id,
            credential_public_id="cred-1",
            ranking=[c1.id],
            weight=1,
            nonce="0" * 32,
        )
        chain_hash = compute_chain_hash(previous_chain_hash=GENESIS_CHAIN_HASH, ballot_hash=ballot_hash)
        Ballot.objects.create(
            election=election,
            credential_public_id="cred-1",
            ranking=[c1.id],
            weight=1,
            ballot_hash=ballot_hash,
            previous_chain_hash=GENESIS_CHAIN_HASH,
            chain_hash=chain_hash,
        )

        elections_services.tally_election(election=election)
        election.refresh_from_db()
        self.assertEqual(election.status, Election.Status.tallied)

        viewer = FreeIPAUser("viewer", {"uid": ["viewer"], "memberof_group": []})
        with patch("core.backends.FreeIPAUser.get", return_value=viewer):
            resp = self.client.get(reverse("election-audit-log", args=[election.id]))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "class=\"timeline\"")
        # The Meek tally always emits iteration summaries.
        self.assertContains(resp, "Iteration 1")
        # Candidate IDs should not appear in summaries/audit text.
        self.assertNotContains(resp, f"(#{c1.id})")
        # Quota is total/(seats+1) = 1/2.
        self.assertContains(resp, "0.5000")

    def test_audit_log_groups_ballot_submissions_by_day_for_managers(self) -> None:
        self._login_as_freeipa_user("admin")
        FreeIPAPermissionGrant.objects.create(
            principal_type=FreeIPAPermissionGrant.PrincipalType.user,
            principal_name="admin",
            permission=ASTRA_ADD_ELECTION,
        )

        now = timezone.now()
        election = Election.objects.create(
            name="Long election",
            description="",
            start_datetime=now - datetime.timedelta(days=10),
            end_datetime=now - datetime.timedelta(days=1),
            number_of_seats=1,
            status=Election.Status.closed,
        )

        day1 = (now - datetime.timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        day2 = (now - datetime.timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0)

        e1 = AuditLogEntry.objects.create(
            election=election,
            event_type="ballot_submitted",
            payload={"ballot_hash": "hash-1"},
            is_public=False,
        )
        e2 = AuditLogEntry.objects.create(
            election=election,
            event_type="ballot_submitted",
            payload={"ballot_hash": "hash-2"},
            is_public=False,
        )
        e3 = AuditLogEntry.objects.create(
            election=election,
            event_type="ballot_submitted",
            payload={"ballot_hash": "hash-3"},
            is_public=False,
        )
        e4 = AuditLogEntry.objects.create(
            election=election,
            event_type="ballot_submitted",
            payload={"ballot_hash": "hash-4"},
            is_public=False,
        )

        AuditLogEntry.objects.filter(id=e1.id).update(timestamp=day1)
        AuditLogEntry.objects.filter(id=e2.id).update(timestamp=day1 + datetime.timedelta(hours=1))
        AuditLogEntry.objects.filter(id=e3.id).update(timestamp=day1 + datetime.timedelta(hours=2))
        AuditLogEntry.objects.filter(id=e4.id).update(timestamp=day2)

        admin = FreeIPAUser("admin", {"uid": ["admin"], "memberof_group": []})
        with patch("core.backends.FreeIPAUser.get", return_value=admin):
            resp = self.client.get(reverse("election-audit-log", args=[election.id]))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ballots submitted")
        self.assertContains(resp, "<details", html=False)
        # The daily summary is expandable (no JS) and includes ballot hashes inline.
        self.assertContains(resp, "hash-1")
        self.assertContains(resp, "hash-2")
        self.assertContains(resp, "hash-3")
        self.assertContains(resp, "hash-4")
