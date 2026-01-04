from __future__ import annotations

import datetime
import logging
from urllib.parse import quote

import post_office.mail
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.module_loading import import_string
from python_freeipa import ClientMeta

from core.agreements import has_enabled_agreements, list_agreements_for_user
from core.backends import FreeIPAFASAgreement, FreeIPAUser
from core.email_context import user_email_context
from core.forms_selfservice import EmailsForm, KeysForm, PasswordChangeFreeIPAForm, ProfileForm
from core.tokens import make_signed_token, read_signed_token
from core.views_utils import (
    _add_change,
    _add_change_list_setattr,
    _add_change_setattr,
    _bool_from_ipa,
    _bool_to_ipa,
    _data_get,
    _first,
    _form_label_for_attr,
    _get_full_user,
    _normalize_str,
    _split_lines,
    _split_list_field,
    _update_user_attrs,
    _value_to_csv,
    _value_to_text,
    settings_context,
)

logger = logging.getLogger(__name__)


def _send_email_validation_email(
    request: HttpRequest,
    *,
    username: str,
    name: str,
    attr: str,
    email_to_validate: str,
) -> None:
    base_ctx = user_email_context(username=username)
    token = make_signed_token({"u": username, "a": attr, "v": email_to_validate})
    validate_url = request.build_absolute_uri(reverse("settings-email-validate")) + f"?token={quote(token)}"
    ttl_seconds = settings.EMAIL_VALIDATION_TOKEN_TTL_SECONDS
    ttl_minutes = max(1, int((ttl_seconds + 59) / 60))
    valid_until = timezone.now() + datetime.timedelta(seconds=ttl_seconds)
    valid_until_utc = valid_until.astimezone(datetime.UTC).strftime("%H:%M")

    post_office.mail.send(
        recipients=[email_to_validate],
        sender=settings.DEFAULT_FROM_EMAIL,
        template=settings.EMAIL_VALIDATION_EMAIL_TEMPLATE_NAME,
        context={
            **base_ctx,
            "name": name or base_ctx["full_name"],
            "attr": attr,
            "email_to_validate": email_to_validate,
            "validate_url": validate_url,
            "ttl_minutes": ttl_minutes,
            "valid_until_utc": valid_until_utc,
        },
    )


def _detect_avatar_provider(user: object, *, size: int = 140) -> tuple[str | None, str | None]:
    """Return (provider_path, avatar_url) for the first provider that yields a URL."""

    for provider_path in settings.AVATAR_PROVIDERS:
        try:
            provider_cls = import_string(provider_path)
        except Exception:
            continue

        get_url = getattr(provider_cls, "get_avatar_url", None)
        if not callable(get_url):
            continue

        try:
            url = str(get_url(user, size, size)).strip()
        except Exception:
            continue

        if url:
            return provider_path, url

    return None, None


def _avatar_manage_url_for_provider(provider_path: str | None) -> str | None:
    if not provider_path:
        return None

    if provider_path.endswith("LibRAvatarProvider"):
        return "https://www.libravatar.org/"
    if provider_path.endswith("GravatarAvatarProvider"):
        return "https://gravatar.com/"

    return None


def avatar_manage(request: HttpRequest) -> HttpResponse:
    """Redirect the user to the appropriate place to manage their avatar."""

    provider_path, _ = _detect_avatar_provider(request.user)
    manage_url = _avatar_manage_url_for_provider(provider_path)
    if manage_url:
        return redirect(manage_url)

    messages.info(request, "Your current avatar provider does not support direct avatar updates here.")
    return redirect("settings-profile")


def settings_profile(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("home")

    data = fu._user_data

    initial = {
        "givenname": fu.first_name,
        "sn": fu.last_name,
        "fasPronoun": _value_to_csv(_data_get(data, "fasPronoun", "")),
        "fasLocale": _first(data, "fasLocale", "") or "",
        "fasTimezone": _first(data, "fasTimezone", "") or "",
        "fasWebsiteUrl": _value_to_text(_data_get(data, "fasWebsiteUrl", "")),
        "fasRssUrl": _value_to_text(_data_get(data, "fasRssUrl", "")),
        "fasIRCNick": _value_to_text(_data_get(data, "fasIRCNick", "")),
        "fasGitHubUsername": _first(data, "fasGitHubUsername", "") or "",
        "fasGitLabUsername": _first(data, "fasGitLabUsername", "") or "",
        "fasIsPrivate": _bool_from_ipa(_data_get(data, "fasIsPrivate", "FALSE"), default=False),
    }

    form = ProfileForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        direct_updates: dict[str, object] = {}
        addattrs: list[str] = []
        setattrs: list[str] = []
        delattrs: list[str] = []

        _add_change(
            updates=direct_updates,
            delattrs=delattrs,
            attr="givenname",
            current_value=initial.get("givenname"),
            new_value=form.cleaned_data["givenname"],
        )
        _add_change(
            updates=direct_updates,
            delattrs=delattrs,
            attr="sn",
            current_value=initial.get("sn"),
            new_value=form.cleaned_data["sn"],
        )
        new_cn = f"{form.cleaned_data['givenname']} {form.cleaned_data['sn']}".strip() or username
        current_cn = _first(data, "cn", "")
        _add_change(
            updates=direct_updates,
            delattrs=delattrs,
            attr="cn",
            current_value=current_cn,
            new_value=new_cn,
        )

        _add_change_list_setattr(
            addattrs=addattrs,
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasPronoun",
            current_values=_data_get(data, "fasPronoun", []),
            new_values=_split_list_field(form.cleaned_data["fasPronoun"]),
        )
        _add_change_setattr(
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasLocale",
            current_value=initial.get("fasLocale"),
            new_value=form.cleaned_data["fasLocale"],
        )
        _add_change_setattr(
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasTimezone",
            current_value=initial.get("fasTimezone"),
            new_value=form.cleaned_data["fasTimezone"],
        )

        _add_change_list_setattr(
            addattrs=addattrs,
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasWebsiteUrl",
            current_values=_data_get(data, "fasWebsiteUrl", []),
            new_values=_split_list_field(form.cleaned_data["fasWebsiteUrl"]),
        )
        _add_change_list_setattr(
            addattrs=addattrs,
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasRssUrl",
            current_values=_data_get(data, "fasRssUrl", []),
            new_values=_split_list_field(form.cleaned_data["fasRssUrl"]),
        )
        _add_change_list_setattr(
            addattrs=addattrs,
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasIRCNick",
            current_values=_data_get(data, "fasIRCNick", []),
            new_values=_split_list_field(form.cleaned_data["fasIRCNick"]),
        )
        _add_change_setattr(
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasGitHubUsername",
            current_value=initial.get("fasGitHubUsername"),
            new_value=form.cleaned_data["fasGitHubUsername"],
        )
        _add_change_setattr(
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasGitLabUsername",
            current_value=initial.get("fasGitLabUsername"),
            new_value=form.cleaned_data["fasGitLabUsername"],
        )

        current_private = initial["fasIsPrivate"]
        new_private = form.cleaned_data["fasIsPrivate"]
        if current_private != new_private:
            setattrs.append(f"fasIsPrivate={_bool_to_ipa(new_private)}")

        try:
            if not direct_updates and not addattrs and not setattrs and not delattrs:
                messages.info(request, "No changes to save.")
                return redirect("settings-profile")

            skipped, applied = _update_user_attrs(
                username,
                direct_updates=direct_updates,
                addattrs=addattrs,
                setattrs=setattrs,
                delattrs=delattrs,
            )
            if skipped:
                for attr in skipped:
                    label = _form_label_for_attr(form, attr)
                    messages.warning(
                        request,
                        f"Saved, but '{label or attr}' is not editable on this FreeIPA server.",
                    )

            if applied:
                messages.success(request, "Profile updated in FreeIPA.")
            else:
                messages.info(request, "No changes were applied.")
            return redirect("settings-profile")
        except Exception as e:
            logger.exception("Failed to update profile username=%s", username)
            if settings.DEBUG:
                messages.error(request, f"Failed to update profile (debug): {e}")
            else:
                messages.error(request, "Failed to update profile due to an internal error.")

    context = {
        "form": form,
        "chat_networks": settings.CHAT_NETWORKS,
        **settings_context("profile"),
    }
    return render(request, "core/settings_profile.html", context)


def settings_emails(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("home")

    data = fu._user_data

    initial = {
        "mail": fu.email,
        "fasRHBZEmail": _first(data, "fasRHBZEmail", "") or "",
    }

    form = EmailsForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        direct_updates: dict[str, object] = {}
        setattrs: list[str] = []
        delattrs: list[str] = []

        pending_validations: list[tuple[str, str]] = []  # (attr, new_value)

        current_mail = _normalize_str(initial.get("mail"))
        new_mail = _normalize_str(form.cleaned_data["mail"]).lower()
        current_rhbz = _normalize_str(initial.get("fasRHBZEmail"))
        new_rhbz = _normalize_str(form.cleaned_data["fasRHBZEmail"]).lower()

        if current_mail != new_mail and new_mail:
            if _normalize_str(current_rhbz).lower() == new_mail and current_rhbz:
                direct_updates["o_mail"] = new_mail
            else:
                pending_validations.append(("mail", new_mail))

        if current_rhbz != new_rhbz:
            if new_rhbz:
                if _normalize_str(current_mail).lower() == new_rhbz and current_mail:
                    _add_change_setattr(
                        setattrs=setattrs,
                        delattrs=delattrs,
                        attr="fasRHBZEmail",
                        current_value=current_rhbz,
                        new_value=new_rhbz,
                    )
                else:
                    pending_validations.append(("fasRHBZEmail", new_rhbz))
            else:
                _add_change_setattr(
                    setattrs=setattrs,
                    delattrs=delattrs,
                    attr="fasRHBZEmail",
                    current_value=current_rhbz,
                    new_value=new_rhbz,
                )

        try:
            if not pending_validations and not direct_updates and not setattrs and not delattrs:
                messages.info(request, "No changes to save.")
                return redirect("settings-emails")

            if direct_updates or setattrs or delattrs:
                skipped, applied = _update_user_attrs(
                    username,
                    direct_updates=direct_updates,
                    setattrs=setattrs,
                    delattrs=delattrs,
                )
                if skipped:
                    for attr in skipped:
                        label = _form_label_for_attr(form, attr)
                        messages.warning(
                            request,
                            f"Saved, but '{label or attr}' is not editable on this FreeIPA server.",
                        )

                if applied:
                    messages.success(request, "Email settings updated in FreeIPA.")
                else:
                    messages.info(request, "No changes were applied.")

            if pending_validations:
                name = fu.full_name
                for attr, address in pending_validations:
                    _send_email_validation_email(
                        request,
                        username=username,
                        name=name,
                        attr=attr,
                        email_to_validate=address,
                    )

                messages.success(
                    request,
                    "We sent you an email to validate your new email address. Please check your inbox.",
                )

            return redirect("settings-emails")
        except Exception as e:
            logger.exception("Failed to update email settings username=%s", username)
            if settings.DEBUG:
                messages.error(request, f"Failed to update email settings (debug): {e}")
            else:
                messages.error(request, "Failed to update email settings due to an internal error.")

    context = {"form": form, **settings_context("emails")}
    return render(request, "core/settings_emails.html", context)


def settings_email_validate(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    token_string = _normalize_str(request.GET.get("token"))
    if not token_string:
        messages.warning(request, "No token provided, please check your email validation link.")
        return redirect("settings-emails")

    try:
        token = read_signed_token(token_string)
    except signing.SignatureExpired:
        messages.warning(request, "This token is no longer valid, please request a new validation email.")
        return redirect("settings-emails")
    except signing.BadSignature:
        messages.warning(request, "The token is invalid, please request a new validation email.")
        return redirect("settings-emails")

    token_user = _normalize_str(token.get("u"))
    attr = _normalize_str(token.get("a"))
    value = _normalize_str(token.get("v")).lower()

    if token_user != username:
        messages.warning(request, "This token does not belong to you.")
        return redirect("settings-emails")

    if attr not in {"mail", "fasRHBZEmail"}:
        messages.warning(request, "The token is invalid, please request a validation email.")
        return redirect("settings-emails")

    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("home")

    attr_label = "E-mail Address" if attr == "mail" else "Red Hat Bugzilla Email"

    if request.method == "POST":
        direct_updates: dict[str, object] = {}
        setattrs: list[str] = []
        delattrs: list[str] = []

        if attr == "mail":
            direct_updates["o_mail"] = value
        else:
            setattrs.append(f"fasRHBZEmail={value}")

        try:
            _update_user_attrs(username, direct_updates=direct_updates, setattrs=setattrs, delattrs=delattrs)
        except Exception as e:
            logger.exception("Email validation apply failed username=%s attr=%s", username, attr)
            if settings.DEBUG:
                messages.error(request, f"Failed to validate email (debug): {e}")
            else:
                messages.error(request, "Failed to validate email due to an internal error.")
            return redirect("settings-emails")

        messages.success(request, "Your email address has been validated.")
        return redirect("settings-emails")

    return render(
        request,
        "core/settings_email_validation.html",
        {"attr": attr, "attr_label": attr_label, "value": value, **settings_context("emails")},
    )


def settings_keys(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("home")

    data = fu._user_data

    gpg = _data_get(data, "fasGPGKeyId", [])
    ssh = _data_get(data, "ipasshpubkey", [])
    if isinstance(gpg, str):
        gpg = [gpg]
    if isinstance(ssh, str):
        ssh = [ssh]

    initial = {
        "fasGPGKeyId": "\n".join(gpg or []),
        "ipasshpubkey": "\n".join(ssh or []),
    }

    form = KeysForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        direct_updates: dict[str, object] = {}
        addattrs: list[str] = []
        setattrs: list[str] = []
        delattrs: list[str] = []

        _add_change_list_setattr(
            addattrs=addattrs,
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasGPGKeyId",
            current_values=_data_get(data, "fasGPGKeyId", []),
            new_values=_split_lines(form.cleaned_data["fasGPGKeyId"]),
        )
        _add_change_list_setattr(
            addattrs=addattrs,
            setattrs=setattrs,
            delattrs=delattrs,
            attr="ipasshpubkey",
            current_values=_data_get(data, "ipasshpubkey", []),
            new_values=_split_lines(form.cleaned_data["ipasshpubkey"]),
        )

        try:
            if not direct_updates and not addattrs and not setattrs and not delattrs:
                messages.info(request, "No changes to save.")
                return redirect("settings-keys")

            skipped, applied = _update_user_attrs(
                username,
                direct_updates=direct_updates,
                addattrs=addattrs,
                setattrs=setattrs,
                delattrs=delattrs,
            )
            if skipped:
                for attr in skipped:
                    label = _form_label_for_attr(form, attr)
                    messages.warning(
                        request,
                        f"Saved, but '{label or attr}' is not editable on this FreeIPA server.",
                    )

            if applied:
                messages.success(request, "Keys updated in FreeIPA.")
            else:
                messages.info(request, "No changes were applied.")
            return redirect("settings-keys")
        except Exception as e:
            logger.exception("Failed to update keys username=%s", username)
            if settings.DEBUG:
                messages.error(request, f"Failed to update keys (debug): {e}")
            else:
                messages.error(request, "Failed to update keys due to an internal error.")

    context = {"form": form, **settings_context("keys")}
    return render(request, "core/settings_keys.html", context)


def settings_password(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    form = PasswordChangeFreeIPAForm(request.POST or None)

    using_otp = False
    try:
        client = FreeIPAUser.get_client()
        res = client.otptoken_find(o_ipatokenowner=username, o_all=True)
        using_otp = bool((res or {}).get("result"))
    except Exception:
        using_otp = False

    if request.method == "POST" and form.is_valid():
        current = form.cleaned_data["current_password"]
        otp = _normalize_str(form.cleaned_data.get("otp"))
        if otp:
            current = f"{current}{otp}"
        new = form.cleaned_data["new_password"]

        try:
            client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
            client.login(username, current)

            passwd = getattr(client, "passwd", None)
            if callable(passwd):
                try:
                    passwd(username, current, new)
                except TypeError:
                    passwd(username, o_password=current, o_new_password=new)
            else:
                client.user_mod(username, o_userpassword=new)

            messages.success(request, "Password changed.")
            return redirect("settings-password")
        except Exception as e:
            logger.exception("Failed to change password username=%s", username)
            if settings.DEBUG:
                messages.error(request, f"Failed to change password (debug): {e}")
            else:
                messages.error(request, "Failed to change password due to an internal error.")

    context = {"form": form, "using_otp": using_otp, **settings_context("password")}
    return render(request, "core/settings_password.html", context)


def settings_agreements(request: HttpRequest) -> HttpResponse:
    username = _normalize_str(request.user.get_username())
    if not username:
        messages.error(request, "Unable to determine your username.")
        return redirect("settings-profile")

    # If there are no agreements configured in FreeIPA (or none enabled), hide
    # the entire feature from the user-facing UI.
    if not has_enabled_agreements():
        return redirect("settings-profile")

    fu = _get_full_user(username)
    user_groups = fu.groups_list if fu else []

    if request.method == "POST":
        action = _normalize_str(request.POST.get("action")).lower()
        cn = _normalize_str(request.POST.get("cn"))
        if action == "sign" and cn:
            agreement = FreeIPAFASAgreement.get(cn)
            if not agreement:
                messages.error(request, "Agreement not found.")
                return redirect("settings-agreements")

            if not agreement.enabled:
                messages.error(request, "This agreement is currently disabled.")
                return redirect("settings-agreements")

            if username in set(agreement.users):
                messages.info(request, "You have already signed this agreement.")
                return redirect("settings-agreements")

            try:
                agreement.add_user(username)
                messages.success(request, "Agreement signed.")
            except Exception as e:
                logger.exception("Failed to sign agreement username=%s agreement=%s", username, cn)
                if settings.DEBUG:
                    messages.error(request, f"Failed to sign agreement (debug): {e}")
                else:
                    messages.error(request, "Failed to sign agreement due to an internal error.")
            return redirect("settings-agreements")

    agreements = list_agreements_for_user(
        username,
        user_groups=user_groups,
        include_disabled=False,
        applicable_only=False,
    )
    context = {"agreements": agreements, **settings_context("agreements")}
    return render(request, "core/settings_agreements.html", context)


def settings_agreement_detail(request: HttpRequest, cn: str) -> HttpResponse:
    username = _normalize_str(request.user.get_username())
    if not username:
        messages.error(request, "Unable to determine your username.")
        return redirect("settings-profile")

    if not has_enabled_agreements():
        return redirect("settings-profile")

    cn = _normalize_str(cn)
    if not cn:
        raise Http404("Agreement not found")

    agreement = FreeIPAFASAgreement.get(cn)
    if not agreement or not agreement.enabled:
        raise Http404("Agreement not found")

    signed = username in agreement.users

    if request.method == "POST":
        action = _normalize_str(request.POST.get("action")).lower()
        if action == "sign":
            if signed:
                messages.info(request, "You have already signed this agreement.")
                return redirect("settings-agreement-detail", cn=cn)
            try:
                agreement.add_user(username)
                messages.success(request, "Agreement signed.")
                return redirect("settings-agreement-detail", cn=cn)
            except Exception as e:
                logger.exception("Failed to sign agreement username=%s agreement=%s", username, cn)
                if settings.DEBUG:
                    messages.error(request, f"Failed to sign agreement (debug): {e}")
                else:
                    messages.error(request, "Failed to sign agreement due to an internal error.")
                return redirect("settings-agreement-detail", cn=cn)

    context = {
        "agreement": agreement,
        "signed": signed,
        **settings_context("agreements"),
    }
    return render(request, "core/settings_agreement_detail.html", context)
