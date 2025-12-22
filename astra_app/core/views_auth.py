from __future__ import annotations

import logging
from typing import override

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

import requests

from python_freeipa import ClientMeta, exceptions

from .forms_auth import ExpiredPasswordChangeForm, FreeIPAAuthenticationForm, SyncTokenForm
from core.views_utils import _normalize_str


logger = logging.getLogger(__name__)


class FreeIPALoginView(auth_views.LoginView):
    """LoginView that can redirect / message based on FreeIPA backend signals."""

    template_name = "core/login.html"
    authentication_form = FreeIPAAuthenticationForm

    @override
    def get_success_url(self) -> str:
        user = getattr(self.request, "user", None)
        get_username = getattr(user, "get_username", None)
        if callable(get_username):
            try:
                username = str(get_username()).strip()
            except Exception:
                username = ""
            if username:
                return reverse("user-profile", kwargs={"username": username})

        return super().get_success_url()

    def form_invalid(self, form) -> HttpResponse:
        request: HttpRequest = self.request

        if getattr(request, "_freeipa_password_expired", False):
            return redirect("password-expired")

        msg = getattr(request, "_freeipa_auth_error", None)
        if msg:
            form.add_error(None, msg)

        return super().form_invalid(form)


def password_expired(request: HttpRequest) -> HttpResponse:
    """Password-expired landing + change-password form.

    FreeIPA often requires a password change when the password is expired.
    This uses python-freeipa's `change_password` endpoint (does not require an authenticated session).
    """

    initial_username = None
    try:
        initial_username = request.session.get("_freeipa_pwexp_username")
    except Exception:
        initial_username = None

    form = ExpiredPasswordChangeForm(request.POST or None, initial={"username": initial_username} if initial_username else None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        current_password = form.cleaned_data["current_password"]
        otp = _normalize_str(form.cleaned_data.get("otp")) or None
        new_password = form.cleaned_data["new_password"]

        try:
            client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
            # python-freeipa signature: change_password(username, new_password, old_password, otp=None)
            client.change_password(username, new_password, current_password, otp=otp)

            try:
                request.session.pop("_freeipa_pwexp_username", None)
            except Exception:
                pass

            messages.success(request, "Password changed. Please log in.")
            return redirect("login")
        except exceptions.PWChangePolicyError as e:
            logger.debug("password_expired: policy error username=%s error=%s", username, e)
            form.add_error(None, "Password change rejected by policy. Please choose a stronger password.")
        except exceptions.PWChangeInvalidPassword as e:
            logger.debug("password_expired: invalid password username=%s error=%s", username, e)
            form.add_error("current_password", "Current password is incorrect.")
        except exceptions.PasswordExpired:
            # Still expired is fine; user is here to change it.
            form.add_error(None, "Password is expired; please change it below.")
        except exceptions.Unauthorized:
            form.add_error(None, "Unable to change password. Please check your username and current password.")
        except exceptions.FreeIPAError as e:
            logger.warning("password_expired: FreeIPA error username=%s error=%s", username, e)
            form.add_error(None, "Unable to change password due to a FreeIPA error.")
        except Exception as e:
            logger.exception("password_expired: unexpected error username=%s", username)
            if settings.DEBUG:
                form.add_error(None, f"Unable to change password (debug): {e}")
            else:
                form.add_error(None, "Unable to change password due to an internal error.")

    return render(request, "core/password_expired.html", {"form": form})


def otp_sync(request: HttpRequest) -> HttpResponse:
    """Noggin-style OTP sync.

    This is intentionally *not* behind login: users may need it when their
    token has drifted and they can't log in.

    FreeIPA supports syncing via a special endpoint:
    POST https://<host>/ipa/session/sync_token
    with form data: user, password, first_code, second_code, token (optional).
    """

    form = SyncTokenForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        first_code = form.cleaned_data["first_code"]
        second_code = form.cleaned_data["second_code"]
        token = _normalize_str(form.cleaned_data.get("token")) or None

        url = f"https://{settings.FREEIPA_HOST}/ipa/session/sync_token"
        data = {
            "user": username,
            "password": password,
            "first_code": first_code,
            "second_code": second_code,
            "token": token or "",
        }

        try:
            session = requests.Session()
            response = session.post(
                url=url,
                data=data,
                verify=settings.FREEIPA_VERIFY_SSL,
                timeout=10,
            )
            if response.ok and "Token sync rejected" not in (response.text or ""):
                messages.success(request, "Token successfully synchronized")
                return redirect("login")

            form.add_error(None, "The username, password or token codes are not correct.")
        except requests.exceptions.RequestException:
            form.add_error(None, "No IPA server available")
        except Exception as e:
            logger.exception("otp_sync: unexpected error username=%s", username)
            if settings.DEBUG:
                form.add_error(None, f"Something went wrong (debug): {e}")
            else:
                form.add_error(None, "Something went wrong")

    return render(request, "core/sync_token.html", {"form": form})
