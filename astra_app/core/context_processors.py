from __future__ import annotations

from core.permissions import (
    ASTRA_ADD_MEMBERSHIP,
    ASTRA_CHANGE_MEMBERSHIP,
    ASTRA_DELETE_MEMBERSHIP,
    ASTRA_VIEW_MEMBERSHIP,
)
from core.models import MembershipRequest, Organization


def membership_review(request) -> dict[str, object]:
    if not hasattr(request, "user"):
        # Some template-tag tests render templates with a minimal request object.
        return {
            "membership_can_add": False,
            "membership_can_change": False,
            "membership_can_delete": False,
            "membership_can_view": False,
            "membership_requests_pending_count": 0,
        }

    user = request.user

    has_has_perm = hasattr(user, "has_perm")
    membership_can_add = bool(has_has_perm and user.has_perm(ASTRA_ADD_MEMBERSHIP))
    membership_can_change = bool(has_has_perm and user.has_perm(ASTRA_CHANGE_MEMBERSHIP))
    membership_can_delete = bool(has_has_perm and user.has_perm(ASTRA_DELETE_MEMBERSHIP))
    membership_can_view = bool(has_has_perm and user.has_perm(ASTRA_VIEW_MEMBERSHIP))

    # Requests UI + approve/reject/ignore is guarded by "add".
    pending_count = MembershipRequest.objects.count() if membership_can_add else 0

    return {
        "membership_can_add": membership_can_add,
        "membership_can_change": membership_can_change,
        "membership_can_delete": membership_can_delete,
        "membership_can_view": membership_can_view,
        "membership_requests_pending_count": pending_count,
    }


def organization_nav(request) -> dict[str, object]:
    if not hasattr(request, "user"):
        return {"has_organizations": False}

    user = request.user
    if not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return {"has_organizations": False}
    if not hasattr(user, "get_username"):
        return {"has_organizations": False}

    username = str(user.get_username() or "").strip()
    if not username:
        return {"has_organizations": False}

    return {
        "has_organizations": Organization.objects.filter(representatives__contains=[username]).exists(),
    }
