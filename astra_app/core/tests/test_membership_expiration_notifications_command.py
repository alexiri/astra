from __future__ import annotations

import datetime
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import Membership, MembershipLog, MembershipType


class MembershipExpirationNotificationsCommandTests(TestCase):
    def test_command_sends_expiring_soon_email_on_schedule(self) -> None:
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

        today_utc = timezone.now().astimezone(datetime.UTC).date()
        expires_in_days = settings.MEMBERSHIP_EXPIRING_SOON_DAYS // 2
        expires_on_utc = today_utc + datetime.timedelta(days=expires_in_days)
        expires_at_utc = datetime.datetime.combine(expires_on_utc, datetime.time(23, 59, 59), tzinfo=datetime.UTC)

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=expires_at_utc,
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            call_command("membership_expiration_notifications")

        from post_office.models import Email

        self.assertTrue(
            Email.objects.filter(
                to="alice@example.com",
                template__name=settings.MEMBERSHIP_EXPIRING_SOON_EMAIL_TEMPLATE_NAME,
                context__membership_type_code="individual",
            ).exists()
        )

    def test_command_does_not_send_expired_email_for_expired_memberships(self) -> None:
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

        today_utc = timezone.now().astimezone(datetime.UTC).date()
        expires_on_utc = today_utc - datetime.timedelta(days=1)
        expires_at_utc = datetime.datetime.combine(expires_on_utc, datetime.time(23, 59, 59), tzinfo=datetime.UTC)

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=expires_at_utc,
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            call_command("membership_expiration_notifications")

        from post_office.models import Email

        self.assertTrue(
            Membership.objects.filter(target_username="alice", membership_type_id="individual").exists()
        )
        self.assertFalse(
            Email.objects.filter(
                to="alice@example.com",
                template__name=settings.MEMBERSHIP_EXPIRED_EMAIL_TEMPLATE_NAME,
                context__membership_type_code="individual",
            ).exists()
        )

    def test_command_does_not_send_twice_same_day_without_force(self) -> None:
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

        today_utc = timezone.now().astimezone(datetime.UTC).date()
        expires_in_days = settings.MEMBERSHIP_EXPIRING_SOON_DAYS
        expires_on_utc = today_utc + datetime.timedelta(days=expires_in_days)
        expires_at_utc = datetime.datetime.combine(expires_on_utc, datetime.time(23, 59, 59), tzinfo=datetime.UTC)

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=expires_at_utc,
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        from post_office.models import Email

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            call_command("membership_expiration_notifications")
            first_count = Email.objects.count()
            call_command("membership_expiration_notifications")
            second_count = Email.objects.count()

        self.assertEqual(first_count, second_count)

    def test_force_sends_even_if_already_sent_today(self) -> None:
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

        today_utc = timezone.now().astimezone(datetime.UTC).date()
        expires_in_days = settings.MEMBERSHIP_EXPIRING_SOON_DAYS
        expires_on_utc = today_utc + datetime.timedelta(days=expires_in_days)
        expires_at_utc = datetime.datetime.combine(expires_on_utc, datetime.time(23, 59, 59), tzinfo=datetime.UTC)

        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=expires_at_utc,
        )

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "memberof_group": [],
            },
        )

        from post_office.models import Email

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            call_command("membership_expiration_notifications")
            first_count = Email.objects.count()
            call_command("membership_expiration_notifications", "--force")
            second_count = Email.objects.count()

        self.assertEqual(first_count + 1, second_count)
