from __future__ import annotations

import post_office.mail
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils import timezone

from core.backends import FreeIPAGroup, FreeIPAUser
from core.models import MembershipRequest


def _membership_requests_url(*, base_url: str) -> str:
    path = reverse("membership-requests")
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return path
    return f"{base}{path}"


class Command(BaseCommand):
    help = "Notify the membership committee when pending membership requests exist."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Send even if an email was already queued today.",
        )

    def handle(self, *args, **options) -> None:
        force: bool = bool(options.get("force"))

        pending_count = MembershipRequest.objects.count()
        if pending_count <= 0:
            self.stdout.write("No pending membership requests.")
            return

        committee_cn = str(settings.MEMBERSHIP_COMMITTEE_GROUP_CN or "").strip()
        if not committee_cn:
            raise CommandError("MEMBERSHIP_COMMITTEE_GROUP_CN is not configured")

        committee_group = FreeIPAGroup.get(committee_cn)
        if committee_group is None:
            raise CommandError(f"Unable to load committee group from FreeIPA: {committee_cn}")

        recipients: list[str] = []
        seen: set[str] = set()
        members: Iterable[str] = committee_group.members

        for username in members:
            user = FreeIPAUser.get(username)
            if user is None or not user.email:
                continue
            addr = str(user.email or "").strip()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            recipients.append(addr)

        if not recipients:
            raise CommandError(f"No email addresses found for committee group members: {committee_cn}")

        if not force:
            from post_office.models import Email

            today = timezone.localdate()
            already_sent = Email.objects.filter(
                template__name=settings.MEMBERSHIP_COMMITTEE_PENDING_REQUESTS_EMAIL_TEMPLATE_NAME,
                created__date=today,
            ).exists()
            if already_sent:
                self.stdout.write("Skipped; email already queued today.")
                return

        recipients.sort()
        post_office.mail.send(
            recipients=recipients,
            sender=settings.DEFAULT_FROM_EMAIL,
            template=settings.MEMBERSHIP_COMMITTEE_PENDING_REQUESTS_EMAIL_TEMPLATE_NAME,
            context={
                "pending_count": pending_count,
                "requests_url": _membership_requests_url(base_url=settings.PUBLIC_BASE_URL),
            },
            render_on_delivery=True,
        )

        self.stdout.write(f"Queued 1 email to {len(recipients)} recipient(s).")
