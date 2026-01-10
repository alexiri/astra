from __future__ import annotations

import datetime
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from core.backends import FreeIPAUser
from core.email_context import organization_sponsor_email_context
from core.forms_membership import MembershipRejectForm, MembershipRequestForm, MembershipUpdateExpiryForm
from core.membership import get_valid_memberships_for_username
from core.membership_notes import add_note
from core.membership_request_workflow import (
    approve_membership_request,
    ignore_membership_request,
    record_membership_request_created,
    reject_membership_request,
)
from core.models import (
    MembershipLog,
    MembershipRequest,
    MembershipType,
    Organization,
    OrganizationSponsorship,
)
from core.permissions import (
    ASTRA_ADD_MEMBERSHIP,
    ASTRA_CHANGE_MEMBERSHIP,
    ASTRA_DELETE_MEMBERSHIP,
    ASTRA_VIEW_MEMBERSHIP,
)
from core.views_utils import _normalize_str

logger = logging.getLogger(__name__)


def _membership_request_target_label(membership_request: MembershipRequest) -> str:
    if membership_request.requested_username:
        return membership_request.requested_username

    org = membership_request.requested_organization
    return org.name if org is not None else (membership_request.requested_organization_name or "organization")


def _send_mail_url(*, to_type: str, to: str, template_name: str, extra_context: dict[str, str]) -> str:
    query_params = {
        "type": to_type,
        "to": to,
        "template": template_name,
        **extra_context,
    }
    send_mail_url = reverse("send-mail")
    return f"{send_mail_url}?{urlencode(query_params)}"


def _custom_email_recipient_for_request(membership_request: MembershipRequest) -> tuple[str, str] | None:
    """Return (Send Mail type, to) for a membership-request custom email.

    For org requests, prefer the representative when it resolves
    to a FreeIPA user with an email address; otherwise fall back to
    Organization.primary_contact_email().
    """

    if membership_request.requested_username:
        return ("users", membership_request.requested_username)

    org = membership_request.requested_organization
    if org is None:
        return None

    representative_username = org.representative
    if representative_username:
        representative = FreeIPAUser.get(representative_username)
        if representative is not None and representative.email:
            return ("users", representative_username)

    org_email = org.primary_contact_email()
    if org_email:
        return ("manual", org_email)

    return None


def _custom_email_redirect(
    *,
    request: HttpRequest,
    membership_request: MembershipRequest,
    template_name: str,
    extra_context: dict[str, str],
    redirect_to: str,
) -> HttpResponse:
    recipient = _custom_email_recipient_for_request(membership_request)
    if recipient is None:
        messages.error(request, "No recipient is available for a custom email.")
        return redirect(redirect_to)

    to_type, to = recipient
    merged_context = dict(extra_context)
    merged_context.setdefault("membership_request_id", str(membership_request.pk))
    return redirect(
        _send_mail_url(
            to_type=to_type,
            to=to,
            template_name=template_name,
            extra_context=merged_context,
        )
    )


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
            elif not membership_type.isIndividual and membership_type.code != "mirror":
                form.add_error("membership_type", "That membership type is not available.")
            elif not membership_type.group_cn:
                form.add_error("membership_type", "That membership type is not currently linked to a group.")
            else:
                existing = (
                    MembershipRequest.objects.filter(
                        requested_username=username,
                        membership_type=membership_type,
                        status=MembershipRequest.Status.pending,
                    )
                    .order_by("-requested_at")
                    .first()
                )
                if existing is not None:
                    messages.info(request, "You already have a pending request of that type.")
                    return redirect("user-profile", username=username)

                responses = form.responses()

                mr = MembershipRequest.objects.create(
                    requested_username=username,
                    membership_type=membership_type,
                    status=MembershipRequest.Status.pending,
                    responses=responses,
                )
                record_membership_request_created(
                    membership_request=mr,
                    actor_username=username,
                    send_submitted_email=True,
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


@permission_required(ASTRA_VIEW_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_audit_log(request: HttpRequest) -> HttpResponse:
    q = _normalize_str(request.GET.get("q"))
    username = _normalize_str(request.GET.get("username"))
    raw_org = _normalize_str(request.GET.get("organization"))
    organization_id = int(raw_org) if raw_org.isdigit() else None
    page_number = _normalize_str(request.GET.get("page")) or None

    logs = MembershipLog.objects.select_related(
        "membership_type",
        "membership_request",
        "membership_request__membership_type",
        "target_organization",
    ).all()
    if username:
        logs = logs.filter(target_username=username)
    if organization_id is not None:
        logs = logs.filter(Q(target_organization_id=organization_id) | Q(target_organization_code=str(organization_id)))
    if q:
        logs = logs.filter(
            Q(target_username__icontains=q)
            | Q(target_organization__name__icontains=q)
            | Q(target_organization_code__icontains=q)
            | Q(target_organization_name__icontains=q)
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
    if organization_id is not None:
        query_params["organization"] = str(organization_id)
    qs = urlencode(query_params)
    page_url_prefix = f"?{qs}&page=" if qs else "?page="

    return render(
        request,
        "core/membership_audit_log.html",
        {
            "logs": page_obj.object_list,
            "filter_username": username,
            "filter_username_param": username,
            "filter_organization": str(organization_id) if organization_id is not None else "",
            "filter_organization_param": str(organization_id) if organization_id is not None else "",
            "q": q,
            **_pagination_context(paginator=paginator, page_obj=page_obj, page_url_prefix=page_url_prefix),
        },
    )


@permission_required(ASTRA_VIEW_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_audit_log_organization(request: HttpRequest, organization_id: int) -> HttpResponse:
    q = _normalize_str(request.GET.get("q"))
    page_number = _normalize_str(request.GET.get("page")) or None

    logs = (
        MembershipLog.objects.select_related(
            "membership_type",
            "membership_request",
            "membership_request__membership_type",
            "target_organization",
        )
        .filter(Q(target_organization_id=organization_id) | Q(target_organization_code=str(organization_id)))
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
            "filter_username": "",
            "filter_username_param": "",
            "filter_organization": str(organization_id),
            "filter_organization_param": str(organization_id),
            "q": q,
            **_pagination_context(paginator=paginator, page_obj=page_obj, page_url_prefix=page_url_prefix),
        },
    )


@permission_required(ASTRA_VIEW_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_audit_log_user(request: HttpRequest, username: str) -> HttpResponse:
    username = _normalize_str(username)
    q = _normalize_str(request.GET.get("q"))
    page_number = _normalize_str(request.GET.get("page")) or None

    logs = (
        MembershipLog.objects.select_related(
            "membership_type",
            "membership_request",
            "membership_request__membership_type",
        )
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


@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_requests(request: HttpRequest) -> HttpResponse:
    requests = (
        MembershipRequest.objects.select_related("membership_type", "requested_organization")
        .filter(status=MembershipRequest.Status.pending)
        .order_by("requested_at")
    )

    request_rows: list[dict[str, object]] = []
    for r in requests:
        if r.requested_username == "":
            org = r.requested_organization
            request_rows.append(
                {
                    "r": r,
                    "organization": org,
                    "organization_code": r.requested_organization_code,
                    "organization_name": r.requested_organization_name,
                }
            )
        else:
            fu = FreeIPAUser.get(r.requested_username)
            full_name = fu.full_name if fu is not None else ""
            request_rows.append(
                {
                    "r": r,
                    "full_name": full_name,
                    "user_deleted": fu is None,
                }
            )

    return render(
        request,
        "core/membership_requests.html",
        {
            "requests": requests,
            "request_rows": request_rows,
        },
    )


@permission_required(ASTRA_VIEW_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_detail(request: HttpRequest, pk: int) -> HttpResponse:
    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type", "requested_organization"), pk=pk)

    target_user = None
    target_full_name = ""
    target_user_deleted = False
    if req.requested_username:
        target_user = FreeIPAUser.get(req.requested_username)
        if target_user is None:
            target_user_deleted = True
        else:
            target_full_name = target_user.full_name

    return render(
        request,
        "core/membership_request_detail.html",
        {
            "req": req,
            "target_user": target_user,
            "target_full_name": target_full_name,
            "target_user_deleted": target_user_deleted,
        },
    )


@permission_required(ASTRA_VIEW_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_note_add(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    can_edit = any(
        request.user.has_perm(p)
        for p in (
            ASTRA_ADD_MEMBERSHIP,
            ASTRA_CHANGE_MEMBERSHIP,
            ASTRA_DELETE_MEMBERSHIP,
        )
    )
    if not can_edit:
        raise PermissionDenied

    req = get_object_or_404(
        MembershipRequest.objects.select_related("membership_type", "requested_organization"),
        pk=pk,
    )

    next_url = str(request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_to = next_url
    else:
        redirect_to = reverse("membership-request-detail", args=[req.pk])

    actor_username = str(request.user.get_username() or "").strip()
    note_action = _normalize_str(request.POST.get("note_action")).lower()
    message = str(request.POST.get("message") or "")

    is_ajax = str(request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest"

    try:
        user_message = ""
        if note_action == "vote_approve":
            add_note(
                membership_request=req,
                username=actor_username,
                content=message,
                action={"type": "vote", "value": "approve"},
            )
            user_message = "Recorded approve vote."
        elif note_action == "vote_disapprove":
            add_note(
                membership_request=req,
                username=actor_username,
                content=message,
                action={"type": "vote", "value": "disapprove"},
            )
            user_message = "Recorded disapprove vote."
        else:
            add_note(
                membership_request=req,
                username=actor_username,
                content=message,
                action=None,
            )
            user_message = "Note added."

        if is_ajax:
            from core.templatetags.core_membership_notes import membership_notes

            notes_context = membership_notes(
                {
                    "request": request,
                    "membership_can_add": request.user.has_perm(ASTRA_ADD_MEMBERSHIP),
                    "membership_can_change": request.user.has_perm(ASTRA_CHANGE_MEMBERSHIP),
                    "membership_can_delete": request.user.has_perm(ASTRA_DELETE_MEMBERSHIP),
                },
                req,
                compact=False,
                next_url=redirect_to,
            )
            html = render_to_string("core/_membership_notes.html", notes_context, request=request)
            return JsonResponse({"ok": True, "html": html, "message": user_message})

        messages.success(request, user_message)
        return redirect(redirect_to)
    except Exception:
        logger.exception("Failed to add membership note request_pk=%s actor=%s", req.pk, actor_username)
        if is_ajax:
            return JsonResponse({"ok": False, "error": "Failed to add note."}, status=500)

        messages.error(request, "Failed to add note.")
        return redirect(redirect_to)

@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_requests_bulk(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

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
        MembershipRequest.objects.select_related("membership_type", "requested_organization")
        .filter(pk__in=selected_ids)
        .order_by("pk")
    )
    if not reqs:
        messages.error(request, "No matching pending requests were found.")
        return redirect("membership-requests")

    approved = 0
    rejected = 0
    ignored = 0
    failures = 0

    for req in reqs:
        if action == "approve":
            try:
                approve_membership_request(
                    membership_request=req,
                    actor_username=actor_username,
                    send_approved_email=True,
                )
            except Exception:
                logger.exception("Bulk approve failed for membership request pk=%s", req.pk)
                failures += 1
                continue

            approved += 1

        elif action == "reject":
            try:
                _, email_error = reject_membership_request(
                    membership_request=req,
                    actor_username=actor_username,
                    rejection_reason="",
                    send_rejected_email=True,
                )
                if email_error is not None:
                    failures += 1
            except Exception:
                logger.exception("Bulk reject failed for membership request pk=%s", req.pk)
                failures += 1
                continue

            rejected += 1

        else:
            try:
                ignore_membership_request(
                    membership_request=req,
                    actor_username=actor_username,
                )
            except Exception:
                logger.exception("Bulk ignore failed for membership request pk=%s", req.pk)
                failures += 1
                continue

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


@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_approve(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type", "requested_organization"), pk=pk)
    membership_type = req.membership_type

    custom_email = bool(str(request.POST.get("custom_email") or "").strip())

    next_url = str(request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_to = next_url
    else:
        referer = str(request.META.get("HTTP_REFERER") or "").strip()
        redirect_to = referer or reverse("membership-requests")
        if redirect_to and not url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_to = reverse("membership-requests")

    try:
        approve_membership_request(
            membership_request=req,
            actor_username=request.user.get_username(),
            send_approved_email=not custom_email,
            approved_email_template_name=None,
        )
    except Exception:
        logger.exception("Failed to approve membership request pk=%s", req.pk)
        messages.error(request, "Failed to approve the request.")
        return redirect(redirect_to)

    target_label = _membership_request_target_label(req)

    template_name = settings.MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME
    if membership_type.acceptance_template_id is not None:
        template_name = membership_type.acceptance_template.name

    messages.success(request, f"Approved request for {target_label}.")

    if req.requested_username == "":
        org = req.requested_organization

        if custom_email:
            return _custom_email_redirect(
                request=request,
                membership_request=req,
                template_name=template_name,
                extra_context={
                    "organization_name": org.name if org is not None else (req.requested_organization_name or ""),
                    **(organization_sponsor_email_context(organization=org) if org is not None else {}),
                    "membership_type": membership_type.name,
                    "membership_type_code": membership_type.code,
                },
                redirect_to=redirect_to,
            )
        return redirect(redirect_to)

    if custom_email:
        return _custom_email_redirect(
            request=request,
            membership_request=req,
            template_name=template_name,
            extra_context={
                "membership_type": membership_type.name,
                "membership_type_code": membership_type.code,
                "group_cn": membership_type.group_cn,
            },
            redirect_to=redirect_to,
        )
    return redirect(redirect_to)


@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_reject(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type", "requested_organization"), pk=pk)
    membership_type = req.membership_type

    custom_email = bool(str(request.POST.get("custom_email") or "").strip())

    next_url = str(request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_to = next_url
    else:
        referer = str(request.META.get("HTTP_REFERER") or "").strip()
        redirect_to = referer or reverse("membership-requests")
        if redirect_to and not url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_to = reverse("membership-requests")

    form = MembershipRejectForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid rejection reason.")
        return redirect(redirect_to)

    reason = str(form.cleaned_data.get("reason") or "").strip()

    _, email_error = reject_membership_request(
        membership_request=req,
        actor_username=request.user.get_username(),
        rejection_reason=reason,
        send_rejected_email=not custom_email,
    )

    target_label = _membership_request_target_label(req)
    messages.success(request, f"Rejected request for {target_label}.")

    if email_error is not None:
        messages.error(request, "Request was rejected, but the email could not be sent.")

    if req.requested_username == "":
        org = req.requested_organization

        if custom_email:
            return _custom_email_redirect(
                request=request,
                membership_request=req,
                template_name=settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME,
                extra_context={
                    "organization_name": org.name if org is not None else (req.requested_organization_name or ""),
                    **(organization_sponsor_email_context(organization=org) if org is not None else {}),
                    "membership_type": membership_type.name,
                    "membership_type_code": membership_type.code,
                    "rejection_reason": reason,
                },
                redirect_to=redirect_to,
            )
        return redirect(redirect_to)

    if custom_email:
        return _custom_email_redirect(
            request=request,
            membership_request=req,
            template_name=settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME,
            extra_context={
                "membership_type": membership_type.name,
                "membership_type_code": membership_type.code,
                "rejection_reason": reason,
            },
            redirect_to=redirect_to,
        )
    return redirect(redirect_to)


@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_ignore(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type", "requested_organization"), pk=pk)

    next_url = str(request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_to = next_url
    else:
        referer = str(request.META.get("HTTP_REFERER") or "").strip()
        redirect_to = referer or reverse("membership-requests")
        if redirect_to and not url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_to = reverse("membership-requests")

    ignore_membership_request(
        membership_request=req,
        actor_username=request.user.get_username(),
    )

    target_label = _membership_request_target_label(req)
    messages.success(request, f"Ignored request for {target_label}.")
    return redirect(redirect_to)


@permission_required(ASTRA_CHANGE_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_set_expiry(request: HttpRequest, username: str, membership_type_code: str) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    username = _normalize_str(username)
    membership_type_code = _normalize_str(membership_type_code)
    if not username or not membership_type_code:
        raise Http404("Not found")

    membership_type = get_object_or_404(MembershipType, pk=membership_type_code)

    valid_memberships = get_valid_memberships_for_username(username)
    current_membership = next(
        (m for m in valid_memberships if m.membership_type_id == membership_type.code),
        None,
    )
    if current_membership is None:
        messages.error(request, "That user does not currently have an active membership of that type.")
        return redirect("user-profile", username=username)

    form = MembershipUpdateExpiryForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid expiration date.")
        return redirect("user-profile", username=username)

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


@permission_required(ASTRA_DELETE_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_terminate(request: HttpRequest, username: str, membership_type_code: str) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    username = _normalize_str(username)
    membership_type_code = _normalize_str(membership_type_code)
    if not username or not membership_type_code:
        raise Http404("Not found")

    membership_type = get_object_or_404(MembershipType, pk=membership_type_code)

    target = FreeIPAUser.get(username)
    if target is None:
        messages.error(request, "Unable to load the requested user from FreeIPA.")
        return redirect("user-profile", username=username)

    valid_memberships = get_valid_memberships_for_username(username)
    current_membership = next(
        (m for m in valid_memberships if m.membership_type_id == membership_type.code),
        None,
    )
    if current_membership is None:
        messages.error(request, "That user does not currently have an active membership of that type.")
        return redirect("user-profile", username=username)

    MembershipLog.create_for_termination(
        actor_username=request.user.get_username(),
        target_username=username,
        membership_type=membership_type,
    )

    messages.success(request, "Membership terminated.")
    return redirect("user-profile", username=username)


@permission_required(ASTRA_CHANGE_MEMBERSHIP, login_url=reverse_lazy("users"))
def organization_sponsorship_set_expiry(request: HttpRequest, organization_id: int, membership_type_code: str) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    membership_type_code = _normalize_str(membership_type_code)
    if organization_id <= 0 or not membership_type_code:
        raise Http404("Not found")

    organization = get_object_or_404(Organization, pk=organization_id)
    membership_type = get_object_or_404(MembershipType, pk=membership_type_code)

    if organization.membership_level_id != membership_type.code:
        messages.error(request, "That organization does not currently have an active sponsorship of that type.")
        return redirect("organization-detail", organization_id=organization.pk)

    sponsorship = OrganizationSponsorship.objects.filter(organization=organization, membership_type=membership_type).first()
    if sponsorship is None or sponsorship.expires_at is None or sponsorship.expires_at <= timezone.now():
        messages.error(request, "That organization does not currently have an active sponsorship of that type.")
        return redirect("organization-detail", organization_id=organization.pk)

    next_url = str(request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_to = next_url
    else:
        referer = str(request.META.get("HTTP_REFERER") or "").strip()
        redirect_to = referer or reverse("organization-detail", kwargs={"organization_id": organization.pk})
        if redirect_to and not url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_to = reverse("organization-detail", kwargs={"organization_id": organization.pk})

    form = MembershipUpdateExpiryForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid expiration date.")
        return redirect(redirect_to)

    expires_on = form.cleaned_data["expires_on"]
    expires_at = datetime.datetime.combine(expires_on, datetime.time(23, 59, 59), tzinfo=datetime.UTC)
    MembershipLog.create_for_org_expiry_change(
        actor_username=request.user.get_username(),
        target_organization=organization,
        membership_type=membership_type,
        expires_at=expires_at,
    )

    messages.success(request, "Sponsorship expiration updated.")
    return redirect(redirect_to)


@permission_required(ASTRA_DELETE_MEMBERSHIP, login_url=reverse_lazy("users"))
def organization_sponsorship_terminate(request: HttpRequest, organization_id: int, membership_type_code: str) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    membership_type_code = _normalize_str(membership_type_code)
    if organization_id <= 0 or not membership_type_code:
        raise Http404("Not found")

    organization = get_object_or_404(Organization, pk=organization_id)
    membership_type = get_object_or_404(MembershipType, pk=membership_type_code)

    if organization.membership_level_id != membership_type.code:
        messages.error(request, "That organization does not currently have an active sponsorship of that type.")
        return redirect("organization-detail", organization_id=organization.pk)

    sponsorship = OrganizationSponsorship.objects.filter(organization=organization, membership_type=membership_type).first()
    if sponsorship is None or sponsorship.expires_at is None or sponsorship.expires_at <= timezone.now():
        messages.error(request, "That organization does not currently have an active sponsorship of that type.")
        return redirect("organization-detail", organization_id=organization.pk)

    MembershipLog.create_for_org_termination(
        actor_username=request.user.get_username(),
        target_organization=organization,
        membership_type=membership_type,
    )
    organization.membership_level = None
    organization.save(update_fields=["membership_level"])

    messages.success(request, "Sponsorship terminated.")
    return redirect("organization-detail", organization_id=organization.pk)
