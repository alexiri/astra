from __future__ import annotations

from typing import cast

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from core.agreements import missing_required_agreements_for_user_in_group, required_agreements_for_group
from core.backends import FreeIPAFASAgreement, FreeIPAGroup, FreeIPAOperationFailed, FreeIPAUser
from core.views_utils import _normalize_str


def groups(request: HttpRequest) -> HttpResponse:
    q = _normalize_str(request.GET.get("q"))
    page_number = _normalize_str(request.GET.get("page")) or None

    def _sort_key(group: FreeIPAGroup) -> str:
        return group.cn.lower()

    def _matches_query(group: FreeIPAGroup, query: str) -> bool:
        if not query:
            return True
        query_lower = query.lower()
        if query_lower in group.cn.lower():
            return True
        desc = (group.description or "").lower()
        return query_lower in desc

    groups_list = FreeIPAGroup.all()
    groups_filtered = [g for g in groups_list if g.fas_group and _matches_query(g, q)]
    groups_sorted = sorted(groups_filtered, key=_sort_key)

    for g in groups_sorted:
        member_count = 0
        if hasattr(g, "member_count_recursive"):
            try:
                fn = getattr(g, "member_count_recursive")
                member_count = int(fn() if callable(fn) else fn)
            except Exception:
                member_count = 0
        else:
            try:
                member_count = len(getattr(g, "members", []) or [])
            except Exception:
                member_count = 0
        setattr(g, "member_count", member_count)

    paginator = Paginator(groups_sorted, 30)
    page_obj = paginator.get_page(page_number)

    total_pages = paginator.num_pages
    current_page = page_obj.number
    if total_pages <= 10:
        page_numbers = list(range(1, total_pages + 1))
        show_first = False
        show_last = False
    else:
        start = max(1, current_page - 2)
        end = min(total_pages, current_page + 2)
        page_numbers = list(range(start, end + 1))
        show_first = 1 not in page_numbers
        show_last = total_pages not in page_numbers

    return render(
        request,
        "core/groups.html",
        {
            "q": q,
            "paginator": paginator,
            "page_obj": page_obj,
            "is_paginated": paginator.num_pages > 1,
            "page_numbers": page_numbers,
            "show_first": show_first,
            "show_last": show_last,
            "groups": page_obj.object_list,
        },
    )


def group_detail(request: HttpRequest, name: str) -> HttpResponse:
    cn = _normalize_str(name)
    if not cn:
        raise Http404("Group not found")

    group = FreeIPAGroup.get(cn)
    if not group or not group.fas_group:
        raise Http404("Group not found")

    q = _normalize_str(request.GET.get("q"))

    member_count = 0
    if hasattr(group, "member_count_recursive"):
        try:
            fn = getattr(group, "member_count_recursive")
            member_count = int(fn() if callable(fn) else fn)
        except Exception:
            member_count = 0
    else:
        try:
            member_count = len(getattr(group, "members", []) or [])
        except Exception:
            member_count = 0

    username = _normalize_str(request.user.get_username())
    sponsors = set(group.sponsors)
    sponsor_groups = set(getattr(group, "sponsor_groups", []) or [])
    members = set(group.members)
    user_groups: set[str] = set()
    if isinstance(request.user, FreeIPAUser):
        user_groups = set(request.user.groups_list)

    sponsor_groups_lower = {g.lower() for g in sponsor_groups}
    user_groups_lower = {g.lower() for g in user_groups}
    is_sponsor = (username in sponsors) or bool(sponsor_groups_lower & user_groups_lower)
    is_member = username in members

    sponsor_groups_list = sorted(sponsor_groups, key=lambda s: s.lower())
    sponsors_list = sorted(sponsors, key=lambda s: s.lower())

    required_agreement_cns = required_agreements_for_group(cn)
    required_agreements: list[dict[str, object]] = []
    unsigned_usernames: set[str] = set()
    if required_agreement_cns:
        agreement_user_sets: dict[str, set[str]] = {}
        for agreement_cn in required_agreement_cns:
            agreement = FreeIPAFASAgreement.get(agreement_cn)
            users = set(agreement.users) if agreement else set()
            agreement_user_sets[agreement_cn] = users

        for agreement_cn in required_agreement_cns:
            users_signed = agreement_user_sets.get(agreement_cn, set())
            required_agreements.append(
                {
                    "cn": agreement_cn,
                    "signed": username in users_signed,
                    "detail_url": reverse("settings-agreement-detail", kwargs={"cn": agreement_cn}),
                    "list_url": reverse("settings-agreements"),
                }
            )

        for u in sorted(members | sponsors, key=lambda s: s.lower()):
            for agreement_cn in required_agreement_cns:
                if u not in agreement_user_sets.get(agreement_cn, set()):
                    unsigned_usernames.add(u)
                    break

    if request.method == "POST":
        action = _normalize_str(request.POST.get("action")).lower()

        if action == "leave":
            if not is_member:
                messages.info(request, "You are not a member of this group.")
                return redirect("group-detail", name)
            try:
                cast(FreeIPAUser, request.user).remove_from_group(cn)
                messages.success(request, "You have left the group.")
            except Exception:
                messages.error(request, "Failed to leave group due to an internal error.")
            return redirect("group-detail", name)

        if action == "stop_sponsoring":
            if not is_sponsor:
                messages.info(request, "You are not a sponsor of this group.")
                return redirect("group-detail", name)
            try:
                group.remove_sponsor(username)
                messages.success(request, "You are no longer a sponsor of this group.")
            except Exception:
                messages.error(request, "Failed to update sponsor status due to an internal error.")
            return redirect("group-detail", name)

        if action in {"add_member", "remove_member"}:
            if not is_sponsor:
                messages.error(request, "Only sponsors can manage group members.")
                return redirect("group-detail", name)

            target = _normalize_str(request.POST.get("username"))
            if not target:
                messages.error(request, "Please provide a username.")
                return redirect("group-detail", name)

            if target == username and action == "add_member":
                messages.error(request, "You can't add yourself to a group.")
                return redirect("group-detail", name)

            if action == "add_member":
                missing = missing_required_agreements_for_user_in_group(target, cn)
                if missing:
                    messages.error(
                        request,
                        "User must sign required agreement(s) before joining: " + ", ".join(missing),
                    )
                    return redirect("group-detail", name)
                try:
                    group.add_member(target)
                    messages.success(request, f"Added {target} to the group.")
                except FreeIPAOperationFailed as e:
                    messages.error(request, str(e))
                except Exception:
                    messages.error(request, "Failed to add member due to an internal error.")
                return redirect("group-detail", name)

            if action == "remove_member":
                try:
                    group.remove_member(target)
                    messages.success(request, f"Removed {target} from the group.")
                except FreeIPAOperationFailed as e:
                    messages.error(request, str(e))
                except Exception:
                    messages.error(request, "Failed to remove member due to an internal error.")
                return redirect("group-detail", name)

    return render(
        request,
        "core/group_detail.html",
        {
            "group": group,
            "member_count": member_count,
            "q": q,
            "is_member": is_member,
            "is_sponsor": is_sponsor,
            "sponsors_list": sponsors_list,
            "sponsor_groups_list": sponsor_groups_list,
            "required_agreements": required_agreements,
            "unsigned_usernames": sorted(unsigned_usernames, key=lambda s: s.lower()),
        },
    )
