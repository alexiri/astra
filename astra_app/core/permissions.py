from __future__ import annotations

ASTRA_ADD_MEMBERSHIP = "astra.add_membership"
ASTRA_CHANGE_MEMBERSHIP = "astra.change_membership"
ASTRA_DELETE_MEMBERSHIP = "astra.delete_membership"
ASTRA_VIEW_MEMBERSHIP = "astra.view_membership"

MEMBERSHIP_PERMISSIONS: frozenset[str] = frozenset(
    {
        ASTRA_ADD_MEMBERSHIP,
        ASTRA_CHANGE_MEMBERSHIP,
        ASTRA_DELETE_MEMBERSHIP,
        ASTRA_VIEW_MEMBERSHIP,
    }
)


def has_any_membership_permission(user: object) -> bool:
    if not hasattr(user, "has_perm"):
        return False

    for perm in MEMBERSHIP_PERMISSIONS:
        try:
            if user.has_perm(perm):
                return True
        except Exception:
            # Be defensive: template context processors may be invoked with
            # partial stubs or AnonymousUser-like objects.
            continue

    return False
