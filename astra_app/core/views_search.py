from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse

from core.backends import FreeIPAGroup, FreeIPAUser


def _user_full_name(user: object) -> str:
    get_full_name = getattr(user, "get_full_name", None)
    if callable(get_full_name):
        try:
            return str(get_full_name()).strip()
        except Exception:
            return ""
    return ""


@login_required(login_url="/login/")
def global_search(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"users": [], "groups": []})

    q_lower = q.lower()

    users_out: list[dict[str, str]] = []
    for u in FreeIPAUser.all():
        username = getattr(u, "username", "")
        if not isinstance(username, str):
            continue
        username_norm = username.strip()
        if not username_norm:
            continue

        full_name = _user_full_name(u)
        if q_lower not in username_norm.lower() and (not full_name or q_lower not in full_name.lower()):
            continue

        users_out.append({"username": username_norm, "full_name": full_name})
        if len(users_out) >= 7:
            break

    groups_out: list[dict[str, str]] = []
    for g in FreeIPAGroup.all():
        if not getattr(g, "fas_group", False):
            continue
        cn = getattr(g, "cn", "")
        if not isinstance(cn, str):
            continue
        cn_norm = cn.strip()
        if not cn_norm:
            continue

        desc = getattr(g, "description", "")
        desc_norm = desc.strip() if isinstance(desc, str) else ""

        if q_lower not in cn_norm.lower() and (not desc_norm or q_lower not in desc_norm.lower()):
            continue

        groups_out.append({"cn": cn_norm, "description": desc_norm})
        if len(groups_out) >= 7:
            break

    # Keep output deterministic for tests/UI.
    users_out.sort(key=lambda x: x["username"].lower())
    groups_out.sort(key=lambda x: x["cn"].lower())

    return JsonResponse({"users": users_out, "groups": groups_out})
