from __future__ import annotations

import base64
import io
import os
from base64 import b32encode
from typing import Any

import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from python_freeipa import ClientMeta, exceptions

from core.backends import FreeIPAUser
from core.forms_selfservice import OTPAddForm, OTPConfirmForm, OTPTokenActionForm, OTPTokenRenameForm
from core.views_utils import _normalize_str, settings_context

# Must be the same as KEY_LENGTH in ipaserver/plugins/otptoken.py.
# For maximum compatibility, must be a multiple of 5.
OTP_KEY_LENGTH = 35


type TokenDict = dict[str, Any]


@login_required(login_url="/login/")
def settings_otp(request: HttpRequest) -> HttpResponse:
    """Noggin-style OTP management."""

    username = request.user.get_username()

    is_add = request.method == "POST" and "add-submit" in request.POST
    is_confirm = request.method == "POST" and "confirm-submit" in request.POST

    add_form = OTPAddForm(request.POST if is_add else None, prefix="add")
    confirm_form = OTPConfirmForm(request.POST if is_confirm else None, prefix="confirm")

    tokens: list[TokenDict] = []
    otp_uri: str | None = None
    otp_qr_png_b64: str | None = None

    def _service_client() -> ClientMeta:
        c = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
        c.login(settings.FREEIPA_SERVICE_USER, settings.FREEIPA_SERVICE_PASSWORD)
        return c

    def _user_can_reauth(password: str) -> bool:
        c = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
        c.login(username, password)
        return True

    try:
        svc = _service_client()
        res = svc.otptoken_find(o_ipatokenowner=username, o_all=True)
        tokens = res.get("result", []) if isinstance(res, dict) else []
    except Exception:
        tokens = []

    # FreeIPA commonly returns attributes as single-item lists; normalize fields
    # we render directly so templates don't display Python list reprs.
    normalized_tokens: list[TokenDict] = []
    for raw in tokens:
        if not isinstance(raw, dict):
            continue
        t: TokenDict = dict(raw)

        description = t.get("description")
        if isinstance(description, list):
            description = description[0] if description else ""
        t["description"] = str(description).strip() if description else ""

        token_id = t.get("ipatokenuniqueid")
        if isinstance(token_id, list):
            out: list[str] = []
            for v in token_id:
                s = str(v).strip()
                if s:
                    out.append(s)
            t["ipatokenuniqueid"] = out
        elif token_id:
            t["ipatokenuniqueid"] = [str(token_id).strip()]
        else:
            t["ipatokenuniqueid"] = []

        normalized_tokens.append(t)

    tokens = normalized_tokens

    tokens.sort(key=lambda t: str(t.get("description") or "").casefold())

    secret: str | None = None

    if is_add and add_form.is_valid():
        description = _normalize_str(add_form.cleaned_data.get("description"))
        password = add_form.cleaned_data.get("password") or ""
        otp = _normalize_str(add_form.cleaned_data.get("otp"))
        if otp:
            password = f"{password}{otp}"

        try:
            _user_can_reauth(password)
        except exceptions.InvalidSessionPassword:
            add_form.add_error("password", "Incorrect password")
        except exceptions.Unauthorized:
            add_form.add_error("password", "Incorrect password")
        except Exception as e:
            if settings.DEBUG:
                add_form.add_error(None, f"Unable to reauthenticate (debug): {e}")
            else:
                add_form.add_error(None, "Unable to reauthenticate due to an internal error.")
        else:
            secret = b32encode(os.urandom(OTP_KEY_LENGTH)).decode("ascii")
            confirm_form = OTPConfirmForm(
                initial={
                    "secret": secret,
                    "description": description,
                },
                prefix="confirm",
            )

    if is_confirm:
        secret = _normalize_str(request.POST.get("confirm-secret")) or None

        if confirm_form.is_valid():
            description = _normalize_str(confirm_form.cleaned_data.get("description"))
            try:
                svc = _service_client()
                svc.otptoken_add(
                    o_ipatokenowner=username,
                    o_description=description,
                    o_type="totp",
                    o_ipatokenotpkey=confirm_form.cleaned_data["secret"],
                )
            except exceptions.FreeIPAError:
                confirm_form.add_error(None, "Cannot create the token.")
            except Exception as e:
                if settings.DEBUG:
                    confirm_form.add_error(None, f"Cannot create the token (debug): {e}")
                else:
                    confirm_form.add_error(None, "Cannot create the token.")
            else:
                messages.success(request, "The token has been created.")
                return redirect("settings-otp")

    if secret:
        host = settings.FREEIPA_HOST
        parts = host.split(".")
        realm = ".".join(parts[1:]).upper() if len(parts) > 1 else host.upper()
        issuer = f"{username}@{realm}" if realm else username

        if is_confirm:
            description = _normalize_str(request.POST.get("confirm-description"))
        elif is_add:
            description = _normalize_str(add_form.cleaned_data.get("description"))
        else:
            description = (getattr(confirm_form, "initial", {}) or {}).get("description") or ""
            description = _normalize_str(description)

        token = pyotp.TOTP(secret)
        otp_uri = str(token.provisioning_uri(name=description or "(no name)", issuer_name=issuer))

        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(otp_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        otp_qr_png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    context = {
        "add_form": add_form,
        "confirm_form": confirm_form,
        "tokens": tokens,
        "otp_uri": otp_uri,
        "otp_qr_png_b64": otp_qr_png_b64,
        **settings_context("otp"),
    }
    return render(request, "core/settings_otp.html", context)


@login_required(login_url="/login/")
def otp_enable(request: HttpRequest) -> HttpResponse:
    form = OTPTokenActionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        token = form.cleaned_data["token"]
        try:
            client = FreeIPAUser.get_client()
            client.otptoken_mod(a_ipatokenuniqueid=token, o_ipatokendisabled=False)
        except exceptions.FreeIPAError as e:
            messages.error(request, f"Cannot enable the token. {e}")
        else:
            messages.success(request, "OTP token enabled.")
    else:
        messages.error(request, "Token must not be empty")
    return redirect("settings-otp")


@login_required(login_url="/login/")
def otp_disable(request: HttpRequest) -> HttpResponse:
    form = OTPTokenActionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        token = form.cleaned_data["token"]
        try:
            client = FreeIPAUser.get_client()
            client.otptoken_mod(a_ipatokenuniqueid=token, o_ipatokendisabled=True)
        except exceptions.FreeIPAError as e:
            messages.error(request, f"Cannot disable the token. {e}")
        else:
            messages.success(request, "OTP token disabled.")
    else:
        messages.error(request, "Token must not be empty")
    return redirect("settings-otp")


@login_required(login_url="/login/")
def otp_delete(request: HttpRequest) -> HttpResponse:
    form = OTPTokenActionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        token = form.cleaned_data["token"]
        try:
            client = FreeIPAUser.get_client()
            client.otptoken_del(a_ipatokenuniqueid=token)
        except exceptions.BadRequest as e:
            if "can't delete last active token" in str(e).lower():
                messages.warning(request, "Sorry, you cannot delete your last active token.")
            else:
                messages.error(request, "Cannot delete the token.")
        except exceptions.FreeIPAError:
            messages.error(request, "Cannot delete the token.")
        else:
            messages.success(request, "OTP token deleted.")
    else:
        messages.error(request, "Token must not be empty")
    return redirect("settings-otp")


@login_required(login_url="/login/")
def otp_rename(request: HttpRequest) -> HttpResponse:
    form = OTPTokenRenameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        token = form.cleaned_data["token"]
        description = _normalize_str(form.cleaned_data.get("description"))
        try:
            client = FreeIPAUser.get_client()
            client.otptoken_mod(a_ipatokenuniqueid=token, o_description=description)
        except exceptions.BadRequest as e:
            if "no modifications" not in str(e).lower():
                messages.error(request, "Cannot rename the token.")
        except exceptions.FreeIPAError:
            messages.error(request, "Cannot rename the token.")
        else:
            messages.success(request, "OTP token renamed.")
    else:
        if form.errors:
            first_field_errors = next(iter(form.errors.values()))
            first_error = first_field_errors[0] if first_field_errors else "Invalid form"
            messages.error(request, str(first_error))
        else:
            messages.error(request, "Token must not be empty")
    return redirect("settings-otp")
