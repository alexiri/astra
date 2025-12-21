from __future__ import annotations

from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from core.backends import FreeIPAGroup


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

    return render(
        request,
        "core/group_detail.html",
        {
            "group": group,
            "q": q,
        },
    )
