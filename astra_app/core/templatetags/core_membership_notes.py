from __future__ import annotations

import hashlib
from typing import Any

from django import template
from django.http import HttpRequest

from core.backends import FreeIPAUser
from core.membership_notes import note_action_icon, note_action_label, tally_last_votes
from core.models import MembershipRequest, Note

register = template.Library()


_BUBBLE_BG_COLORS: list[str] = [
    # Light, readable colors. Keep these fairly pastel to avoid jarring UI.
    "#BBDEFB",
    "#C8E6C9",
    "#FFE0B2",
    "#E1BEE7",
    "#B2EBF2",
    "#FFF9C4",
    "#F8BBD0",
    "#D1C4E9",
    "#C5CAE9",
    "#DCEDC8",
    "#F0F4C3",
    "#B2DFDB",
    "#FFECB3",
    "#FFCCBC",
    "#D7CCC8",
    "#CFD8DC",
    "#B3E5FC",
    "#C5E1A5",
    "#FFCDD2",
    "#E6EE9C",
]


def _relative_luminance_from_hex(hex_color: str) -> float:
    v = hex_color.lstrip("#")
    if len(v) != 6:
        return 1.0

    r = int(v[0:2], 16) / 255.0
    g = int(v[2:4], 16) / 255.0
    b = int(v[4:6], 16) / 255.0

    def to_linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    rl, gl, bl = to_linear(r), to_linear(g), to_linear(b)
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl


def _pick_foreground_for_background(bg_hex: str) -> str:
    # Choose foreground with better WCAG contrast against the background.
    bg_l = _relative_luminance_from_hex(bg_hex)
    white_l = 1.0
    blackish_l = 0.0

    contrast_white = (white_l + 0.05) / (bg_l + 0.05)
    contrast_black = (bg_l + 0.05) / (blackish_l + 0.05)
    return "#ffffff" if contrast_white >= contrast_black else "#212529"


def _bubble_style_for_username(username: str) -> str:
    # Built-in hash() is randomized per-process; use a stable digest.
    digest = hashlib.blake2s(username.encode("utf-8"), digest_size=2).digest()
    idx = int.from_bytes(digest, "big") % len(_BUBBLE_BG_COLORS)
    bg = _BUBBLE_BG_COLORS[idx]
    fg = _pick_foreground_for_background(bg)
    return f"--bubble-bg: {bg}; --bubble-fg: {fg};"


@register.inclusion_tag("core/_membership_notes.html", takes_context=True)
def membership_notes(
    context: dict[str, Any],
    membership_request: MembershipRequest | int,
    *,
    compact: bool = False,
    next_url: str | None = None,
) -> dict[str, Any]:
    request = context.get("request")
    http_request = request if isinstance(request, HttpRequest) else None

    mr: MembershipRequest | None
    if isinstance(membership_request, MembershipRequest):
        mr = membership_request
    else:
        mr = MembershipRequest.objects.select_related("membership_type", "requested_organization").filter(pk=membership_request).first()

    if mr is None:
        return {"ok": False, "compact": compact}

    notes = list(Note.objects.filter(membership_request_id=mr.pk).order_by("timestamp", "pk"))
    approvals, disapprovals = tally_last_votes(notes)

    resolved_next_url = next_url
    if resolved_next_url is None:
        resolved_next_url = http_request.get_full_path() if http_request is not None else ""

    avatar_users_by_username: dict[str, object] = {}
    for username in {n.username for n in notes if n.username}:
        user_obj = FreeIPAUser.get(username)
        if user_obj is not None:
            avatar_users_by_username[username] = user_obj

    current_username = ""
    if http_request is not None and getattr(http_request, "user", None) is not None:
        try:
            current_username = str(http_request.user.get_username() or "").strip()
        except Exception:
            current_username = ""

    membership_can_add = bool(context.get("membership_can_add", False))
    membership_can_change = bool(context.get("membership_can_change", False))
    membership_can_delete = bool(context.get("membership_can_delete", False))
    can_post = membership_can_add or membership_can_change or membership_can_delete

    entries: list[dict[str, Any]] = []
    for n in notes:
        is_self = current_username and n.username.lower() == current_username.lower()
        avatar_user = avatar_users_by_username.get(n.username)

        if isinstance(n.action, dict) and n.action:
            label = note_action_label(n.action)
            icon = note_action_icon(n.action)
            entries.append(
                {
                    "kind": "action",
                    "note": n,
                    "label": label,
                    "icon": icon,
                    "is_self": is_self,
                    "avatar_user": avatar_user,
                    "bubble_style": "--bubble-bg: #f8f9fa; --bubble-fg: #212529;",
                }
            )

        if n.content is not None and str(n.content).strip() != "":
            bubble_style: str | None = None
            if not is_self and n.username:
                bubble_style = _bubble_style_for_username(n.username.strip().lower())

            entries.append(
                {
                    "kind": "message",
                    "note": n,
                    "is_self": is_self,
                    "avatar_user": avatar_user,
                    "bubble_style": bubble_style,
                }
            )

    return {
        "ok": True,
        "compact": compact,
        "membership_request": mr,
        "entries": entries,
        "note_count": len(notes),
        "approvals": approvals,
        "disapprovals": disapprovals,
        "can_post": can_post,
        "next_url": resolved_next_url,
    }
