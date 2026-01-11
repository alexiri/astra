from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from core.agreements import (
    has_enabled_agreements,
    list_agreements_for_user,
    missing_required_agreements_for_user_in_group,
)
from core.backends import FreeIPAGroup, FreeIPAUser
from core.country_codes import country_code_status_from_user_data
from core.membership import get_valid_membership_type_codes_for_username, get_valid_memberships_for_username
from core.models import MembershipLog, MembershipRequest, MembershipType
from core.views_utils import _data_get, _first, _get_full_user, _normalize_str, _value_to_text

logger = logging.getLogger(__name__)


def _profile_context_for_user(
    request: HttpRequest,
    *,
    fu: FreeIPAUser,
    is_self: bool,
) -> dict[str, object]:
    data = fu._user_data

    fas_tz_name = _first(data, "fasTimezone", "")
    tz_name = ""
    tzinfo: ZoneInfo | None = None
    if fas_tz_name:
        try:
            tzinfo = ZoneInfo(fas_tz_name)
            tz_name = fas_tz_name
        except Exception:
            tz_name = ""
            tzinfo = None

    now_local = timezone.localtime(timezone.now(), timezone=tzinfo) if tzinfo else None

    groups_list = fu.groups_list

    # Only show FAS groups on the public profile page.
    # Using `FreeIPAGroup.all()` keeps this one cached call vs. per-group lookups.
    fas_groups = [g for g in FreeIPAGroup.all() if g.fas_group]
    fas_cns = {g.cn for g in fas_groups if g.cn}

    member_groups = {g for g in groups_list if g in fas_cns}

    sponsor_groups: set[str] = set()
    for g in fas_groups:
        cn = g.cn
        if not cn:
            continue
        if fu.username in g.sponsors:
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

    profile_avatar_user: object = fu

    membership_request_url = reverse("membership-request")
    valid_memberships = get_valid_memberships_for_username(fu.username)
    valid_membership_type_codes = get_valid_membership_type_codes_for_username(fu.username)

    membership_type_ids = {m.membership_type_id for m in valid_memberships}

    request_id_by_membership_type_id: dict[str, int] = {}
    if membership_type_ids:
        logs = (
            MembershipLog.objects.filter(
                target_username=fu.username,
                membership_type_id__in=membership_type_ids,
                membership_request__isnull=False,
                action=MembershipLog.Action.approved,
            )
            .only("membership_type_id", "membership_request_id", "created_at")
            .order_by("-created_at")
        )
        for log in logs:
            req_id = log.membership_request_id
            if req_id is None:
                continue
            request_id_by_membership_type_id.setdefault(log.membership_type_id, req_id)

        missing = membership_type_ids - request_id_by_membership_type_id.keys()
        if missing:
            approved_requests = (
                MembershipRequest.objects.filter(
                    requested_username=fu.username,
                    membership_type_id__in=missing,
                    status=MembershipRequest.Status.approved,
                )
                .only("pk", "membership_type_id", "decided_at", "requested_at")
                .order_by("-decided_at", "-requested_at")
            )
            for req in approved_requests:
                request_id_by_membership_type_id.setdefault(req.membership_type_id, req.pk)
    now = timezone.now()
    expiring_soon_by = now + datetime.timedelta(days=settings.MEMBERSHIP_EXPIRING_SOON_DAYS)

    memberships: list[dict[str, object]] = []
    for membership in valid_memberships:
        expires_at = membership.expires_at
        is_expiring_soon = bool(expires_at and expires_at <= expiring_soon_by)
        memberships.append(
            {
                "membership_type": membership.membership_type,
                "expires_at": expires_at,
                "is_expiring_soon": is_expiring_soon,
                "extend_url": f"{membership_request_url}?membership_type={membership.membership_type.code}",
                "request_id": request_id_by_membership_type_id.get(membership.membership_type_id),
            }
        )

    pending_requests_qs = list(
        MembershipRequest.objects.select_related("membership_type")
        .filter(requested_username=fu.username, status__in=[MembershipRequest.Status.pending, MembershipRequest.Status.on_hold])
        .order_by("requested_at")
    )

    pending_requests: list[dict[str, object]] = [
        {
            "membership_type": r.membership_type,
            "requested_at": r.requested_at,
            "request_id": r.pk,
            "status": r.status,
            "on_hold_at": r.on_hold_at,
        }
        for r in pending_requests_qs
    ]

    membership_action_required_requests: list[dict[str, object]] = [
        r for r in pending_requests if r.get("status") == MembershipRequest.Status.on_hold
    ]

    membership_can_request_any = MembershipType.objects.filter(enabled=True, isIndividual=True).exclude(
        code__in=valid_membership_type_codes
    ).exclude(group_cn="").exists()

    email_is_blacklisted = False
    if is_self and fu.email:
        # Local import: this app uses django-ses to track delivery-related blacklisting.
        from django_ses.models import BlacklistedEmail

        email_is_blacklisted = BlacklistedEmail.objects.filter(email__iexact=fu.email).exists()

    country_status = country_code_status_from_user_data(data)

    return {
        "fu": fu,
        "profile_avatar_user": profile_avatar_user,
        "is_self": is_self,
        "email_is_blacklisted": email_is_blacklisted,
        "country_code": country_status.code,
        "country_code_missing_or_invalid": not country_status.is_valid,
        "membership_request_url": membership_request_url,
        "membership_can_request_any": membership_can_request_any,
        "memberships": memberships,
        "membership_pending_requests": pending_requests,
        "membership_action_required_requests": membership_action_required_requests,
        "groups": groups,
        "agreements": agreements,
        "missing_agreements": missing_agreements,
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


def home(request: HttpRequest) -> HttpResponse:
    username = _normalize_str(request.user.get_username())
    if not username:
        messages.error(request, "Unable to determine your username.")
        return redirect("login")
    return redirect("user-profile", username=username)


def user_profile(request: HttpRequest, username: str) -> HttpResponse:
    username = _normalize_str(username)
    if not username:
        raise Http404("User not found")

    viewer_username = _normalize_str(request.user.get_username())
    logger.debug("User profile view: username=%s viewer=%s", username, viewer_username)

    fu = _get_full_user(username)
    if not fu:
        raise Http404("User not found")

    is_self = username == viewer_username

    context = _profile_context_for_user(request, fu=fu, is_self=is_self)
    return render(request, "core/user_profile.html", context)


def users(request: HttpRequest) -> HttpResponse:
    users_list = FreeIPAUser.all()
    q = _normalize_str(request.GET.get("q"))

    return render(
        request,
        "core/users.html",
        {
            "q": q,
            # Pass the full list; `core_user_grid.user_grid` handles filtering + pagination.
            "users": users_list,
        },
    )
