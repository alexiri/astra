from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.template import Library
from django.utils.html import format_html

register = Library()


def _get_default_server(scheme: str) -> str | None:
    networks = getattr(settings, "CHAT_NETWORKS", None)
    if not isinstance(networks, dict):
        return None
    network = networks.get(scheme)
    if not isinstance(network, dict):
        return None
    default_server = network.get("default_server")
    return default_server if isinstance(default_server, str) and default_server else None


@register.filter(name="nickname")
def nickname(value: str | None, scheme: str | None = None) -> str:
    """Render a chat nickname as a link (Noggin-style).

    Supported schemes:
    - IRC: produces an irc:// link
    - Matrix: produces a https://matrix.to link

    Input formats supported (best-effort):
    - Stored URL forms: irc:///nick, irc://server/nick, matrix:/nick, matrix://server/nick
    - Plain forms: nick, @nick, nick:server, nick@server
    """

    if not value:
        return ""

    raw = str(value).strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    parsed_scheme = (parsed.scheme or "").lower()

    effective_scheme = (scheme or parsed_scheme or "irc").lower()
    default_server = _get_default_server(effective_scheme)

    nick: str
    server: str

    if parsed_scheme:
        nick = (parsed.path or "").lstrip("/")
        if not nick and parsed.fragment:
            nick = parsed.fragment.lstrip("#@")
        server = (parsed.netloc or "").strip() or (default_server or "")
    else:
        # Plain forms like nick, nick:server, nick@server, @nick:server
        cleaned = raw.lstrip("@").strip()
        if ":" in cleaned:
            nick, _, server = cleaned.partition(":")
        elif "@" in cleaned:
            nick, _, server = cleaned.partition("@")
        else:
            nick, server = cleaned, ""
        server = server.strip() or (default_server or "")

    if not nick or not server:
        # Best-effort: if we can't confidently build a link, return plain text.
        return raw

    if effective_scheme == "irc":
        href = f"irc://{server}/{nick},isnick"
        title = f"IRC on {server}"
        display = nick
        if default_server and server != default_server:
            display = f"{display}:{server}"
        elif not default_server:
            display = f"{display}:{server}"
        return format_html('<a href="{}" title="{}">{}</a>', href, title, display)

    if effective_scheme == "matrix":
        matrixto_args = getattr(settings, "CHAT_MATRIX_TO_ARGS", None)
        args = matrixto_args if isinstance(matrixto_args, str) and matrixto_args else ""
        href = f"https://matrix.to/#/@{nick}:{server}"
        if args:
            href = f"{href}?{args}"

        title = f"Matrix on {server}"

        display = f"@{nick}"
        if default_server and server != default_server:
            display = f"{display}:{server}"
        elif not default_server:
            display = f"{display}:{server}"

        return format_html('<a href="{}" title="{}" target="_blank" rel="noopener noreferrer">{}</a>', href, title, display)

    return raw
