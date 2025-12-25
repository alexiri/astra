from __future__ import annotations

from core.membership import is_membership_committee_user
from core.models import MembershipRequest


def membership_review(request) -> dict[str, object]:
    if not hasattr(request, "user"):
        # Some template-tag tests render templates with a minimal request object.
        return {
            "is_membership_committee": False,
            "membership_requests_pending_count": 0,
        }

    user = request.user
    is_committee = is_membership_committee_user(user)
    pending_count = MembershipRequest.objects.count() if is_committee else 0
    return {
        "is_membership_committee": is_committee,
        "membership_requests_pending_count": pending_count,
    }
