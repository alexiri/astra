import json
from typing import Any

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import caches
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def _safe_preview(value: Any, *, max_chars: int) -> Any:
    if value is None:
        return None

    try:
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, sort_keys=True, default=str)
        else:
            text = str(value)
    except Exception:
        text = repr(value)

    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def _list_keys_from_backend(backend) -> list[str] | None:
    # LocMemCache exposes a per-process dict called _cache.
    internal = getattr(backend, "_cache", None)
    if isinstance(internal, dict):
        return sorted(str(k) for k in internal.keys())
    return None


@require_GET
@login_required(login_url="/admin/login/")
@user_passes_test(lambda u: bool(getattr(u, "is_superuser", False)), login_url="/admin/login/")
def cache_debug_view(request):
    """Superuser-only cache inspection endpoint.

    This runs inside the live Django process, so it can see LocMemCache keys.
    """

    backend = caches["default"]
    backend_path = f"{backend.__class__.__module__}.{backend.__class__.__name__}"

    max_chars = request.GET.get("max_chars", "4000")
    try:
        max_chars_i = int(max_chars)
    except ValueError:
        max_chars_i = 4000

    prefix = request.GET.get("prefix")
    key = request.GET.get("key")

    keys = _list_keys_from_backend(backend)
    supports_key_listing = keys is not None

    if keys is None:
        keys = []

    if prefix:
        keys = [k for k in keys if k.startswith(prefix)]

    payload: dict[str, Any] = {
        "backend": backend_path,
        "supports_key_listing": supports_key_listing,
        "count": len(keys),
        "keys": keys,
        "known_freeipa_keys": [
            "freeipa_users_all",
            "freeipa_groups_all",
            "freeipa_user_<username>",
            "freeipa_group_<cn>",
        ],
    }

    if key:
        payload["key"] = key
        payload["value_preview"] = _safe_preview(backend.get(key), max_chars=max_chars_i)

    return JsonResponse(payload)
