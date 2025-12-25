from __future__ import annotations

import datetime
import logging
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import post_office.mail
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.backends import FreeIPAUser
from core.forms_membership import MembershipRejectForm, MembershipRequestForm, MembershipUpdateExpiryForm
from core.membership import get_valid_memberships_for_username, is_membership_committee_user
from core.membership_notifications import send_membership_notification
from core.models import MembershipLog, MembershipRequest, MembershipType
from core.views_utils import _first, _normalize_str

logger = logging.getLogger(__name__)


def _require_committee(request: HttpRequest) -> bool:
    if is_membership_committee_user(request.user):
        return True

    messages.error(request, "Only the membership committee can access that page.")
    return False


def _pagination_context(*, paginator: Paginator, page_obj, page_url_prefix: str) -> dict[str, object]:
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

    return {
        "paginator": paginator,
        "page_obj": page_obj,
        "is_paginated": paginator.num_pages > 1,
        "page_numbers": page_numbers,
        "show_first": show_first,
        "show_last": show_last,
        "page_url_prefix": page_url_prefix,
    }


def _previous_expires_at_for_extension(*, username: str, membership_type: MembershipType) -> datetime.datetime | None:
    """Return the previous expires_at to extend from, or None if approval should start now.

    We only consider the most recent state-changing log.
    If the latest action is termination, we do not extend from older expirations.
    """

    latest = (
        MembershipLog.objects.filter(
            target_username=username,
            membership_type=membership_type,
            action__in=[
                MembershipLog.Action.approved,
                MembershipLog.Action.expiry_changed,
                MembershipLog.Action.terminated,
            ],
        )
        .order_by("-created_at")
        .first()
    )
    if latest is None:
        return None
    if latest.action == MembershipLog.Action.terminated:
        return None
    return latest.expires_at


@login_required(login_url="/login/")
def membership_request(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    if not username:
        raise Http404("User not found")

    prefill_membership_type = str(request.GET.get("membership_type") or "").strip()

    fu = FreeIPAUser.get(username)
    if fu is None:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("user-profile", username=username)

    if request.method == "POST":
        form = MembershipRequestForm(request.POST, username=username)
        if form.is_valid():
            membership_type: MembershipType = form.cleaned_data["membership_type"]
            if not membership_type.enabled:
                form.add_error("membership_type", "That membership type is not available.")
            elif not membership_type.isIndividual:
                form.add_error("membership_type", "That membership type is not available.")
            elif not membership_type.group_cn:
                form.add_error("membership_type", "That membership type is not currently linked to a group.")
            else:
                MembershipRequest.objects.update_or_create(
                    requested_username=username,
                    defaults={"membership_type": membership_type},
                )
                MembershipLog.create_for_request(
                    actor_username=username,
                    target_username=username,
                    membership_type=membership_type,
                )

                if fu.email:
                    post_office.mail.send(
                        recipients=[fu.email],
                        sender=settings.DEFAULT_FROM_EMAIL,
                        template=settings.MEMBERSHIP_REQUEST_SUBMITTED_EMAIL_TEMPLATE_NAME,
                        context={
                            "username": username,
                            "membership_type": membership_type.name,
                            "membership_type_code": membership_type.code,
                        },
                    )

                messages.success(request, "Membership request submitted.")
                return redirect("user-profile", username=username)
    else:
            form = MembershipRequestForm(username=username, initial={"membership_type": prefill_membership_type})

    return render(
        request,
        "core/membership_request.html",
        {
            "form": form,
        },
    )


@login_required(login_url="/login/")
def membership_audit_log(request: HttpRequest) -> HttpResponse:
    if not _require_committee(request):
        return redirect("users")

    q = _normalize_str(request.GET.get("q"))
    username = _normalize_str(request.GET.get("username"))
    page_number = _normalize_str(request.GET.get("page")) or None

    logs = MembershipLog.objects.select_related("membership_type").all()
    if username:
        logs = logs.filter(target_username=username)
    if q:
        logs = logs.filter(
            Q(target_username__icontains=q)
            | Q(actor_username__icontains=q)
            | Q(membership_type__name__icontains=q)
            | Q(membership_type__code__icontains=q)
            | Q(action__icontains=q)
        )

    logs = logs.order_by("-created_at")
    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(page_number)
    query_params: dict[str, str] = {}
    if q:
        query_params["q"] = q
    if username:
        query_params["username"] = username
    qs = urlencode(query_params)
    page_url_prefix = f"?{qs}&page=" if qs else "?page="

    return render(
        request,
        "core/membership_audit_log.html",
        {
            "logs": page_obj.object_list,
            "filter_username": username,
            "filter_username_param": username,
            "q": q,
            **_pagination_context(paginator=paginator, page_obj=page_obj, page_url_prefix=page_url_prefix),
        },
    )


@login_required(login_url="/login/")
def membership_audit_log_user(request: HttpRequest, username: str) -> HttpResponse:
    if not _require_committee(request):
        return redirect("users")

    username = _normalize_str(username)
    q = _normalize_str(request.GET.get("q"))
    page_number = _normalize_str(request.GET.get("page")) or None

    logs = (
        MembershipLog.objects.select_related("membership_type")
        .filter(target_username=username)
        .order_by("-created_at")
    )
    if q:
        logs = logs.filter(
            Q(actor_username__icontains=q)
            | Q(membership_type__name__icontains=q)
            | Q(membership_type__code__icontains=q)
            | Q(action__icontains=q)
        )

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(page_number)
    query_params: dict[str, str] = {}
    if q:
        query_params["q"] = q
    qs = urlencode(query_params)
    page_url_prefix = f"?{qs}&page=" if qs else "?page="

    return render(
        request,
        "core/membership_audit_log.html",
        {
            "logs": page_obj.object_list,
            "filter_username": username,
            "filter_username_param": "",
            "q": q,
            **_pagination_context(paginator=paginator, page_obj=page_obj, page_url_prefix=page_url_prefix),
        },
    )


@login_required(login_url="/login/")
def membership_requests(request: HttpRequest) -> HttpResponse:
    if not _require_committee(request):
        return redirect("users")

    requests = MembershipRequest.objects.select_related("membership_type").all()

    request_rows: list[dict[str, object]] = []
    for r in requests:
        fu = FreeIPAUser.get(r.requested_username)
        full_name = fu.get_full_name() if fu is not None else ""
        request_rows.append({"r": r, "full_name": full_name})

    return render(
        request,
        "core/membership_requests.html",
        {
            "requests": requests,
            "request_rows": request_rows,
        },
    )


@login_required(login_url="/login/")
def membership_requests_bulk(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    if not _require_committee(request):
        return redirect("users")

    raw_action = _normalize_str(request.POST.get("bulk_action"))
    action = raw_action
    if action == "accept":
        action = "approve"

    selected_raw = request.POST.getlist("selected")
    selected_ids: list[int] = []
    for v in selected_raw:
        try:
            selected_ids.append(int(v))
        except (TypeError, ValueError):
            continue

    if not selected_ids:
        messages.error(request, "Select one or more requests first.")
        return redirect("membership-requests")

    if action not in {"approve", "reject", "ignore"}:
        messages.error(request, "Choose a valid bulk action.")
        return redirect("membership-requests")

    actor_username = request.user.get_username()
    reqs = list(
        MembershipRequest.objects.select_related("membership_type").filter(pk__in=selected_ids).order_by("pk")
    )
    if not reqs:
        messages.error(request, "No matching pending requests were found.")
        return redirect("membership-requests")

    approved = 0
    rejected = 0
    ignored = 0
    failures = 0

    for req in reqs:
        membership_type = req.membership_type

        if action == "approve":
            if not membership_type.group_cn:
                failures += 1
                continue

            target = FreeIPAUser.get(req.requested_username)
            if target is None:
                failures += 1
                continue

            try:
                target.add_to_group(group_name=membership_type.group_cn)
            except Exception:
                logger.exception("Bulk approve failed to add user to membership group")
                failures += 1
                continue

            MembershipLog.create_for_approval(
                actor_username=actor_username,
                target_username=req.requested_username,
                membership_type=membership_type,
                previous_expires_at=_previous_expires_at_for_extension(
                    username=req.requested_username,
                    membership_type=membership_type,
                ),
            )
            req.delete()
            approved += 1

            if target.email:
                post_office.mail.send(
                    recipients=[target.email],
                    sender=settings.DEFAULT_FROM_EMAIL,
                    template=settings.MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME,
                    context={
                        "username": target.username,
                        "membership_type": membership_type.name,
                        "membership_type_code": membership_type.code,
                        "group_cn": membership_type.group_cn,
                    },
                )

        elif action == "reject":
            target = FreeIPAUser.get(req.requested_username)
            reason = ""
            MembershipLog.create_for_rejection(
                actor_username=actor_username,
                target_username=req.requested_username,
                membership_type=membership_type,
                rejection_reason=reason,
            )
            req.delete()
            rejected += 1

            if target is not None and target.email:
                post_office.mail.send(
                    recipients=[target.email],
                    sender=settings.DEFAULT_FROM_EMAIL,
                    template=settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME,
                    context={
                        "username": target.username,
                        "membership_type": membership_type.name,
                        "membership_type_code": membership_type.code,
                        "rejection_reason": reason,
                    },
                )

        else:
            MembershipLog.create_for_ignore(
                actor_username=actor_username,
                target_username=req.requested_username,
                membership_type=membership_type,
            )
            req.delete()
            ignored += 1

    if approved:
        messages.success(request, f"Approved {approved} request(s).")
    if rejected:
        messages.success(request, f"Rejected {rejected} request(s).")
    if ignored:
        messages.success(request, f"Ignored {ignored} request(s).")
    if failures:
        messages.error(request, f"Failed to process {failures} request(s).")

    return redirect("membership-requests")


@login_required(login_url="/login/")
def membership_request_approve(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    if not _require_committee(request):
        return redirect("users")

    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type"), pk=pk)
    membership_type = req.membership_type
    if not membership_type.group_cn:
        messages.error(request, "This membership type is not linked to a group.")
        return redirect("membership-requests")

    target = FreeIPAUser.get(req.requested_username)
    if target is None:
        messages.error(request, "Unable to load the requested user from FreeIPA.")
        return redirect("membership-requests")

    try:
        target.add_to_group(group_name=membership_type.group_cn)
    except Exception:
        logger.exception("Failed to add user to membership group")
        messages.error(request, "Failed to add user to the group.")
        return redirect("membership-requests")

    MembershipLog.create_for_approval(
        actor_username=request.user.get_username(),
        target_username=req.requested_username,
        membership_type=membership_type,
        previous_expires_at=_previous_expires_at_for_extension(
            username=req.requested_username,
            membership_type=membership_type,
        ),
    )

    req.delete()

    if target.email:
        post_office.mail.send(
            recipients=[target.email],
            sender=settings.DEFAULT_FROM_EMAIL,
            template=settings.MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME,
            context={
                "username": target.username,
                "membership_type": membership_type.name,
                "membership_type_code": membership_type.code,
                "group_cn": membership_type.group_cn,
            },
        )

    messages.success(request, f"Approved membership request for {target.username}.")
    return redirect("membership-requests")


@login_required(login_url="/login/")
def membership_request_reject(request: HttpRequest, pk: int) -> HttpResponse:
    if not _require_committee(request):
        return redirect("users")

    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type"), pk=pk)
    membership_type = req.membership_type

    if request.method == "POST":
        form = MembershipRejectForm(request.POST)
        if form.is_valid():
            reason = str(form.cleaned_data.get("reason") or "").strip()
            target = FreeIPAUser.get(req.requested_username)

            MembershipLog.create_for_rejection(
                actor_username=request.user.get_username(),
                target_username=req.requested_username,
                membership_type=membership_type,
                rejection_reason=reason,
            )

            req.delete()

            if target is not None and target.email:
                post_office.mail.send(
                    recipients=[target.email],
                    sender=settings.DEFAULT_FROM_EMAIL,
                    template=settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME,
                    context={
                        "username": target.username,
                        "membership_type": membership_type.name,
                        "membership_type_code": membership_type.code,
                        "rejection_reason": reason,
                    },
                )

            messages.success(request, f"Rejected membership request for {req.requested_username}.")
            return redirect("membership-requests")
    else:
        form = MembershipRejectForm()

    return render(
        request,
        "core/membership_reject.html",
        {
            "req": req,
            "form": form,
        },
    )


@login_required(login_url="/login/")
def membership_request_ignore(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    if not _require_committee(request):
        return redirect("users")

    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type"), pk=pk)
    MembershipLog.create_for_ignore(
        actor_username=request.user.get_username(),
        target_username=req.requested_username,
        membership_type=req.membership_type,
    )
    req.delete()

    messages.success(request, f"Ignored membership request for {req.requested_username}.")
    return redirect("membership-requests")


@login_required(login_url="/login/")
def membership_set_expiry(request: HttpRequest, username: str, membership_type_code: str) -> HttpResponse:
    if not _require_committee(request):
        return redirect("users")

    username = _normalize_str(username)
    membership_type_code = _normalize_str(membership_type_code)
    if not username or not membership_type_code:
        raise Http404("Not found")

    membership_type = get_object_or_404(MembershipType, pk=membership_type_code)

    target_user = FreeIPAUser.get(username)
    tz_name_raw = str(_first(target_user._user_data, "fasTimezone", "") or "").strip() if target_user else ""
    tz_name = tz_name_raw or "UTC"
    try:
        ZoneInfo(tz_name)
    except Exception:
        tz_name = "UTC"
        ZoneInfo("UTC")

    valid_logs = get_valid_memberships_for_username(username)
    current_log = next((log for log in valid_logs if log.membership_type_id == membership_type.code), None)
    if current_log is None:
        messages.error(request, "That user does not currently have an active membership of that type.")
        return redirect("user-profile", username=username)

    if request.method == "POST":
        form = MembershipUpdateExpiryForm(request.POST)
        if form.is_valid():
            expires_on = form.cleaned_data["expires_on"]

            # The committee sets an expiration DATE. Interpret that as end-of-day UTC
            # (single source of truth), and rely on timezone conversion for display.
            expires_at = datetime.datetime.combine(expires_on, datetime.time(23, 59, 59), tzinfo=datetime.UTC)

            MembershipLog.create_for_expiry_change(
                actor_username=request.user.get_username(),
                target_username=username,
                membership_type=membership_type,
                expires_at=expires_at,
            )
            messages.success(request, "Membership expiration updated.")
            return redirect("user-profile", username=username)
    else:
        initial_date = current_log.expires_at.astimezone(datetime.UTC).date() if current_log.expires_at else None
        form = MembershipUpdateExpiryForm(initial={"expires_on": initial_date})

    return render(
        request,
        "core/membership_set_expiry.html",
        {
            "target_username": username,
            "membership_type": membership_type,
            "current_log": current_log,
            "target_timezone_name": tz_name,
            "form": form,
        },
    )


@login_required(login_url="/login/")
def membership_terminate(request: HttpRequest, username: str, membership_type_code: str) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    if not _require_committee(request):
        return redirect("users")

    username = _normalize_str(username)
    membership_type_code = _normalize_str(membership_type_code)
    if not username or not membership_type_code:
        raise Http404("Not found")

    membership_type = get_object_or_404(MembershipType, pk=membership_type_code)

    target = FreeIPAUser.get(username)
    if target is None:
        messages.error(request, "Unable to load the requested user from FreeIPA.")
        return redirect("user-profile", username=username)

    valid_logs = get_valid_memberships_for_username(username)
    current_log = next((log for log in valid_logs if log.membership_type_id == membership_type.code), None)
    if current_log is None:
        messages.error(request, "That user does not currently have an active membership of that type.")
        return redirect("user-profile", username=username)

    if membership_type.group_cn:
        try:
            target.remove_from_group(group_name=membership_type.group_cn)
        except Exception:
            logger.exception("Failed to remove user from membership group")
            messages.error(request, "Failed to remove the user from the group.")
            return redirect("user-profile", username=username)

    MembershipLog.create_for_termination(
        actor_username=request.user.get_username(),
        target_username=username,
        membership_type=membership_type,
    )

    if target.email:
        tz_name = str(_first(target._user_data, "fasTimezone", "") or "").strip() or "UTC"
        send_membership_notification(
            recipient_email=target.email,
            username=username,
            membership_type=membership_type,
            template_name=settings.MEMBERSHIP_EXPIRED_EMAIL_TEMPLATE_NAME,
            expires_at=datetime.datetime.now(tz=datetime.UTC),
            base_url=request.build_absolute_uri("/"),
            tz_name=tz_name,
        )

    messages.success(request, "Membership terminated.")
    return redirect("user-profile", username=username)
