from __future__ import annotations

from typing import Any

from django.template import Context, Library
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

register = Library()


def _sponsorship_label_for(organization: object) -> str:
    # Template tags are intentionally duck-typed; the object may be a real
    # Organization model or a lightweight stub from tests.
    if not hasattr(organization, "membership_level"):
        return ""

    membership_level = organization.membership_level
    if membership_level is None:
        return ""

    name = ""
    if hasattr(membership_level, "name"):
        try:
            name = str(membership_level.name or "").strip()
        except Exception:
            name = ""

    return name


def _sponsorship_tier_for(organization: object) -> str:
    if not hasattr(organization, "membership_level"):
        return ""

    membership_level = organization.membership_level
    if membership_level is None:
        return ""

    if hasattr(membership_level, "code"):
        try:
            code = str(membership_level.code or "").strip()
        except Exception:
            code = ""
        if code:
            return code.replace("_", " ").title()

    label = _sponsorship_label_for(organization)
    if not label:
        return ""
    parts = label.split()
    return parts[0].strip().title() if parts else ""


def _sponsorship_badge_class_for(tier: str) -> str:
    tier_lower = tier.strip().lower()
    return {
        "platinum": "badge-primary",
        "gold": "badge-warning",
        "silver": "badge-secondary",
        "ruby": "badge-danger",
    }.get(tier_lower, "badge-info")


def _sponsorship_pill_text_for(organization: object) -> str:
    label = _sponsorship_label_for(organization)
    if not label:
        return ""

    # Keep the UI label short and readable.
    # Many of our membership types include a trailing "Member" (e.g. "Silver Sponsor Member").
    normalized = label.strip()
    if normalized.lower().endswith(" sponsor member"):
        return normalized[: -len(" member")]
    if normalized.lower().endswith(" member"):
        return normalized[: -len(" member")]
    return normalized


@register.simple_tag(takes_context=True, name="organization")
def organization_widget(context: Context, organization: object, **kwargs: Any) -> str:
    extra_class = kwargs.get("class", "") or ""
    extra_style = kwargs.get("style", "") or ""

    html = render_to_string(
        "core/_organization_widget.html",
        {
            "organization": organization,
            "sponsorship_label": _sponsorship_label_for(organization),
            "sponsorship_tier": _sponsorship_tier_for(organization),
            "sponsorship_badge_class": _sponsorship_badge_class_for(_sponsorship_tier_for(organization)),
            "sponsorship_pill_text": _sponsorship_pill_text_for(organization),
            "extra_class": extra_class,
            "extra_style": extra_style,
        },
        request=context.get("request"),
    )
    return mark_safe(html)
