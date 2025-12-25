from __future__ import annotations

from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.backends import FreeIPAUser


class MembershipRequestsFlowTests(TestCase):
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_user_can_request_membership_and_email_is_sent(self) -> None:
        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            with patch("post_office.mail.send", autospec=True) as send_mock:
                resp = self.client.post(
                    reverse("membership-request"),
                    data={"membership_type": "individual"},
                    follow=False,
                )

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            MembershipRequest.objects.filter(requested_username="alice", membership_type_id="individual").exists()
        )
        self.assertTrue(
            MembershipLog.objects.filter(
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.requested,
            ).exists()
        )

        send_mock.assert_called_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs["recipients"], ["alice@example.com"])
        self.assertEqual(kwargs["sender"], settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(kwargs["template"], settings.MEMBERSHIP_REQUEST_SUBMITTED_EMAIL_TEMPLATE_NAME)
        self.assertEqual(kwargs["context"]["username"], "alice")
        self.assertEqual(kwargs["context"]["membership_type"], "Individual")

    def test_committee_can_approve_request_adds_user_to_group_logs_and_emails(self) -> None:
        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )
        req = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch.object(FreeIPAUser, "add_to_group", autospec=True) as add_mock:
                with patch("post_office.mail.send", autospec=True) as send_mock:
                    resp = self.client.post(
                        reverse("membership-request-approve", args=[req.pk]),
                        follow=False,
                    )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MembershipRequest.objects.filter(pk=req.pk).exists())
        add_mock.assert_called_once()
        _, call_kwargs = add_mock.call_args
        self.assertEqual(call_kwargs["group_name"], "almalinux-individual")

        self.assertTrue(
            MembershipLog.objects.filter(
                actor_username="reviewer",
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.approved,
            ).exists()
        )

        send_mock.assert_called_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs["recipients"], ["alice@example.com"])
        self.assertEqual(kwargs["template"], settings.MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME)

    def test_committee_can_reject_request_logs_and_emails_with_reason(self) -> None:
        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )
        req = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch("post_office.mail.send", autospec=True) as send_mock:
                resp = self.client.post(
                    reverse("membership-request-reject", args=[req.pk]),
                    data={"reason": "Missing required info"},
                    follow=False,
                )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MembershipRequest.objects.filter(pk=req.pk).exists())
        self.assertTrue(
            MembershipLog.objects.filter(
                actor_username="reviewer",
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.rejected,
                rejection_reason__icontains="Missing required info",
            ).exists()
        )

        send_mock.assert_called_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs["recipients"], ["alice@example.com"])
        self.assertEqual(kwargs["template"], settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME)
        self.assertIn("Missing required info", kwargs["context"]["rejection_reason"])

    def test_committee_can_ignore_request_logs_and_does_not_email(self) -> None:
        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )
        req = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )

        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            with patch("post_office.mail.send", autospec=True) as send_mock:
                resp = self.client.post(
                    reverse("membership-request-ignore", args=[req.pk]),
                    follow=False,
                )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MembershipRequest.objects.filter(pk=req.pk).exists())
        self.assertTrue(
            MembershipLog.objects.filter(
                actor_username="reviewer",
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.ignored,
            ).exists()
        )
        send_mock.assert_not_called()

    def test_extension_starts_when_current_membership_ends(self) -> None:
        import datetime

        from django.utils import timezone

        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )

        now = timezone.now()
        current_expires = now + datetime.timedelta(days=100)
        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=current_expires,
        )

        req = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch.object(FreeIPAUser, "add_to_group", autospec=True):
                with patch("post_office.mail.send", autospec=True):
                    resp = self.client.post(reverse("membership-request-approve", args=[req.pk]), follow=False)

        self.assertEqual(resp.status_code, 302)
        latest = (
            MembershipLog.objects.filter(
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.approved,
            )
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(latest)
        assert latest is not None
        expected = current_expires + datetime.timedelta(days=settings.MEMBERSHIP_VALIDITY_DAYS)
        self.assertEqual(latest.expires_at, expected)

    def test_pending_request_count_renders_in_nav_for_committee(self) -> None:
        from core.models import MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )
        MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")
        MembershipRequest.objects.create(requested_username="bob", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )

        self._login_as_freeipa_user("reviewer")
        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            with patch("core.views_users.FreeIPAUser.all", autospec=True, return_value=[]):
                resp = self.client.get(reverse("users"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'navbar-badge">2<')
        self.assertContains(resp, 'Membership Requests')

    def test_approval_expiry_is_end_of_day_utc(self) -> None:
        import datetime

        from core.models import MembershipLog, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )
        mt = MembershipType.objects.get(code="individual")

        approved_at = datetime.datetime(2026, 1, 20, 10, 15, 0, tzinfo=datetime.UTC)
        with patch("django.utils.timezone.now", autospec=True, return_value=approved_at):
            log = MembershipLog.create_for_approval(
                actor_username="reviewer",
                target_username="alice",
                membership_type=mt,
            )

        expected_expires_at = datetime.datetime(
            2027,
            1,
            20,
            23,
            59,
            59,
            tzinfo=datetime.UTC,
        )
        self.assertEqual(log.expires_at, expected_expires_at)

    def test_committee_can_bulk_approve_requests(self) -> None:
        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )

        req1 = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")
        req2 = MembershipRequest.objects.create(requested_username="bob", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )
        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )
        bob = FreeIPAUser(
            "bob",
            {
                "uid": ["bob"],
                "mail": ["bob@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            if username == "bob":
                return bob
            return None

        self._login_as_freeipa_user("reviewer")
        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch.object(FreeIPAUser, "add_to_group", autospec=True) as add_mock:
                with patch("post_office.mail.send", autospec=True) as send_mock:
                    resp = self.client.post(
                        reverse("membership-requests-bulk"),
                        data={
                            "bulk_action": "approve",
                            "selected": [str(req1.pk), str(req2.pk)],
                        },
                        follow=False,
                    )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MembershipRequest.objects.filter(pk=req1.pk).exists())
        self.assertFalse(MembershipRequest.objects.filter(pk=req2.pk).exists())
        self.assertEqual(add_mock.call_count, 2)
        send_mock.assert_called()
        self.assertEqual(send_mock.call_count, 2)

        self.assertTrue(
            MembershipLog.objects.filter(
                actor_username="reviewer",
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.approved,
            ).exists()
        )
        self.assertTrue(
            MembershipLog.objects.filter(
                actor_username="reviewer",
                target_username="bob",
                membership_type_id="individual",
                action=MembershipLog.Action.approved,
            ).exists()
        )

    def test_committee_can_bulk_ignore_requests(self) -> None:
        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )

        req1 = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")
        req2 = MembershipRequest.objects.create(requested_username="bob", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )

        self._login_as_freeipa_user("reviewer")
        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            with patch("post_office.mail.send", autospec=True) as send_mock:
                resp = self.client.post(
                    reverse("membership-requests-bulk"),
                    data={
                        "bulk_action": "ignore",
                        "selected": [str(req1.pk), str(req2.pk)],
                    },
                    follow=False,
                )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MembershipRequest.objects.filter(pk=req1.pk).exists())
        self.assertFalse(MembershipRequest.objects.filter(pk=req2.pk).exists())
        send_mock.assert_not_called()
        self.assertTrue(MembershipLog.objects.filter(target_username="alice", action=MembershipLog.Action.ignored).exists())
        self.assertTrue(MembershipLog.objects.filter(target_username="bob", action=MembershipLog.Action.ignored).exists())

    def test_committee_can_bulk_reject_requests(self) -> None:
        from core.models import MembershipLog, MembershipRequest, MembershipType

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "sort_order": 0,
                "enabled": True,
            },
        )

        req1 = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")
        req2 = MembershipRequest.objects.create(requested_username="bob", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = FreeIPAUser(
            "reviewer",
            {
                "uid": ["reviewer"],
                "mail": ["reviewer@example.com"],
                "memberof_group": [committee_cn],
            },
        )
        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )
        bob = FreeIPAUser(
            "bob",
            {
                "uid": ["bob"],
                "mail": ["bob@example.com"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            if username == "bob":
                return bob
            return None

        self._login_as_freeipa_user("reviewer")
        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch("post_office.mail.send", autospec=True) as send_mock:
                resp = self.client.post(
                    reverse("membership-requests-bulk"),
                    data={
                        "bulk_action": "reject",
                        "selected": [str(req1.pk), str(req2.pk)],
                    },
                    follow=False,
                )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MembershipRequest.objects.filter(pk=req1.pk).exists())
        self.assertFalse(MembershipRequest.objects.filter(pk=req2.pk).exists())
        self.assertEqual(send_mock.call_count, 2)
        self.assertTrue(MembershipLog.objects.filter(target_username="alice", action=MembershipLog.Action.rejected).exists())
        self.assertTrue(MembershipLog.objects.filter(target_username="bob", action=MembershipLog.Action.rejected).exists())
