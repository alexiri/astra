from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from django.http import HttpRequest, JsonResponse
from django.template import Context, Template
from django.template.exceptions import TemplateSyntaxError
from post_office.models import EmailTemplate

_VAR_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_]+)")
_PLURALIZE_PATTERN = re.compile(
    r"{{\s*(?P<var>[A-Za-z0-9_]+)\s*\|\s*pluralize(?:\s*:\s*(?P<q>['\"])(?P<arg>.*?)(?P=q))?\s*}}"
)


def _iter_pluralize_vars(*sources: str) -> Iterable[str]:
    for s in sources:
        for m in _PLURALIZE_PATTERN.finditer(str(s or "")):
            yield m.group("var")


def _parse_pluralize_arg(raw_arg: str | None) -> tuple[str, str]:
    """Return (singular, plural) for the pluralize filter argument.

    - No arg: equivalent to pluralize:,s
    - One part: pluralize:'es' => ('', 'es')
    - Two parts: pluralize:'y,ies' => ('y', 'ies')
    """

    if raw_arg is None:
        return "", "s"

    arg = str(raw_arg)
    if "," not in arg:
        return "", arg

    singular, plural = arg.split(",", 1)
    return singular, plural


def _render_pluralize_placeholder(*, singular: str, plural: str) -> str:
    if singular:
        return f"-{singular}/{plural}-"
    return f"-/{plural}-"


def _try_get_count(value: object) -> int | None:
    if isinstance(value, int):
        return value

    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return int(raw)
        return None

    # Best-effort: if it's a container (list/queryset/etc), use its length.
    try:
        return len(value)  # type: ignore[arg-type]
    except TypeError:
        return None


def _coerce_pluralize_inputs(*, render_context: dict[str, object], sources: tuple[str, ...]) -> None:
    """Normalize values used with `pluralize` so Django picks correctly.

    Django's `pluralize` compares against integer 1; if a template provides
    count values as strings (e.g. "1"), the default behavior can select the
    wrong branch. For preview, we try to coerce integer-like strings.
    """

    for var in set(_iter_pluralize_vars(*sources)):
        if var not in render_context:
            continue

        value = render_context[var]
        if isinstance(value, str):
            raw = value.strip()
            if raw.isdigit():
                render_context[var] = int(raw)


def _apply_pluralize_placeholders(*, template: str, render_context: Mapping[str, object]) -> str:
    """Render `pluralize` to a deterministic preview string.

    For unknown values (missing or not count-like), render a placeholder
    `-singular/plural-` (or `-/plural-` for empty singular).
    """

    def repl(match: re.Match[str]) -> str:
        var = match.group("var")
        singular, plural = _parse_pluralize_arg(match.group("arg"))

        if var not in render_context:
            return _render_pluralize_placeholder(singular=singular, plural=plural)

        count = _try_get_count(render_context[var])
        if count is None:
            return _render_pluralize_placeholder(singular=singular, plural=plural)

        return singular if count == 1 else plural

    return _PLURALIZE_PATTERN.sub(repl, template or "")


def placeholder_context_from_sources(*sources: str) -> dict[str, str]:
    names: set[str] = set()
    for s in sources:
        for m in _VAR_PATTERN.finditer(str(s or "")):
            names.add(m.group(1))
    return {name: f"-{name}-" for name in sorted(names)}


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
    sources = (subject, html_content, text_content)

    render_context: dict[str, object]
    if context:
        render_context = dict(context)
    else:
        render_context = placeholder_context_from_sources(*sources)

    _coerce_pluralize_inputs(render_context=render_context, sources=sources)

    subject = _apply_pluralize_placeholders(template=subject, render_context=render_context)
    html_content = _apply_pluralize_placeholders(template=html_content, render_context=render_context)
    text_content = _apply_pluralize_placeholders(template=text_content, render_context=render_context)

    return {
        "subject": render_template_string(subject, render_context),
        "html": render_template_string(html_content, render_context),
        "text": render_template_string(text_content, render_context),
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
