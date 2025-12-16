from __future__ import annotations

from django.contrib.auth import get_user as django_get_user
from django.contrib.auth.models import AnonymousUser
from django.utils.functional import SimpleLazyObject

from .backends import FreeIPAUser


def _get_freeipa_or_default_user(request):
    # If this is a FreeIPA session, we store the username directly so it survives reloads.
    username = None
    try:
        username = request.session.get("_freeipa_username")
    except Exception:
        username = None

    if username:
        user = FreeIPAUser.get(username)
        return user if user is not None else AnonymousUser()

    # Fallback to Django's normal session-based user loading.
    return django_get_user(request)


class FreeIPAAuthenticationMiddleware:
    """Authentication middleware that can restore FreeIPA users without a DB row.

    Django's default AuthenticationMiddleware restores the user via backend.get_user(user_id).
    Our backend historically needed an in-memory id->username cache; this middleware prefers the
    username stored in session during login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: _get_freeipa_or_default_user(request))
        return self.get_response(request)
