from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from core.views_utils import _get_full_user


@login_required(login_url="/login/")
def groups(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    groups_list = sorted(getattr(fu, "groups_list", []) or []) if fu else []
    return render(request, "core/groups.html", {"groups": groups_list})
