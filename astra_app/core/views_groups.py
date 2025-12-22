from __future__ import annotations

from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from core.backends import FreeIPAFASAgreement, FreeIPAGroup, FreeIPAOperationFailed
from core.agreements import missing_required_agreements_for_user_in_group, required_agreements_for_group


@login_required(login_url="/login/")
def groups(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    page_number = (request.GET.get("page") or "").strip() or None

    def _cn(group: object) -> str:
        cn = getattr(group, "cn", None)
        return str(cn).strip() if cn is not None else ""

    def _sort_key(group: object) -> str:
        return _cn(group).lower()

    def _description(group: object) -> str:
        desc = getattr(group, "description", None)
        return str(desc).strip() if desc is not None else ""

    def _is_fas_group(group: object) -> bool:
        return bool(getattr(group, "fas_group", False))

    def _matches_query(group: object, query: str) -> bool:
        if not query:
            return True
        query_lower = query.lower()
        if query_lower in _sort_key(group):
            return True
        desc = _description(group).lower()
        return bool(desc) and query_lower in desc

    groups_list = FreeIPAGroup.all()
    groups_filtered = [g for g in groups_list if _is_fas_group(g) and _matches_query(g, q)]
    groups_sorted = sorted(groups_filtered, key=_sort_key)

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


@login_required(login_url="/login/")
def group_detail(request: HttpRequest, name: str) -> HttpResponse:
    cn = (name or "").strip()
    if not cn:
        raise Http404("Group not found")

    group = FreeIPAGroup.get(cn)
    if not group or not getattr(group, "fas_group", False):
        raise Http404("Group not found")

    q = (request.GET.get("q") or "").strip()

    username = (request.user.get_username() or "").strip()
    sponsors = {str(u).strip() for u in (getattr(group, "sponsors", []) or []) if str(u).strip()}
    members = {str(u).strip() for u in (getattr(group, "members", []) or []) if str(u).strip()}
    is_sponsor = bool(username) and username in sponsors
    is_member = bool(username) and username in members

    sponsors_list = sorted(sponsors, key=lambda s: s.lower())

    required_agreement_cns = required_agreements_for_group(cn)
    required_agreements: list[dict[str, object]] = []
    unsigned_usernames: set[str] = set()
    if required_agreement_cns:
        agreement_user_sets: dict[str, set[str]] = {}
        for agreement_cn in required_agreement_cns:
            agreement = FreeIPAFASAgreement.get(agreement_cn)
            users = {str(u).strip() for u in (getattr(agreement, "users", []) or []) if str(u).strip()} if agreement else set()
            agreement_user_sets[agreement_cn] = users

        for agreement_cn in required_agreement_cns:
            users_signed = agreement_user_sets.get(agreement_cn, set())
            required_agreements.append(
                {
                    "cn": agreement_cn,
                    "signed": bool(username) and username in users_signed,
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
        action = (request.POST.get("action") or "").strip().lower()

        if action == "leave":
            if not is_member:
                messages.info(request, "You are not a member of this group.")
                return redirect("group-detail", name)
            try:
                request.user.remove_from_group(cn)
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

            target = (request.POST.get("username") or "").strip()
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
            "q": q,
            "is_member": is_member,
            "is_sponsor": is_sponsor,
            "sponsors_list": sponsors_list,
            "required_agreements": required_agreements,
            "unsigned_usernames": sorted(unsigned_usernames, key=lambda s: s.lower()),
        },
    )
