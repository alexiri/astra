from __future__ import annotations

import datetime
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.backends import FreeIPAUser


class MembershipProfileSidebarAndRequestsTests(TestCase):
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def _make_user(self, username: str, *, full_name: str = "", groups: list[str] | None = None) -> FreeIPAUser:
        givenname = ""
        sn = ""
        if full_name and " " in full_name:
            givenname, sn = full_name.split(" ", 1)
        return FreeIPAUser(
            username,
            {
                "uid": [username],
                "givenname": [givenname] if givenname else [],
                "sn": [sn] if sn else [],
                "cn": [full_name] if full_name else [],
                "displayname": [full_name] if full_name else [],
                "mail": [f"{username}@example.com"],
                "memberof_group": list(groups or []),
            },
        )

    def test_profile_shows_request_link_when_no_membership(self) -> None:
        from core.models import MembershipType

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

        alice = self._make_user("alice", full_name="Alice User")
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            with patch("core.views_users._get_full_user", return_value=alice):
                with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[]):
                    with patch("core.views_users.has_enabled_agreements", autospec=True, return_value=False):
                        resp = self.client.get(reverse("user-profile", kwargs={"username": "alice"}))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Membership")
        self.assertContains(resp, reverse("membership-request"))

    def test_profile_shows_pending_membership_request_greyed_out(self) -> None:
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

        alice = self._make_user("alice", full_name="Alice User")
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            with patch("core.views_users._get_full_user", return_value=alice):
                with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[]):
                    with patch("core.views_users.has_enabled_agreements", autospec=True, return_value=False):
                        resp = self.client.get(reverse("user-profile", kwargs={"username": "alice"}))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pending")
        self.assertContains(resp, "Individual")

    def test_profile_shows_extend_button_when_membership_expires_soon(self) -> None:
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

        now = timezone.now()
        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=now + datetime.timedelta(days=50),
        )

        alice = self._make_user("alice", full_name="Alice User")
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            with patch("core.views_users._get_full_user", return_value=alice):
                with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[]):
                    with patch("core.views_users.has_enabled_agreements", autospec=True, return_value=False):
                        resp = self.client.get(reverse("user-profile", kwargs={"username": "alice"}))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Extend")
        self.assertContains(resp, reverse("membership-request") + "?membership_type=individual")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp_request = self.client.get(reverse("membership-request"))
        self.assertEqual(resp_request.status_code, 200)
        self.assertContains(resp_request, 'value="individual"')

    def test_terminated_membership_does_not_count_as_active(self) -> None:
        import datetime

        from django.utils import timezone

        from core.membership import get_valid_memberships_for_username
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

        now = timezone.now()
        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=now + datetime.timedelta(days=200),
        )
        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.terminated,
            expires_at=now,
        )

        valid = get_valid_memberships_for_username("alice")
        self.assertEqual(valid, [])

    def test_user_cannot_request_membership_type_if_already_valid(self) -> None:
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

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=timezone.now() + datetime.timedelta(days=200),
        )

        alice = self._make_user("alice", full_name="Alice User")
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp_get = self.client.get(reverse("membership-request"))
        self.assertEqual(resp_get.status_code, 200)
        self.assertNotContains(resp_get, 'value="individual"')

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp_post = self.client.post(
                reverse("membership-request"),
                data={"membership_type": "individual"},
            )

        self.assertEqual(resp_post.status_code, 200)
        self.assertFalse(MembershipRequest.objects.filter(requested_username="alice").exists())

    def test_profile_disables_request_button_when_no_membership_types_available(self) -> None:
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

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=timezone.now() + datetime.timedelta(days=200),
        )

        alice = self._make_user("alice", full_name="Alice User")
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            with patch("core.views_users._get_full_user", return_value=alice):
                with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[]):
                    with patch("core.views_users.has_enabled_agreements", autospec=True, return_value=False):
                        resp = self.client.get(reverse("user-profile", kwargs={"username": "alice"}))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Request")
        self.assertContains(resp, "disabled")

    def test_committee_can_terminate_membership_early_and_it_is_logged(self) -> None:
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

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=timezone.now() + datetime.timedelta(days=200),
        )

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        alice = self._make_user("alice", full_name="Alice User")

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch.object(FreeIPAUser, "remove_from_group", autospec=True) as remove_mock:
                with patch("post_office.mail.send", autospec=True) as send_mock:
                    resp = self.client.post(
                        reverse(
                            "membership-terminate",
                            kwargs={"username": "alice", "membership_type_code": "individual"},
                        ),
                        follow=False,
                    )

        self.assertEqual(resp.status_code, 302)
        remove_mock.assert_not_called()
        self.assertTrue(
            MembershipLog.objects.filter(
                actor_username="reviewer",
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.terminated,
            ).exists()
        )

        send_mock.assert_not_called()

    def test_committee_can_change_membership_expiration_date_and_it_is_logged(self) -> None:
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

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=timezone.now() + datetime.timedelta(days=200),
        )

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        alice = self._make_user("alice", full_name="Alice User")

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            resp = self.client.post(
                reverse(
                    "membership-set-expiry",
                    kwargs={"username": "alice", "membership_type_code": "individual"},
                ),
                data={"expires_on": "2030-01-02"},
                follow=False,
            )

        self.assertEqual(resp.status_code, 302)
        log = (
            MembershipLog.objects.filter(
                actor_username="reviewer",
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.expiry_changed,
            )
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(log)
        assert log is not None
        self.assertIsNotNone(log.expires_at)
        assert log.expires_at is not None
        self.assertEqual(log.expires_at.tzinfo, datetime.UTC)
        self.assertEqual(log.expires_at, datetime.datetime(2030, 1, 2, 23, 59, 59, tzinfo=datetime.UTC))

    def test_committee_sidebar_link_has_badge_green_when_zero_red_when_nonzero(self) -> None:
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

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            with patch("core.views_users.FreeIPAUser.all", autospec=True, return_value=[]):
                resp0 = self.client.get(reverse("users"))

        self.assertEqual(resp0.status_code, 200)
        self.assertContains(resp0, reverse("membership-requests"))
        self.assertContains(resp0, "badge-success")

        MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            with patch("core.views_users.FreeIPAUser.all", autospec=True, return_value=[]):
                resp1 = self.client.get(reverse("users"))

        self.assertEqual(resp1.status_code, 200)
        self.assertContains(resp1, reverse("membership-requests"))
        self.assertContains(resp1, "badge-danger")

    def test_committee_sidebar_has_audit_log_link_to_all_users(self) -> None:
        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            with patch("core.views_users.FreeIPAUser.all", autospec=True, return_value=[]):
                resp = self.client.get(reverse("users"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("membership-audit-log"))

    def test_requests_list_links_to_profile_and_shows_full_name(self) -> None:
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
        req = MembershipRequest.objects.create(requested_username="alice", membership_type_id="individual")

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        alice = self._make_user("alice", full_name="Alice User")

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            resp = self.client.get(reverse("membership-requests"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("user-profile", kwargs={"username": req.requested_username}))
        self.assertContains(resp, "Alice User")

    def test_membership_request_only_allows_individual_membership_types(self) -> None:
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
        MembershipType.objects.update_or_create(
            code="mirror",
            defaults={
                "name": "Mirror",
                "group_cn": "almalinux-mirror",
                "isIndividual": False,
                "isOrganization": True,
                "sort_order": 1,
                "enabled": True,
            },
        )

        alice = self._make_user("alice", full_name="Alice User")
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp_get = self.client.get(reverse("membership-request"))

        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'value="individual"')
        self.assertNotContains(resp_get, 'value="mirror"')

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp_post = self.client.post(
                reverse("membership-request"),
                data={"membership_type": "mirror"},
            )

        self.assertEqual(resp_post.status_code, 200)
        self.assertFalse(MembershipRequest.objects.filter(requested_username="alice").exists())

    def test_membership_audit_log_is_paginated_50_per_page(self) -> None:
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

        base_time = timezone.now()
        for i in range(51):
            MembershipLog.objects.create(
                actor_username="reviewer",
                target_username=f"user{i}",
                membership_type=mt,
                requested_group_cn=mt.group_cn,
                action=MembershipLog.Action.requested,
                created_at=base_time + datetime.timedelta(seconds=i),
            )

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp_page_1 = self.client.get(reverse("membership-audit-log"))
        self.assertEqual(resp_page_1.status_code, 200)
        self.assertContains(resp_page_1, "user50")
        self.assertNotContains(resp_page_1, "user0")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp_page_2 = self.client.get(reverse("membership-audit-log") + "?page=2")
        self.assertEqual(resp_page_2.status_code, 200)
        self.assertContains(resp_page_2, "user0")

    def test_committee_can_view_membership_audit_log_all_and_by_user(self) -> None:
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

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=timezone.now() + datetime.timedelta(days=settings.MEMBERSHIP_VALIDITY_DAYS),
        )

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp_all = self.client.get(reverse("membership-audit-log"))

        self.assertEqual(resp_all.status_code, 200)
        self.assertContains(resp_all, "Membership Audit Log")
        self.assertContains(resp_all, "alice")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp_user = self.client.get(reverse("membership-audit-log-user", kwargs={"username": "alice"}))

        self.assertEqual(resp_user.status_code, 200)
        self.assertContains(resp_user, "Membership Audit Log")
        self.assertContains(resp_user, "alice")

    def test_membership_management_menu_stays_open_on_child_pages(self) -> None:
        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        self._login_as_freeipa_user("reviewer")

        with patch("core.backends.FreeIPAUser.get", return_value=reviewer):
            resp = self.client.get(reverse("membership-audit-log"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Membership Management")
        self.assertContains(resp, "menu-open")

    def test_profile_shows_membership_audit_log_button_for_committee_viewer(self) -> None:
        from core.models import MembershipType

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

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])
        alice = self._make_user("alice", full_name="Alice User")

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "reviewer":
                return reviewer
            if username == "alice":
                return alice
            return None

        self._login_as_freeipa_user("reviewer")
        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch("core.views_users._get_full_user", return_value=alice):
                with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[]):
                    with patch("core.views_users.has_enabled_agreements", autospec=True, return_value=False):
                        resp = self.client.get(reverse("user-profile", kwargs={"username": "alice"}))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("membership-audit-log-user", kwargs={"username": "alice"}))

    def test_profile_shows_expiry_in_users_timezone(self) -> None:
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

        expires_at_utc = timezone.now() + datetime.timedelta(days=2)
        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=expires_at_utc,
        )

        committee_cn = settings.MEMBERSHIP_COMMITTEE_GROUP_CN
        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
                "fasTimezone": ["Australia/Brisbane"],
            },
        )
        reviewer = self._make_user("reviewer", full_name="Reviewer Person", groups=[committee_cn])

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alice":
                return alice
            if username == "reviewer":
                return reviewer
            return None

        self._login_as_freeipa_user("alice")
        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            with patch("core.views_users._get_full_user", return_value=alice):
                with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[]):
                    with patch("core.views_users.has_enabled_agreements", autospec=True, return_value=False):
                        resp = self.client.get(reverse("user-profile", kwargs={"username": "alice"}))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "(Australia/Brisbane)")
