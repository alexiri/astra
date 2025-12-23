from __future__ import annotations

from typing import override

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Organization


def _require_representative(request: HttpRequest, organization: Organization) -> None:
    if not request.user.is_authenticated:
        raise Http404

    username = str(request.user.get_username() or "").strip()
    if not username:
        raise Http404

    reps = organization.representatives if isinstance(organization.representatives, list) else []
    if username not in reps:
        # Hide existence of organizations from non-reps.
        raise Http404


class OrganizationEditForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ("name", "logo", "contact", "website")

    @override
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs.setdefault("class", "form-control-file")
            else:
                field.widget.attrs.setdefault("class", "form-control")


@login_required
def organizations(request: HttpRequest) -> HttpResponse:
    username = str(request.user.get_username() or "").strip()
    if not username:
        raise Http404

    # Only representatives should be able to see this interface.
    orgs = Organization.objects.filter(representatives__contains=[username]).order_by("name", "code")
    if not orgs.exists():
        raise Http404

    return render(request, "core/organizations.html", {"organizations": orgs})


@login_required
def organization_detail(request: HttpRequest, code: str) -> HttpResponse:
    organization = get_object_or_404(Organization, code=code)
    _require_representative(request, organization)

    return render(request, "core/organization_detail.html", {"organization": organization})


@login_required
def organization_edit(request: HttpRequest, code: str) -> HttpResponse:
    organization = get_object_or_404(Organization, code=code)
    _require_representative(request, organization)

    form = OrganizationEditForm(request.POST or None, request.FILES or None, instance=organization)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("organization-detail", code=organization.code)

    return render(request, "core/organization_edit.html", {"organization": organization, "form": form})
