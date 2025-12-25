from __future__ import annotations

import datetime
import math
from collections.abc import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.backends import FreeIPAUser
from core.membership_notifications import send_membership_notification
from core.models import MembershipLog
from core.views_utils import _first


class Command(BaseCommand):
    help = "Send membership expiration warning/expired emails via django-post-office."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Send even if an email was already queued today.",
        )

    def handle(self, *args, **options) -> None:
        force: bool = bool(options.get("force"))

        now = timezone.now()
        today_utc = now.astimezone(datetime.UTC).date()

        schedule_divisors = (1, 2, 4, 8, 16, 32)
        schedule_days = [
            math.floor(settings.MEMBERSHIP_EXPIRING_SOON_DAYS / divisor)
            for divisor in schedule_divisors
        ] + [0]

        logs: Iterable[MembershipLog] = (
            MembershipLog.objects.select_related("membership_type")
            .filter(
                action__in=[
                    MembershipLog.Action.approved,
                    MembershipLog.Action.expiry_changed,
                    MembershipLog.Action.terminated,
                ]
            )
            .order_by("target_username", "membership_type_id", "-created_at")
        )

        seen: set[tuple[str, str]] = set()

        queued = 0
        skipped = 0

        for log in logs:
            key = (log.target_username, log.membership_type_id)
            if key in seen:
                continue
            seen.add(key)

            # Terminations are handled immediately when they happen.
            if log.action == MembershipLog.Action.terminated:
                continue

            if not log.expires_at:
                continue

            expires_on_utc = log.expires_at.astimezone(datetime.UTC).date()
            days_until = (expires_on_utc - today_utc).days

            if days_until not in schedule_days:
                continue

            if days_until == 0:
                template = settings.MEMBERSHIP_EXPIRED_EMAIL_TEMPLATE_NAME
            else:
                template = settings.MEMBERSHIP_EXPIRING_SOON_EMAIL_TEMPLATE_NAME

            fu = FreeIPAUser.get(log.target_username)
            if fu is None or not fu.email:
                continue

            tz_name = str(_first(fu._user_data, "fasTimezone", "") or "").strip() or "UTC"

            did_queue = send_membership_notification(
                recipient_email=fu.email,
                username=log.target_username,
                membership_type=log.membership_type,
                template_name=template,
                expires_at=log.expires_at,
                days=days_until,
                force=force,
                tz_name=tz_name,
            )
            if did_queue:
                queued += 1
            else:
                skipped += 1

        self.stdout.write(f"Queued {queued} email(s); skipped {skipped}.")
