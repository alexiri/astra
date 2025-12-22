from __future__ import annotations

import logging
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from zoneinfo import ZoneInfo

from core.backends import FreeIPAGroup, FreeIPAUser
from core.agreements import has_enabled_agreements, list_agreements_for_user, missing_required_agreements_for_user_in_group
from core.views_utils import _data_get, _first, _get_full_user, _normalize_str, _value_to_text


logger = logging.getLogger(__name__)


def _profile_context_for_user(
    request: HttpRequest,
    *,
    fu: FreeIPAUser,
    is_self: bool,
) -> dict[str, object]:
    data = getattr(fu, "_user_data", {})

    tz_name = timezone.get_current_timezone_name()
    fas_tz_name = _first(data, "fasTimezone", "")
    tzinfo = timezone.get_current_timezone()
    if fas_tz_name:
        try:
            tzinfo = ZoneInfo(fas_tz_name)
            tz_name = fas_tz_name
        except Exception:
            pass

    now_local = timezone.localtime(timezone.now(), timezone=tzinfo)

    groups_raw = getattr(fu, "groups_list", []) or []
    if isinstance(groups_raw, str):
        groups_raw = [groups_raw]
    groups_list = [str(g).strip() for g in groups_raw if str(g).strip()]

    # Only show FAS groups on the public profile page.
    # Using `FreeIPAGroup.all()` keeps this one cached call vs. per-group lookups.
    fas_groups = [g for g in (FreeIPAGroup.all() or []) if getattr(g, "fas_group", False)]
    fas_cns = {str(getattr(g, "cn", "")).strip().lower() for g in fas_groups if getattr(g, "cn", None)}

    member_groups = {g for g in groups_list if g.lower() in fas_cns}

    sponsor_groups: set[str] = set()
    for g in fas_groups:
        cn = str(getattr(g, "cn", "") or "").strip()
        if not cn:
            continue
        sponsors = {str(u).strip() for u in (getattr(g, "sponsors", []) or []) if str(u).strip()}
        if fu.username in sponsors:
            sponsor_groups.add(cn)

    visible_groups = sorted(member_groups | sponsor_groups, key=str.lower)
    groups = [
        {
            "cn": cn,
            "role": "Sponsor" if cn in sponsor_groups else "Member",
        }
        for cn in visible_groups
    ]

    show_agreements = has_enabled_agreements()
    if show_agreements:
        agreements = [
            a.cn
            for a in list_agreements_for_user(
                fu.username,
                user_groups=groups_list,
                include_disabled=False,
                applicable_only=False,
            )
            if a.signed
        ]
        agreements = sorted(agreements, key=str.lower)

        missing_required: dict[str, set[str]] = {}
        for group_cn in sorted(member_groups, key=str.lower):
            for agreement_cn in missing_required_agreements_for_user_in_group(fu.username, group_cn):
                missing_required.setdefault(agreement_cn, set()).add(group_cn)

        missing_agreements = [
            {
                "cn": agreement_cn,
                "required_by": sorted(required_by, key=str.lower),
                "settings_url": reverse("settings-agreement-detail", kwargs={"cn": agreement_cn})
                if is_self
                else None,
            }
            for agreement_cn, required_by in sorted(missing_required.items(), key=lambda kv: kv[0].lower())
        ]
    else:
        agreements = []
        missing_agreements = []

    def _as_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if _normalize_str(v)]
        if isinstance(value, str):
            s = value.strip()
            return [s] if s else []
        return []

    irc_nicks = _as_list(_data_get(data, "fasIRCNick", []))
    website_urls = _as_list(_data_get(data, "fasWebsiteUrl", []))
    rss_urls = _as_list(_data_get(data, "fasRssUrl", []))
    gpg_keys = _as_list(_data_get(data, "fasGPGKeyId", []))
    ssh_keys = _as_list(_data_get(data, "ipasshpubkey", []))

    # django-avatar expects either a Django user model or an authenticated object
    # with get_username(). Some tests (and some call sites) use lightweight
    # user stubs for `fu` that don't implement that method.
    profile_avatar_user: object = fu
    if not getattr(fu, "is_authenticated", False) or not hasattr(fu, "get_username"):
        safe_username = getattr(fu, "username", "") or ""
        profile_avatar_user = SimpleNamespace(
            is_authenticated=True,
            get_username=lambda: safe_username,
            username=safe_username,
            email=getattr(fu, "email", "") or "",
        )

    return {
        "fu": fu,
        "profile_avatar_user": profile_avatar_user,
        "is_self": is_self,
        "groups": groups,
        "agreements": agreements,
        "missing_agreements": missing_agreements,
        "timezone": tz_name,
        "timezone_name": tz_name,
        "current_time": now_local,
        "pronouns": _value_to_text(_data_get(data, "fasPronoun", "")),
        "locale": _first(data, "fasLocale", "") or "",
        "irc_nicks": irc_nicks,
        "website_urls": website_urls,
        "rss_urls": rss_urls,
        "rhbz_email": _first(data, "fasRHBZEmail", "") or "",
        "github_username": _first(data, "fasGitHubUsername", "") or "",
        "gitlab_username": _first(data, "fasGitLabUsername", "") or "",
        "gpg_keys": gpg_keys,
        "ssh_keys": ssh_keys,
    }


@login_required(login_url="/login/")
def home(request: HttpRequest) -> HttpResponse:
    username = (request.user.get_username() or "").strip()
    if not username:
        messages.error(request, "Unable to determine your username.")
        return redirect("login")
    return redirect("user-profile", username=username)


@login_required(login_url="/login/")
def user_profile(request: HttpRequest, username: str) -> HttpResponse:
    username = (username or "").strip()
    if not username:
        raise Http404("User not found")

    viewer_username = (request.user.get_username() or "").strip()
    logger.debug("User profile view: username=%s viewer=%s", username, viewer_username)

    fu = _get_full_user(username)
    if not fu:
        raise Http404("User not found")

    context = _profile_context_for_user(request, fu=fu, is_self=(username == viewer_username))
    return render(request, "core/user_profile.html", context)


@login_required(login_url="/login/")
def users(request: HttpRequest) -> HttpResponse:
    users_list = FreeIPAUser.all()
    q = (request.GET.get("q") or "").strip()

    return render(
        request,
        "core/users.html",
        {
            "q": q,
            # Pass the full list; `core_user_grid.user_grid` handles filtering + pagination.
            "users": users_list,
        },
    )
