from __future__ import annotations

from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user as django_get_user
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from django.utils.functional import SimpleLazyObject

from core.backends import FreeIPAUser, clear_freeipa_service_client_cache


def _first_ci(data: object, attr: str):
    if not isinstance(data, dict):
        return None
    if attr in data:
        value = data.get(attr)
    else:
        value = data.get(attr.lower())
        if value is None:
            for k, v in data.items():
                if str(k).lower() == attr.lower():
                    value = v
                    break

    if isinstance(value, list):
        return value[0] if value else None
    return value


def _get_user_timezone_name(user) -> str | None:
    data = getattr(user, "_user_data", None)
    tz_name = _first_ci(data, "fasTimezone")
    tz_name = str(tz_name).strip() if tz_name else ""
    return tz_name or None


def _get_freeipa_or_default_user(request):
    # Prefer Django's standard session-based user restoration first.
    user = django_get_user(request)
    if getattr(user, "is_authenticated", False):
        return user

    # If this is a FreeIPA session, we store the username directly so it survives reloads.
    try:
        username = request.session.get("_freeipa_username")
    except Exception:
        username = None

    if username:
        freeipa_user = FreeIPAUser.get(username)
        return freeipa_user if freeipa_user is not None else AnonymousUser()

    return user


class FreeIPAAuthenticationMiddleware:
    """Authentication middleware that can restore FreeIPA users without a DB row.

    Django's default AuthenticationMiddleware restores the user via backend.get_user(user_id).
    Our backend historically needed an in-memory id->username cache; this middleware prefers the
    username stored in session during login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If an upstream middleware already attached an authenticated user,
        # preserve it. Otherwise, wrap request.user so we can restore a FreeIPA
        # user from session-stored username even if Django resolves to
        # AnonymousUser (e.g. when no DB row exists).
        existing_user = getattr(request, "user", None)
        if not getattr(existing_user, "is_authenticated", False):
            request.user = SimpleLazyObject(lambda: _get_freeipa_or_default_user(request))

        # Activate the user's timezone for this request so template tags/filters
        # (and timezone.localtime) reflect the user's configured FreeIPA timezone.
        activated = False
        try:
            user = request.user
            tz_name = None
            if getattr(user, "is_authenticated", False):
                tz_name = _get_user_timezone_name(user)

            if not tz_name:
                tz_name = settings.TIME_ZONE

            try:
                timezone.activate(ZoneInfo(tz_name))
            except Exception:
                timezone.activate(ZoneInfo("UTC"))

            activated = True
            return self.get_response(request)
        finally:
            if activated:
                timezone.deactivate()


class FreeIPAServiceClientReuseMiddleware:
    """Request-scoped reuse of the FreeIPA service client.

    Service-account operations can happen multiple times per request
    (profile page + groups + permissions, etc.). Reusing the logged-in client
    reduces repeated logins, but we must prevent reuse across requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Default to reusing the service client across requests (per worker
        # thread) to cut down on repeated admin logins. If you run an async
        # server with concurrent requests in the same thread and see issues,
        # set FREEIPA_SERVICE_CLIENT_REUSE_ACROSS_REQUESTS=0.
        if not settings.FREEIPA_SERVICE_CLIENT_REUSE_ACROSS_REQUESTS:
            clear_freeipa_service_client_cache()
        try:
            return self.get_response(request)
        finally:
            if not settings.FREEIPA_SERVICE_CLIENT_REUSE_ACROSS_REQUESTS:
                clear_freeipa_service_client_cache()
