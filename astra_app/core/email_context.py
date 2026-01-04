from __future__ import annotations

from typing import TYPE_CHECKING

from core.backends import FreeIPAUser

if TYPE_CHECKING:
    from core.models import Organization


def user_email_context(*, username: str) -> dict[str, str]:
    """Return canonical user variables for templated emails.

    The email templates assume these variables exist, even if blank:
    - username
    - first_name
    - last_name
    - full_name
    - email

    We intentionally do not expose `displayname` to templates.
    """

    normalized_username = str(username or "").strip()
    if not normalized_username:
        return {"username": "", "first_name": "", "last_name": "", "full_name": "", "email": ""}

    user = FreeIPAUser.get(normalized_username)
    if user is None:
        return {
            "username": normalized_username,
            "first_name": "",
            "last_name": "",
            "full_name": normalized_username,
            "email": "",
        }

    return {
        "username": str(user.username or ""),
        "first_name": str(user.first_name or ""),
        "last_name": str(user.last_name or ""),
        "full_name": str(user.full_name or ""),
        "email": str(user.email or ""),
    }


def user_email_context_from_user(*, user: FreeIPAUser) -> dict[str, str]:
    return {
        "username": str(user.username or ""),
        "first_name": str(user.first_name or ""),
        "last_name": str(user.last_name or ""),
        "full_name": str(user.full_name or ""),
        "email": str(user.email or ""),
    }


def organization_email_context_from_organization(*, organization: Organization) -> dict[str, str]:
    """Return canonical organization variables for sponsor-facing templated emails.

    The email templates assume these variables exist, even if blank:
    - business_contact_name, business_contact_email
    - pr_marketing_contact_name, pr_marketing_contact_email
    - technical_contact_name, technical_contact_email
    """

    return {
        "business_contact_name": str(organization.business_contact_name or ""),
        "business_contact_email": str(organization.business_contact_email or ""),
        "pr_marketing_contact_name": str(organization.pr_marketing_contact_name or ""),
        "pr_marketing_contact_email": str(organization.pr_marketing_contact_email or ""),
        "technical_contact_name": str(organization.technical_contact_name or ""),
        "technical_contact_email": str(organization.technical_contact_email or ""),
    }


def organization_sponsor_email_context(*, organization: Organization) -> dict[str, str]:
    """Return sponsor email context: org contact fields + representative user variables."""

    representative_username = str(organization.representative or "").strip()
    if representative_username:
        representative = FreeIPAUser.get(representative_username)
        representative_context = (
            user_email_context_from_user(user=representative)
            if representative is not None
            else user_email_context(username=representative_username)
        )
    else:
        representative_context = user_email_context(username="")

    return organization_email_context_from_organization(organization=organization) | representative_context
