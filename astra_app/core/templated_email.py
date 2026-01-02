from __future__ import annotations

from collections.abc import Mapping

from django.http import HttpRequest, JsonResponse
from django.template import Context, Template
from django.template.exceptions import TemplateSyntaxError
from post_office.models import EmailTemplate


def render_template_string(value: str, context: Mapping[str, object]) -> str:
    """Render a Django template string with a plain context.

    Raise ValueError for template syntax errors so callers can consistently
    surface user-facing messages.
    """

    try:
        return Template(value or "").render(Context(dict(context)))
    except TemplateSyntaxError as exc:
        raise ValueError(str(exc)) from exc


def render_templated_email_preview(*, subject: str, html_content: str, text_content: str, context: Mapping[str, object]) -> dict[str, str]:
    return {
        "subject": render_template_string(subject, context),
        "html": render_template_string(html_content, context),
        "text": render_template_string(text_content, context),
    }


def render_templated_email_preview_response(*, request: HttpRequest, context: Mapping[str, object]) -> JsonResponse:
    """Render preview from request.POST and return a JSON response.

    This keeps view code focused on gathering context. Rendering and template
    error handling (syntax errors surfaced as 400s) is centralized here.
    """

    subject = str(request.POST.get("subject") or "")
    html_content = str(request.POST.get("html_content") or "")
    text_content = str(request.POST.get("text_content") or "")

    try:
        return JsonResponse(
            render_templated_email_preview(
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                context=context,
            )
        )
    except ValueError as exc:
        return JsonResponse({"error": f"Template error: {exc}"}, status=400)


def email_template_to_dict(template: EmailTemplate) -> dict[str, object]:
    return {
        "id": template.pk,
        "name": template.name,
        "subject": template.subject or "",
        "html_content": template.html_content or "",
        "text_content": template.content or "",
    }


def update_email_template(*, template: EmailTemplate, subject: str, html_content: str, text_content: str) -> None:
    template.subject = subject
    template.html_content = html_content
    template.content = text_content
    template.save(update_fields=["subject", "html_content", "content"])


def unique_email_template_name(raw_name: str) -> str:
    name = raw_name
    suffix = 2
    while EmailTemplate.objects.filter(name=name).exists():
        name = f"{raw_name}-{suffix}"
        suffix += 1
    return name


def create_email_template_unique(*, raw_name: str, subject: str, html_content: str, text_content: str) -> EmailTemplate:
    name = unique_email_template_name(raw_name)
    return EmailTemplate.objects.create(
        name=name,
        subject=subject,
        html_content=html_content,
        content=text_content,
    )
