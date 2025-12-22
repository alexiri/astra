from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.backends import FreeIPAFASAgreement


@dataclass(frozen=True, slots=True)
class AgreementForUser:
    cn: str
    description: str
    signed: bool
    applicable: bool
    enabled: bool


def has_enabled_agreements() -> bool:
    for agreement in FreeIPAFASAgreement.all() or []:
        if bool(getattr(agreement, "enabled", True)):
            return True
    return False


def list_agreements_for_user(
    username: str,
    *,
    user_groups: Iterable[str],
    include_disabled: bool = False,
    applicable_only: bool = False,
) -> list[AgreementForUser]:
    username = (username or "").strip()
    groups_set = {str(g).strip().lower() for g in (user_groups or []) if str(g).strip()}

    out: list[AgreementForUser] = []
    for agreement in FreeIPAFASAgreement.all() or []:
        cn = str(getattr(agreement, "cn", "") or "").strip()
        if not cn:
            continue

        full = FreeIPAFASAgreement.get(cn) or agreement
        enabled = bool(getattr(full, "enabled", True))
        if not include_disabled and not enabled:
            continue

        agreement_groups = {str(g).strip().lower() for g in (getattr(full, "groups", []) or []) if str(g).strip()}
        applicable = not agreement_groups or bool(groups_set & agreement_groups)
        if applicable_only and not applicable:
            continue

        users = {str(u).strip() for u in (getattr(full, "users", []) or []) if str(u).strip()}
        signed = username in users if username else False

        out.append(
            AgreementForUser(
                cn=cn,
                description=str(getattr(full, "description", "") or ""),
                signed=signed,
                applicable=applicable,
                enabled=enabled,
            )
        )

    return sorted(out, key=lambda a: a.cn.lower())


def required_agreements_for_group(group_cn: str) -> list[str]:
    """Return enabled agreement CNs that apply to a given group.

    Group gating is based on agreements that explicitly list the group in their
    linked groups.
    """

    group_cn = (group_cn or "").strip()
    if not group_cn:
        return []

    group_key = group_cn.lower()
    required: list[str] = []

    for agreement in FreeIPAFASAgreement.all() or []:
        cn = str(getattr(agreement, "cn", "") or "").strip()
        if not cn:
            continue

        full = FreeIPAFASAgreement.get(cn) or agreement
        if not bool(getattr(full, "enabled", True)):
            continue

        agreement_groups = {
            str(g).strip().lower()
            for g in (getattr(full, "groups", []) or [])
            if str(g).strip()
        }
        if group_key in agreement_groups:
            required.append(cn)

    return sorted(set(required), key=str.lower)


def missing_required_agreements_for_user_in_group(username: str, group_cn: str) -> list[str]:
    """Return agreement CNs the user must sign before joining a group."""

    username = (username or "").strip()
    if not username:
        return []

    missing: list[str] = []
    for agreement_cn in required_agreements_for_group(group_cn):
        agreement = FreeIPAFASAgreement.get(agreement_cn)
        if not agreement or not bool(getattr(agreement, "enabled", True)):
            continue

        users = {str(u).strip() for u in (getattr(agreement, "users", []) or []) if str(u).strip()}
        if username not in users:
            missing.append(agreement_cn)

    return sorted(set(missing), key=str.lower)
