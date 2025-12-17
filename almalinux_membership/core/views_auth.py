from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from python_freeipa import ClientMeta, exceptions

from .forms_auth import ExpiredPasswordChangeForm


logger = logging.getLogger(__name__)


class FreeIPALoginView(auth_views.LoginView):
    """LoginView that can redirect / message based on FreeIPA backend signals."""

    template_name = "core/login.html"

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
        new_password = form.cleaned_data["new_password"]

        try:
            client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
            # python-freeipa signature: change_password(username, new_password, old_password, otp=None)
            client.change_password(username, new_password, current_password)

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
