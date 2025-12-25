from __future__ import annotations

import datetime
from collections.abc import Iterable

from django.conf import settings
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import Membership


def is_membership_committee_user(user: object) -> bool:
    if not isinstance(user, FreeIPAUser):
        return False

    committee_cn = str(settings.MEMBERSHIP_COMMITTEE_GROUP_CN or "").strip()
    if not committee_cn:
        return False

    committee_key = committee_cn.lower()
    return any(str(g or "").lower() == committee_key for g in user.groups_list)


def get_valid_memberships_for_username(username: str) -> list[Membership]:
    """Return the current unexpired active memberships.

    This is used to:
    - show current memberships on a user's profile
    - prevent requesting a membership type that is already valid
    """

    now = timezone.now()

    memberships: Iterable[Membership] = (
        Membership.objects.select_related("membership_type")
        .filter(
            target_username=username,
            expires_at__gt=now,
        )
        .order_by("membership_type__sort_order", "membership_type__code")
    )

    return list(memberships)


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
