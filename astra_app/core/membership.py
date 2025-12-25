from __future__ import annotations

import datetime
from collections.abc import Iterable

from django.conf import settings
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import MembershipLog


def is_membership_committee_user(user: object) -> bool:
    if not isinstance(user, FreeIPAUser):
        return False

    committee_cn = str(settings.MEMBERSHIP_COMMITTEE_GROUP_CN or "").strip()
    if not committee_cn:
        return False

    committee_key = committee_cn.lower()
    return any(str(g or "").lower() == committee_key for g in user.groups_list)


def get_valid_memberships_for_username(username: str) -> list[MembershipLog]:
    """Return the latest unexpired approved membership per membership type.

    This is used to:
    - show current memberships on a user's profile
    - prevent requesting a membership type that is already valid
    """

    now = timezone.now()

    logs: Iterable[MembershipLog] = (
        MembershipLog.objects.select_related("membership_type")
        .filter(
            target_username=username,
            action__in=[
                MembershipLog.Action.approved,
                MembershipLog.Action.expiry_changed,
                MembershipLog.Action.terminated,
            ],
        )
        .order_by("-created_at")
    )

    by_type_code: dict[str, MembershipLog] = {}
    seen_type_codes: set[str] = set()

    for log in logs:
        # `membership_type_id` is the MembershipType.code (FK to_field_name is PK).
        type_code = log.membership_type_id
        if type_code in seen_type_codes:
            continue
        seen_type_codes.add(type_code)

        # A termination is a state change that should block any earlier approvals.
        if log.action == MembershipLog.Action.terminated:
            continue

        expires_at = log.expires_at
        if not expires_at or expires_at <= now:
            continue

        by_type_code[type_code] = log

    return sorted(
        by_type_code.values(),
        key=lambda log: (log.membership_type.sort_order, log.membership_type.code),
    )


def get_valid_membership_type_codes_for_username(username: str) -> set[str]:
    return {log.membership_type_id for log in get_valid_memberships_for_username(username)}


def get_extendable_membership_type_codes_for_username(username: str) -> set[str]:
    now = timezone.now()
    expiring_soon_by = now + datetime.timedelta(days=settings.MEMBERSHIP_EXPIRING_SOON_DAYS)
    return {
        log.membership_type_id
        for log in get_valid_memberships_for_username(username)
        if log.expires_at and log.expires_at <= expiring_soon_by
    }
