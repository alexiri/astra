from __future__ import annotations

import datetime
from typing import override

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import MembershipLog, MembershipRequest, MembershipType, Organization, OrganizationSponsorship
from core.permissions import (
    ASTRA_ADD_MEMBERSHIP,
    ASTRA_CHANGE_MEMBERSHIP,
    ASTRA_DELETE_MEMBERSHIP,
    ASTRA_VIEW_MEMBERSHIP,
)
from core.views_utils import _normalize_str


def _can_access_organization(request: HttpRequest, organization: Organization) -> bool:
    if not request.user.is_authenticated:
        return False

    username = str(request.user.get_username() or "").strip()
    if not username:
        return False

    if hasattr(request.user, "has_perm") and request.user.has_perm(ASTRA_VIEW_MEMBERSHIP):
        return True

    reps = organization.representatives if isinstance(organization.representatives, list) else []
    return username in reps


def _require_organization_access(request: HttpRequest, organization: Organization) -> None:
    if not _can_access_organization(request, organization):
        # Hide existence of organizations from unauthorized users.
        raise Http404


def _require_representative(request: HttpRequest, organization: Organization) -> None:
    if not request.user.is_authenticated:
        raise Http404

    username = str(request.user.get_username() or "").strip()
    if not username:
        raise Http404

    reps = organization.representatives if isinstance(organization.representatives, list) else []
    if username not in reps:
        raise Http404


def _can_edit_organization(request: HttpRequest, organization: Organization) -> bool:
    if not request.user.is_authenticated:
        return False

    if hasattr(request.user, "has_perm") and any(
        request.user.has_perm(p)
        for p in (ASTRA_ADD_MEMBERSHIP, ASTRA_CHANGE_MEMBERSHIP, ASTRA_DELETE_MEMBERSHIP)
    ):
        return True

    username = str(request.user.get_username() or "").strip()
    if not username:
        return False

    reps = organization.representatives if isinstance(organization.representatives, list) else []
    return username in reps


def _require_organization_edit_access(request: HttpRequest, organization: Organization) -> None:
    if not _can_edit_organization(request, organization):
        raise Http404


class OrganizationEditForm(forms.ModelForm):
    representatives = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control alx-select2",
                "data-placeholder": "Search users…",
            }
        ),
        help_text="Select the FreeIPA users who will be representatives for this organization.",
    )

    class Meta:
        model = Organization
        fields = (
            "business_contact_name",
            "business_contact_email",
            "business_contact_phone",
            "pr_marketing_contact_name",
            "pr_marketing_contact_email",
            "pr_marketing_contact_phone",
            "technical_contact_name",
            "technical_contact_email",
            "technical_contact_phone",
            "membership_level",
            "name",
            "website_logo",
            "website",
            "logo",
            "additional_information",
        )

        labels = {
            "business_contact_name": "Name",
            "business_contact_email": "Email",
            "business_contact_phone": "Phone",
            "pr_marketing_contact_name": "Name",
            "pr_marketing_contact_email": "Email",
            "pr_marketing_contact_phone": "Phone",
            "technical_contact_name": "Name",
            "technical_contact_email": "Email",
            "technical_contact_phone": "Phone",
            "membership_level": "Sponsorship Level",
            "name": "Legal/Official name of the sponsor to be listed",
            "website_logo": "High-quality logo that you would like used on the website",
            "website": "URL we should link to",
            "logo": "Logo upload for AlmaLinux Accounts",
            "additional_information": "Please provide any additional information the Membership Committee should take into account",
        }

        help_texts = {
            "website_logo": "Please provide a white logo, or a link to all of your logo options",
            "website": "Please provide the exact URL that you would like the logo to link to - this can be a dedicated page or just your primary URL",
        }

    @override
    def __init__(self, *args, **kwargs):
        self.can_select_representatives: bool = bool(kwargs.pop("can_select_representatives", False))
        super().__init__(*args, **kwargs)

        self.fields["membership_level"].queryset = MembershipType.objects.filter(isOrganization=True).order_by(
            "sort_order",
            "code",
        )

        self.fields["membership_level"].label_from_instance = (
            lambda membership_type: membership_type.description or membership_type.name
        )

        self.fields["business_contact_name"].required = True
        self.fields["business_contact_email"].required = True
        self.fields["pr_marketing_contact_name"].required = True
        self.fields["pr_marketing_contact_email"].required = True
        self.fields["technical_contact_name"].required = True
        self.fields["technical_contact_email"].required = True
        self.fields["membership_level"].required = False
        self.fields["name"].required = True
        self.fields["website_logo"].required = True
        self.fields["website"].required = True

        for field in self.fields.values():
            if isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs.setdefault("class", "form-control-file")
            else:
                field.widget.attrs.setdefault("class", "form-control")

        self.fields["website"].widget = forms.URLInput(attrs={"class": "form-control", "placeholder": "https://…"})
        self.fields["website_logo"].widget = forms.URLInput(attrs={"class": "form-control", "placeholder": "https://…"})
        self.fields["business_contact_email"].widget = forms.EmailInput(attrs={"class": "form-control"})
        self.fields["pr_marketing_contact_email"].widget = forms.EmailInput(attrs={"class": "form-control"})
        self.fields["technical_contact_email"].widget = forms.EmailInput(attrs={"class": "form-control"})

        if not self.can_select_representatives:
            # Representatives are defaulted to the creator; only membership admins can change.
            del self.fields["representatives"]
        else:
            # Select2 uses AJAX, so only include currently-selected values as choices.
            current_raw: list[str] = []
            if self.is_bound:
                current_raw = list(self.data.getlist("representatives"))
            else:
                initial = self.initial.get("representatives")
                if isinstance(initial, list):
                    current_raw = [str(v) for v in initial]
            current = [str(v).strip() for v in current_raw if str(v).strip()]
            self.fields["representatives"].choices = [(u, u) for u in sorted(set(current), key=str.lower)]

    def clean_representatives(self) -> list[str]:
        if "representatives" not in self.fields:
            return []

        raw = self.cleaned_data.get("representatives") or []
        cleaned = [str(u).strip() for u in raw if str(u).strip()]
        cleaned = sorted(set(cleaned), key=str.lower)

        missing: list[str] = []
        for username in cleaned:
            if FreeIPAUser.get(username) is None:
                missing.append(username)

        if missing:
            raise forms.ValidationError(
                f"Unknown user(s): {', '.join(missing)}",
                code="unknown_representatives",
            )

        return cleaned


class OrganizationCommitteeNotesForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ("notes",)

    @override
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False
        self.fields["notes"].widget.attrs.setdefault("class", "form-control")


@login_required
def organizations(request: HttpRequest) -> HttpResponse:
    username = str(request.user.get_username() or "").strip()
    if not username:
        raise Http404

    can_manage_memberships = any(
        request.user.has_perm(p)
        for p in (
            ASTRA_ADD_MEMBERSHIP,
            ASTRA_CHANGE_MEMBERSHIP,
            ASTRA_DELETE_MEMBERSHIP,
            ASTRA_VIEW_MEMBERSHIP,
        )
    )

    if can_manage_memberships:
        orgs = Organization.objects.select_related("membership_level").all().order_by("name", "id")
        empty_label = "No organizations found."
    else:
        orgs = (
            Organization.objects.select_related("membership_level")
            .filter(representatives__contains=[username])
            .order_by("name", "id")
        )
        empty_label = "You don't represent any organizations yet."

    q = _normalize_str(request.GET.get("q"))

    return render(
        request,
        "core/organizations.html",
        {
            "organizations": orgs,
            "create_url": reverse("organization-create"),
            "q": q,
            "empty_label": empty_label,
        },
    )


@login_required
def organization_create(request: HttpRequest) -> HttpResponse:
    username = str(request.user.get_username() or "").strip()
    if not username:
        raise Http404

    can_select_representatives = bool(hasattr(request.user, "has_perm") and request.user.has_perm(ASTRA_ADD_MEMBERSHIP))

    if request.method == "POST":
        form = OrganizationEditForm(
            request.POST,
            request.FILES,
            can_select_representatives=can_select_representatives,
        )
        if can_select_representatives and "representatives" in form.fields:
            form.fields["representatives"].widget.attrs["data-ajax-url"] = reverse(
                "organization-representatives-search"
            )
        if form.is_valid():
            organization = form.save(commit=False)

            reps: list[str]
            if can_select_representatives:
                selected = form.cleaned_data.get("representatives") or []
                reps = sorted(set([username, *selected]), key=str.lower)
            else:
                reps = [username]

            organization.representatives = reps
            organization.save()
            messages.success(request, "Organization created.")
            return redirect("organizations")
    else:
        form = OrganizationEditForm(can_select_representatives=can_select_representatives)
        if can_select_representatives and "representatives" in form.fields:
            form.fields["representatives"].widget.attrs["data-ajax-url"] = reverse(
                "organization-representatives-search"
            )

    return render(
        request,
        "core/organization_form.html",
        {
            "form": form,
            "cancel_url": reverse("organizations"),
            "is_create": True,
            "organization": None,
            "show_representatives": "representatives" in form.fields,
        },
    )


def organization_representatives_search(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("users")

    if not hasattr(request.user, "has_perm") or not (
        request.user.has_perm(ASTRA_ADD_MEMBERSHIP) or request.user.has_perm(ASTRA_CHANGE_MEMBERSHIP)
    ):
        return redirect("users")

    q = _normalize_str(request.GET.get("q"))
    if not q:
        return JsonResponse({"results": []})

    q_lower = q.lower()

    results: list[dict[str, str]] = []
    for u in FreeIPAUser.all():
        if not u.username:
            continue

        full_name = u.get_full_name()
        if q_lower not in u.username.lower() and q_lower not in full_name.lower():
            continue

        text = u.username
        if full_name and full_name != u.username:
            text = f"{u.username} — {full_name}"

        results.append({"id": u.username, "text": text})
        if len(results) >= 20:
            break

    results.sort(key=lambda r: r["id"].lower())
    return JsonResponse({"results": results})


@login_required
def organization_detail(request: HttpRequest, organization_id: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=organization_id)
    _require_organization_access(request, organization)

    username = str(request.user.get_username() or "").strip()
    is_representative = bool(username and isinstance(organization.representatives, list) and username in organization.representatives)

    sponsorship: OrganizationSponsorship | None = OrganizationSponsorship.objects.select_related("membership_type").filter(
        organization=organization
    ).first()
    now = timezone.now()
    expiring_soon_by = now + datetime.timedelta(days=settings.MEMBERSHIP_EXPIRING_SOON_DAYS)
    sponsorship_is_expiring_soon = bool(sponsorship and sponsorship.expires_at and sponsorship.expires_at <= expiring_soon_by)

    pending_membership_level_request = (
        MembershipRequest.objects.select_related("membership_type")
        .filter(requested_organization=organization, status=MembershipRequest.Status.pending)
        .order_by("-requested_at")
        .first()
    )

    can_edit_organization = _can_edit_organization(request, organization)

    return render(
        request,
        "core/organization_detail.html",
        {
            "organization": organization,
            "pending_membership_level_request": pending_membership_level_request,
            "sponsorship": sponsorship,
            "sponsorship_is_expiring_soon": sponsorship_is_expiring_soon,
            "is_representative": is_representative,
            "can_edit_organization": can_edit_organization,
        },
    )


@login_required
def organization_sponsorship_extend(request: HttpRequest, organization_id: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404("Not found")

    organization = get_object_or_404(Organization, pk=organization_id)
    _require_representative(request, organization)

    if organization.membership_level_id is None:
        messages.error(request, "No sponsorship level set to extend.")
        return redirect("organization-detail", organization_id=organization.pk)

    membership_type = organization.membership_level
    if membership_type is None:
        messages.error(request, "No sponsorship level set to extend.")
        return redirect("organization-detail", organization_id=organization.pk)

    sponsorship = OrganizationSponsorship.objects.filter(organization=organization).first()
    if sponsorship is None or sponsorship.expires_at is None:
        messages.error(request, "No sponsorship expiration recorded to extend.")
        return redirect("organization-detail", organization_id=organization.pk)

    now = timezone.now()
    if sponsorship.expires_at <= now:
        messages.error(request, "This sponsorship has already expired and cannot be extended. Submit a new sponsorship request.")
        return redirect("organization-detail", organization_id=organization.pk)

    expiring_soon_by = now + datetime.timedelta(days=settings.MEMBERSHIP_EXPIRING_SOON_DAYS)
    if sponsorship.expires_at > expiring_soon_by:
        messages.info(request, "This sponsorship is not expiring soon yet.")
        return redirect("organization-detail", organization_id=organization.pk)

    existing = (
        MembershipRequest.objects.filter(
            requested_organization=organization,
            membership_type=membership_type,
            status=MembershipRequest.Status.pending,
        )
        .order_by("-requested_at")
        .first()
    )
    if existing is not None:
        messages.info(request, "A sponsorship renewal request is already pending.")
        return redirect("organization-detail", organization_id=organization.pk)

    responses: list[dict[str, str]] = []
    if organization.additional_information.strip():
        responses.append({"Additional Information": organization.additional_information.strip()})

    mr = MembershipRequest.objects.create(
        requested_username="",
        requested_organization=organization,
        membership_type=membership_type,
        status=MembershipRequest.Status.pending,
        responses=responses,
    )
    MembershipLog.create_for_org_request(
        actor_username=request.user.get_username(),
        target_organization=organization,
        membership_type=membership_type,
        membership_request=mr,
    )
    messages.success(request, "Sponsorship renewal request submitted for review.")
    return redirect("organization-detail", organization_id=organization.pk)


@login_required
def organization_committee_notes_update(request: HttpRequest, organization_id: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=organization_id)

    if not hasattr(request.user, "has_perm") or not request.user.has_perm(ASTRA_VIEW_MEMBERSHIP):
        raise Http404

    can_edit = any(
        request.user.has_perm(p)
        for p in (ASTRA_ADD_MEMBERSHIP, ASTRA_CHANGE_MEMBERSHIP, ASTRA_DELETE_MEMBERSHIP)
    )
    if not can_edit:
        raise Http404

    form = OrganizationCommitteeNotesForm(request.POST or None, instance=organization)
    if request.method == "POST" and form.is_valid():
        form.save()

        redirect_to = str(request.POST.get("next") or "").strip()
        if redirect_to and redirect_to.startswith("/"):
            return redirect(redirect_to)
        return redirect("organization-detail", organization_id=organization.pk)

    return redirect("organization-detail", organization_id=organization.pk)


@login_required
def organization_edit(request: HttpRequest, organization_id: int) -> HttpResponse:
    organization = get_object_or_404(Organization, pk=organization_id)
    _require_organization_edit_access(request, organization)

    original_membership_level_id = organization.membership_level_id

    can_select_representatives = bool(
        hasattr(request.user, "has_perm") and request.user.has_perm(ASTRA_CHANGE_MEMBERSHIP)
    )

    initial: dict[str, object] = {}
    if can_select_representatives and isinstance(organization.representatives, list):
        initial["representatives"] = organization.representatives

    form = OrganizationEditForm(
        request.POST or None,
        request.FILES or None,
        instance=organization,
        can_select_representatives=can_select_representatives,
        initial=initial,
    )
    if can_select_representatives and "representatives" in form.fields:
        form.fields["representatives"].widget.attrs["data-ajax-url"] = reverse("organization-representatives-search")

    if request.method == "POST" and form.is_valid():
        requested_membership_level = form.cleaned_data.get("membership_level")

        updated_org = form.save(commit=False)

        if can_select_representatives and "representatives" in form.fields:
            reps = form.cleaned_data.get("representatives") or []
            if not reps:
                form.add_error("representatives", "At least one representative is required.")
                return render(
                    request,
                    "core/organization_form.html",
                    {
                        "organization": organization,
                        "form": form,
                        "is_create": False,
                        "cancel_url": "",
                        "show_representatives": True,
                    },
                )
            updated_org.representatives = reps

        # Membership level changes are reviewed by the committee; do not apply directly.
        updated_org.membership_level_id = original_membership_level_id
        updated_org.save()

        if (
            requested_membership_level is not None
            and requested_membership_level.code != original_membership_level_id
        ):
            existing = (
                MembershipRequest.objects.filter(
                    requested_organization=organization,
                    membership_type=requested_membership_level,
                    status=MembershipRequest.Status.pending,
                )
                .order_by("-requested_at")
                .first()
            )
            if existing is None:
                responses: list[dict[str, str]] = []
                if updated_org.additional_information.strip():
                    responses.append({"Additional Information": updated_org.additional_information.strip()})

                mr = MembershipRequest.objects.create(
                    requested_username="",
                    requested_organization=organization,
                    membership_type=requested_membership_level,
                    status=MembershipRequest.Status.pending,
                    responses=responses,
                )

                MembershipLog.create_for_org_request(
                    actor_username=request.user.get_username(),
                    target_organization=organization,
                    membership_type=requested_membership_level,
                    membership_request=mr,
                )

                messages.success(request, "Sponsorship level change submitted for review.")
            else:
                messages.info(request, "A sponsorship level change request is already pending.")

        return redirect("organization-detail", organization_id=organization.pk)

    return render(
        request,
        "core/organization_form.html",
        {
            "organization": organization,
            "form": form,
            "is_create": False,
            "cancel_url": "",
            "show_representatives": "representatives" in form.fields,
        },
    )
