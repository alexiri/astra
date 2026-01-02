from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.http.response import Http404
from django.views.decorators.http import require_GET, require_POST
from post_office.models import EmailTemplate

from core.permissions import ASTRA_ADD_ELECTION, ASTRA_ADD_MAILMERGE, json_permission_required_any
from core.templated_email import (
    create_email_template_unique,
    email_template_to_dict,
    update_email_template,
)

_MANAGE_TEMPLATE_PERMISSIONS: frozenset[str] = frozenset({ASTRA_ADD_ELECTION, ASTRA_ADD_MAILMERGE})


@require_GET
@json_permission_required_any(_MANAGE_TEMPLATE_PERMISSIONS)
def email_template_json(request: HttpRequest, template_id: int) -> JsonResponse:
    template = EmailTemplate.objects.filter(pk=template_id).first()
    if template is None:
        raise Http404("Template not found")

    return JsonResponse(email_template_to_dict(template))


@require_POST
@json_permission_required_any(_MANAGE_TEMPLATE_PERMISSIONS)
def email_template_save(request: HttpRequest) -> JsonResponse:
    template_id_raw = str(request.POST.get("email_template_id") or "").strip()
    if not template_id_raw:
        return JsonResponse({"ok": False, "error": "email_template_id is required"}, status=400)

    try:
        template_id = int(template_id_raw)
    except ValueError:
        return JsonResponse({"ok": False, "error": "Invalid email_template_id"}, status=400)

    template = EmailTemplate.objects.filter(pk=template_id).first()
    if template is None:
        return JsonResponse({"ok": False, "error": "Template not found"}, status=404)

    update_email_template(
        template=template,
        subject=str(request.POST.get("subject") or ""),
        html_content=str(request.POST.get("html_content") or ""),
        text_content=str(request.POST.get("text_content") or ""),
    )

    return JsonResponse({"ok": True, "id": template.pk, "name": template.name})


@require_POST
@json_permission_required_any(_MANAGE_TEMPLATE_PERMISSIONS)
def email_template_save_as(request: HttpRequest) -> JsonResponse:
    raw_name = str(request.POST.get("name") or "").strip()
    if not raw_name:
        return JsonResponse({"ok": False, "error": "name is required"}, status=400)

    template = create_email_template_unique(
        raw_name=raw_name,
        subject=str(request.POST.get("subject") or ""),
        html_content=str(request.POST.get("html_content") or ""),
        text_content=str(request.POST.get("text_content") or ""),
    )

    return JsonResponse({"ok": True, "id": template.pk, "name": template.name})
