from __future__ import annotations

import datetime
import logging
from urllib.parse import urlencode

import post_office.mail
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from post_office.models import EmailTemplate

from core.backends import FreeIPAUser
from core.forms_membership import MembershipRejectForm, MembershipRequestForm, MembershipUpdateExpiryForm
from core.membership import get_valid_memberships_for_username
from core.membership_request_workflow import approve_membership_request, record_membership_request_created
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


def _membership_request_email_templates(*, name_prefix: str) -> list[EmailTemplate]:
    return list(EmailTemplate.objects.filter(name__startswith=name_prefix).order_by("name"))


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


@login_required(login_url="/login/")
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


@login_required(login_url="/login/")
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


@login_required(login_url="/login/")
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


@login_required(login_url="/login/")
@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_requests(request: HttpRequest) -> HttpResponse:
    approved_email_templates = _membership_request_email_templates(name_prefix="membership-request-approved")
    rejected_email_templates = _membership_request_email_templates(name_prefix="membership-request-rejected")

    requests = (
        MembershipRequest.objects.select_related("membership_type", "requested_organization")
        .filter(status=MembershipRequest.Status.pending)
        .order_by("requested_at")
    )

    request_rows: list[dict[str, object]] = []
    for r in requests:
        default_approve_template = settings.MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME
        if r.membership_type.acceptance_template_id is not None:
            default_approve_template = r.membership_type.acceptance_template.name

        default_reject_template = settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME

        if r.requested_username == "":
            org = r.requested_organization
            request_rows.append(
                {
                    "r": r,
                    "organization": org,
                    "organization_code": r.requested_organization_code,
                    "organization_name": r.requested_organization_name,
                    "target_email": org.primary_contact_email() if org is not None else "",
                    "default_approve_template": default_approve_template,
                    "default_reject_template": default_reject_template,
                }
            )
        else:
            fu = FreeIPAUser.get(r.requested_username)
            full_name = fu.get_full_name() if fu is not None else ""
            status_note = fu.fasstatusnote if fu is not None else ""
            request_rows.append(
                {
                    "r": r,
                    "full_name": full_name,
                    "status_note": status_note,
                    "user_deleted": fu is None,
                    "target_email": (fu.email or "") if fu is not None else "",
                    "default_approve_template": default_approve_template,
                    "default_reject_template": default_reject_template,
                }
            )

    return render(
        request,
        "core/membership_requests.html",
        {
            "requests": requests,
            "request_rows": request_rows,
            "approved_email_templates": approved_email_templates,
            "rejected_email_templates": rejected_email_templates,
        },
    )


@login_required(login_url="/login/")
@permission_required(ASTRA_VIEW_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_detail(request: HttpRequest, pk: int) -> HttpResponse:
    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type", "requested_organization"), pk=pk)

    approved_email_templates = _membership_request_email_templates(name_prefix="membership-request-approved")
    rejected_email_templates = _membership_request_email_templates(name_prefix="membership-request-rejected")

    target_user = None
    target_full_name = ""
    target_user_deleted = False
    target_email = ""
    if req.requested_username:
        target_user = FreeIPAUser.get(req.requested_username)
        if target_user is None:
            target_user_deleted = True
        else:
            target_full_name = target_user.get_full_name()
            target_email = target_user.email or ""
    else:
        org = req.requested_organization
        if org is not None:
            target_email = org.primary_contact_email()

    default_approve_template = settings.MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME
    if req.membership_type.acceptance_template_id is not None:
        default_approve_template = req.membership_type.acceptance_template.name
    default_reject_template = settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME

    return render(
        request,
        "core/membership_request_detail.html",
        {
            "req": req,
            "target_user": target_user,
            "target_full_name": target_full_name,
            "target_user_deleted": target_user_deleted,
            "target_email": target_email,
            "approved_email_templates": approved_email_templates,
            "rejected_email_templates": rejected_email_templates,
            "default_approve_template": default_approve_template,
            "default_reject_template": default_reject_template,
        },
    )


@login_required(login_url="/login/")
def membership_status_note_update(request: HttpRequest, username: str) -> HttpResponse:
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

    target_username = _normalize_str(username)
    if not target_username:
        raise Http404("User not found")

    next_url = str(request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_to = next_url
    else:
        referer = str(request.META.get("HTTP_REFERER") or "").strip()
        redirect_to = referer or reverse("user-profile", kwargs={"username": target_username})

        if redirect_to and not url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_to = reverse("user-profile", kwargs={"username": target_username})

    note = str(request.POST.get("fasstatusnote") or "")
    try:
        FreeIPAUser.set_status_note(target_username, note)
    except Exception:
        logger.exception("Failed to update fasstatusnote username=%s", target_username)
        messages.error(request, "Failed to update note.")
        return redirect(redirect_to)

    messages.success(request, "Note updated.")
    return redirect(redirect_to)


@login_required(login_url="/login/")
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
        membership_type = req.membership_type

        if req.requested_username == "":
            org = req.requested_organization

            if action == "approve":
                try:
                    approve_membership_request(
                        membership_request=req,
                        actor_username=actor_username,
                        send_approved_email=False,
                    )
                except Exception:
                    logger.exception("Bulk approve failed for membership request pk=%s", req.pk)
                    failures += 1
                    continue

                approved += 1
                continue

            if action == "reject":
                if org is not None:
                    MembershipLog.create_for_org_rejection(
                        actor_username=actor_username,
                        target_organization=org,
                        membership_type=membership_type,
                        rejection_reason="",
                        membership_request=req,
                    )
                else:
                    MembershipLog.objects.create(
                        actor_username=actor_username,
                        target_username="",
                        target_organization=None,
                        target_organization_code=req.requested_organization_code,
                        target_organization_name=req.requested_organization_name,
                        membership_type=membership_type,
                        membership_request=req,
                        requested_group_cn=membership_type.group_cn,
                        action=MembershipLog.Action.rejected,
                        rejection_reason="",
                        expires_at=None,
                    )
                req.status = MembershipRequest.Status.rejected
                req.decided_at = timezone.now()
                req.decided_by_username = actor_username
                req.save(update_fields=["status", "decided_at", "decided_by_username"])
                rejected += 1
                continue

            if org is not None:
                MembershipLog.create_for_org_ignore(
                    actor_username=actor_username,
                    target_organization=org,
                    membership_type=membership_type,
                    membership_request=req,
                )
            else:
                MembershipLog.objects.create(
                    actor_username=actor_username,
                    target_username="",
                    target_organization=None,
                    target_organization_code=req.requested_organization_code,
                    target_organization_name=req.requested_organization_name,
                    membership_type=membership_type,
                    membership_request=req,
                    requested_group_cn=membership_type.group_cn,
                    action=MembershipLog.Action.ignored,
                    expires_at=None,
                )
            req.status = MembershipRequest.Status.ignored
            req.decided_at = timezone.now()
            req.decided_by_username = actor_username
            req.save(update_fields=["status", "decided_at", "decided_by_username"])
            ignored += 1
            continue

        if action == "approve":
            try:
                approve_membership_request(
                    membership_request=req,
                    actor_username=actor_username,
                    send_approved_email=True,
                )
            except Exception:
                logger.exception("Bulk approve failed to add user to membership group")
                failures += 1
                continue

            approved += 1

        elif action == "reject":
            target = FreeIPAUser.get(req.requested_username)
            reason = ""
            MembershipLog.create_for_rejection(
                actor_username=actor_username,
                target_username=req.requested_username,
                membership_type=membership_type,
                rejection_reason=reason,
                membership_request=req,
            )
            req.status = MembershipRequest.Status.rejected
            req.decided_at = timezone.now()
            req.decided_by_username = actor_username
            req.save(update_fields=["status", "decided_at", "decided_by_username"])
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
                membership_request=req,
            )
            req.status = MembershipRequest.Status.ignored
            req.decided_at = timezone.now()
            req.decided_by_username = actor_username
            req.save(update_fields=["status", "decided_at", "decided_by_username"])
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
@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_approve(request: HttpRequest, pk: int) -> HttpResponse:
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

    skip_email = bool(str(request.POST.get("skip_email") or "").strip())
    selected_template = str(request.POST.get("email_template") or "").strip()
    approved_email_template_name: str | None = None
    if not skip_email and selected_template:
        if not selected_template.startswith("membership-request-approved"):
            messages.error(request, "Invalid email template selection.")
            return redirect(redirect_to)
        if not EmailTemplate.objects.filter(name=selected_template).exists():
            messages.error(request, "Selected email template not found.")
            return redirect(redirect_to)
        approved_email_template_name = selected_template

    try:
        approve_membership_request(
            membership_request=req,
            actor_username=request.user.get_username(),
            send_approved_email=not skip_email,
            approved_email_template_name=approved_email_template_name,
        )
    except Exception:
        logger.exception("Failed to approve membership request pk=%s", req.pk)
        messages.error(request, "Failed to approve the request.")
        return redirect(redirect_to)

    if req.requested_username == "":
        org = req.requested_organization
        org_name = org.name if org is not None else (req.requested_organization_name or "organization")
        messages.success(request, f"Approved sponsorship level request for {org_name}.")
        return redirect(redirect_to)

    messages.success(request, f"Approved membership request for {req.requested_username}.")
    return redirect(redirect_to)


@login_required(login_url="/login/")
@permission_required(ASTRA_ADD_MEMBERSHIP, login_url=reverse_lazy("users"))
def membership_request_reject(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    req = get_object_or_404(MembershipRequest.objects.select_related("membership_type", "requested_organization"), pk=pk)
    membership_type = req.membership_type

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

    if req.requested_username == "":
        form = MembershipRejectForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid rejection reason.")
            return redirect(redirect_to)

        reason = str(form.cleaned_data.get("reason") or "").strip()
        if reason:
            req.responses = [{"Rejection reason": reason}]

        skip_email = bool(str(request.POST.get("skip_email") or "").strip())
        selected_template = str(request.POST.get("email_template") or "").strip()
        reject_template = settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME
        if (not skip_email) and selected_template:
            if not selected_template.startswith("membership-request-rejected"):
                messages.error(request, "Invalid email template selection.")
                return redirect(redirect_to)
            if not EmailTemplate.objects.filter(name=selected_template).exists():
                messages.error(request, "Selected email template not found.")
                return redirect(redirect_to)
            reject_template = selected_template

        org = req.requested_organization
        if org is not None:
            MembershipLog.create_for_org_rejection(
                actor_username=request.user.get_username(),
                target_organization=org,
                membership_type=membership_type,
                rejection_reason=reason,
                membership_request=req,
            )
        else:
            MembershipLog.objects.create(
                actor_username=request.user.get_username(),
                target_username="",
                target_organization=None,
                target_organization_code=req.requested_organization_code,
                target_organization_name=req.requested_organization_name,
                membership_type=membership_type,
                membership_request=req,
                requested_group_cn=membership_type.group_cn,
                action=MembershipLog.Action.rejected,
                rejection_reason=reason,
                expires_at=None,
            )

        req.status = MembershipRequest.Status.rejected
        req.decided_at = timezone.now()
        req.decided_by_username = request.user.get_username()
        req.save(update_fields=["responses", "status", "decided_at", "decided_by_username"])

        org_email = org.primary_contact_email() if org is not None else ""
        if (not skip_email) and org_email:
            post_office.mail.send(
                recipients=[org_email],
                sender=settings.DEFAULT_FROM_EMAIL,
                template=reject_template,
                context={
                    "organization_name": org.name if org is not None else (req.requested_organization_name or ""),
                    "membership_type": membership_type.name,
                    "membership_type_code": membership_type.code,
                    "rejection_reason": reason,
                },
            )

        org_name = org.name if org is not None else (req.requested_organization_name or "organization")
        messages.success(request, f"Rejected sponsorship level request for {org_name}.")
        return redirect(redirect_to)

    form = MembershipRejectForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid rejection reason.")
        return redirect(redirect_to)

    reason = str(form.cleaned_data.get("reason") or "").strip()
    target = FreeIPAUser.get(req.requested_username)

    MembershipLog.create_for_rejection(
        actor_username=request.user.get_username(),
        target_username=req.requested_username,
        membership_type=membership_type,
        rejection_reason=reason,
        membership_request=req,
    )

    req.status = MembershipRequest.Status.rejected
    req.decided_at = timezone.now()
    req.decided_by_username = request.user.get_username()
    req.save(update_fields=["status", "decided_at", "decided_by_username"])

    skip_email = bool(str(request.POST.get("skip_email") or "").strip())
    selected_template = str(request.POST.get("email_template") or "").strip()
    reject_template = settings.MEMBERSHIP_REQUEST_REJECTED_EMAIL_TEMPLATE_NAME
    if (not skip_email) and selected_template:
        if not selected_template.startswith("membership-request-rejected"):
            messages.error(request, "Invalid email template selection.")
            return redirect(redirect_to)
        if not EmailTemplate.objects.filter(name=selected_template).exists():
            messages.error(request, "Selected email template not found.")
            return redirect(redirect_to)
        reject_template = selected_template

    if not skip_email and target is not None and target.email:
        post_office.mail.send(
            recipients=[target.email],
            sender=settings.DEFAULT_FROM_EMAIL,
            template=reject_template,
            context={
                "username": target.username,
                "membership_type": membership_type.name,
                "membership_type_code": membership_type.code,
                "rejection_reason": reason,
            },
        )

    messages.success(request, f"Rejected membership request for {req.requested_username}.")
    return redirect(redirect_to)


@login_required(login_url="/login/")
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

    if req.requested_username == "":
        org = req.requested_organization
        org_name = org.name if org is not None else (req.requested_organization_name or "organization")

        if org is not None:
            MembershipLog.create_for_org_ignore(
                actor_username=request.user.get_username(),
                target_organization=org,
                membership_type=req.membership_type,
                membership_request=req,
            )
        else:
            MembershipLog.objects.create(
                actor_username=request.user.get_username(),
                target_username="",
                target_organization=None,
                target_organization_code=req.requested_organization_code,
                target_organization_name=req.requested_organization_name,
                membership_type=req.membership_type,
                membership_request=req,
                requested_group_cn=req.membership_type.group_cn,
                action=MembershipLog.Action.ignored,
                expires_at=None,
            )

        req.status = MembershipRequest.Status.ignored
        req.decided_at = timezone.now()
        req.decided_by_username = request.user.get_username()
        req.save(update_fields=["status", "decided_at", "decided_by_username"])

        messages.success(request, f"Ignored sponsorship level request for {org_name}.")
        return redirect(redirect_to)

    MembershipLog.create_for_ignore(
        actor_username=request.user.get_username(),
        target_username=req.requested_username,
        membership_type=req.membership_type,
        membership_request=req,
    )

    req.status = MembershipRequest.Status.ignored
    req.decided_at = timezone.now()
    req.decided_by_username = request.user.get_username()
    req.save(update_fields=["status", "decided_at", "decided_by_username"])

    messages.success(request, f"Ignored membership request for {req.requested_username}.")
    return redirect(redirect_to)


@login_required(login_url="/login/")
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


@login_required(login_url="/login/")
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


@login_required(login_url="/login/")
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


@login_required(login_url="/login/")
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
