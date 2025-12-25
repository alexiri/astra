from __future__ import annotations

import datetime
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import Membership, MembershipLog, MembershipType


class MembershipExpiredCleanupCommandTests(TestCase):
    def test_command_removes_group_deletes_row_and_sends_email(self) -> None:
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

        expired_at = timezone.now() - datetime.timedelta(days=1)
        MembershipLog.objects.create(
            actor_username="reviewer",
            target_username="alice",
            membership_type_id="individual",
            requested_group_cn="almalinux-individual",
            action=MembershipLog.Action.approved,
            expires_at=expired_at,
        )

        self.assertTrue(Membership.objects.filter(target_username="alice", membership_type_id="individual").exists())

        alice = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.com"],
                "fasTimezone": ["UTC"],
                "memberof_group": [],
            },
        )

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            with patch.object(FreeIPAUser, "remove_from_group", autospec=True) as remove_mock:
                call_command("membership_expired_cleanup")

        remove_mock.assert_called_once()
        self.assertFalse(Membership.objects.filter(target_username="alice", membership_type_id="individual").exists())

        from post_office.models import Email

        self.assertTrue(
            Email.objects.filter(
                to="alice@example.com",
                template__name=settings.MEMBERSHIP_EXPIRED_EMAIL_TEMPLATE_NAME,
                context__membership_type_code="individual",
            ).exists()
        )
