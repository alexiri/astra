from __future__ import annotations

import logging
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.module_loading import import_string

from python_freeipa import ClientMeta, exceptions

from .backends import FreeIPAUser, _invalidate_user_cache, _invalidate_users_list_cache
from .forms_selfservice import (
    EmailsForm,
    KeysForm,
    OTPAddForm,
    PasswordChangeFreeIPAForm,
    ProfileForm,
)


logger = logging.getLogger(__name__)


_ATTR_NOT_ALLOWED_RE = re.compile(r"attribute\s+['\"]?([a-zA-Z0-9_-]+)['\"]?\s+not\s+allowed", re.IGNORECASE)


def _parse_not_allowed_attr(exc: Exception) -> str | None:
    message = str(exc) or ""
    m = _ATTR_NOT_ALLOWED_RE.search(message)
    if not m:
        return None
    return m.group(1)


def _data_get(data: dict, attr: str, default=None):
    # FreeIPA/JSON results typically use lower-case keys, but LDAP attr names are case-insensitive.
    if attr in data:
        return data.get(attr, default)
    return data.get(attr.lower(), default)


def _first(data: dict, key: str, default=None):
    value = _data_get(data, key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _bool_to_ipa(value: bool) -> str:
    # FreeIPA generally accepts TRUE/FALSE for LDAP boolean-ish attrs.
    return "TRUE" if value else "FALSE"


def _update_user_attrs(
    username: str,
    *,
    direct_updates: dict[str, object] | None = None,
    addattrs: list[str] | None = None,
    setattrs: list[str] | None = None,
    delattrs: list[str] | None = None,
) -> tuple[list[str], bool]:
    """Persist changes to FreeIPA.

    - Built-in user_mod options go in `direct_updates` (keys like o_givenname)
    - Generic attribute updates go via `o_addattr` / `o_setattr` / `o_delattr`

    Returns: (skipped_attrs, applied)
    - skipped_attrs: list of attribute names FreeIPA rejected as not allowed
    - applied: False if nothing was applied (e.g., all requested attrs were disallowed)
    """

    direct_updates = dict(direct_updates or {})
    addattrs = list(addattrs or [])
    setattrs = list(setattrs or [])
    delattrs = list(delattrs or [])

    def _attr_names_from_setattrs(values: list[str]) -> list[str]:
        names: list[str] = []
        for item in values:
            if "=" in item:
                names.append(item.split("=", 1)[0])
            else:
                names.append(item)
        return sorted(set(names))

    def _attr_names_from_delattrs(values: list[str]) -> list[str]:
        names: list[str] = []
        for item in values:
            if "=" in item:
                names.append(item.split("=", 1)[0])
            elif item.endswith("="):
                names.append(item[:-1])
            else:
                names.append(item)
        return sorted(set(names))

    logger.debug(
        "FreeIPA user_mod: username=%s direct_keys=%s addattr_count=%d setattr_count=%d delattr_count=%d",
        username,
        sorted(direct_updates.keys()),
        len(addattrs),
        len(setattrs),
        len(delattrs),
    )

    client = FreeIPAUser.get_client()

    skipped_attrs: list[str] = []
    attempts = 0
    working_addattrs = list(addattrs)
    working_setattrs = list(setattrs)
    working_delattrs = list(delattrs)
    internal_clear_fallback_used = False

    def _delattr_name(item: str) -> str:
        # delattr can be specified as "attr=" (clear) or "attr=value" (remove one value)
        if "=" in item:
            return item.split("=", 1)[0]
        return item[:-1] if item.endswith("=") else item

    def _filter_delattrs(values: list[str], *, remove_attr: str) -> list[str]:
        return [v for v in values if _delattr_name(v) != remove_attr]

    def _is_internal_error(exc: Exception) -> bool:
        return "internal error" in (str(exc) or "").lower()

    while True:
        attempts += 1
        call_updates = dict(direct_updates)
        if working_addattrs:
            call_updates["o_addattr"] = working_addattrs
        if working_setattrs:
            call_updates["o_setattr"] = working_setattrs
        if working_delattrs:
            call_updates["o_delattr"] = working_delattrs

        try:
            client.user_mod(username, **call_updates)
            break
        except Exception as e:
            attr = _parse_not_allowed_attr(e)
            if attr:
                # Expected on some FreeIPA deployments: certain schema attrs are not editable.
                logger.info(
                    "FreeIPA user_mod rejected attribute: username=%s attr=%s direct_keys=%s",
                    username,
                    attr,
                    sorted(direct_updates.keys()),
                )
            else:
                logger.warning(
                    "FreeIPA user_mod failed: username=%s error=%s direct_keys=%s addattr_attrs=%s setattr_attrs=%s delattr_attrs=%s",
                    username,
                    e,
                    sorted(direct_updates.keys()),
                    _attr_names_from_setattrs(working_addattrs),
                    _attr_names_from_setattrs(working_setattrs),
                    _attr_names_from_delattrs(working_delattrs),
                )

            if attr:
                if attempts >= 5:
                    raise

                new_addattrs = [s for s in working_addattrs if not s.startswith(f"{attr}=")]
                new_setattrs = [s for s in working_setattrs if not s.startswith(f"{attr}=")]
                new_delattrs = _filter_delattrs(working_delattrs, remove_attr=attr)
                if (
                    new_addattrs == working_addattrs
                    and new_setattrs == working_setattrs
                    and new_delattrs == working_delattrs
                ):
                    raise

                skipped_attrs.append(attr)
                working_addattrs = new_addattrs
                working_setattrs = new_setattrs
                working_delattrs = new_delattrs

                if not direct_updates and not working_addattrs and not working_setattrs and not working_delattrs:
                    # The only attempted changes were for attributes FreeIPA doesn't allow.
                    return skipped_attrs, False

                continue

            if (
                not internal_clear_fallback_used
                and _is_internal_error(e)
                and working_delattrs
                and not working_addattrs
                and not working_setattrs
                and all(d.endswith("=") for d in working_delattrs)
            ):
                internal_clear_fallback_used = True
                logger.warning(
                    "FreeIPA clear via delattr hit internal error; retrying via setattr: username=%s attrs=%s",
                    username,
                    _attr_names_from_delattrs(working_delattrs),
                )
                working_setattrs = list(working_delattrs)
                working_delattrs = []
                continue

            # Anything else is unexpected; keep the traceback.
            logger.exception("FreeIPA user_mod unexpected failure username=%s", username)
            raise

    # Invalidate caches so lists/details refresh immediately.
    try:
        _invalidate_user_cache(username)
        _invalidate_users_list_cache()
    except Exception:
        pass

    # Re-warm the user object so the next page load reflects the change.
    try:
        FreeIPAUser.get(username)
    except Exception:
        pass

    return skipped_attrs, True


def _normalize_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _add_change(
    *,
    updates: dict[str, object],
    delattrs: list[str],
    attr: str,
    current_value: object,
    new_value: object,
    transform=None,
):
    """Add a change for a single-valued attribute.

    - If unchanged: do nothing
    - If new is empty and current is non-empty: clear via delattr
    - Else: set via explicit option
    """

    current_s = _normalize_str(current_value)
    new_s = _normalize_str(new_value)

    if transform is not None and new_s:
        new_s = transform(new_s)

    if current_s == new_s:
        return

    if new_s == "":
        if current_s != "":
            delattrs.append(f"{attr}=")
        return

    updates[f"o_{attr}"] = new_s


def _add_change_setattr(
    *,
    setattrs: list[str],
    delattrs: list[str],
    attr: str,
    current_value: object,
    new_value: object,
    transform=None,
):
    """Add a change for an attribute using FreeIPA's generic setattr/delattr."""

    current_s = _normalize_str(current_value)
    new_s = _normalize_str(new_value)

    if transform is not None and new_s:
        new_s = transform(new_s)

    if current_s == new_s:
        return

    if new_s == "":
        if current_s != "":
            delattrs.append(f"{attr}=")
        return

    setattrs.append(f"{attr}={new_s}")


def _add_change_list(
    *,
    updates: dict[str, object],
    delattrs: list[str],
    attr: str,
    current_values: object,
    new_values: list[str],
):
    """Add a change for a multi-valued attribute."""

    if isinstance(current_values, str):
        current_list = [current_values]
    elif isinstance(current_values, list):
        current_list = [str(v) for v in current_values]
    else:
        current_list = []

    current_norm = sorted([_normalize_str(v) for v in current_list if _normalize_str(v)])
    new_norm = sorted([_normalize_str(v) for v in (new_values or []) if _normalize_str(v)])

    if current_norm == new_norm:
        return

    if not new_norm:
        if current_norm:
            delattrs.append(f"{attr}=")
        return

    updates[f"o_{attr}"] = new_norm


def _add_change_list_setattr(
    *,
    addattrs: list[str],
    setattrs: list[str],
    delattrs: list[str],
    attr: str,
    current_values: object,
    new_values: list[str],
):
    """Update a multi-valued attribute using delattr+addattr.

    Avoids `attr=` clears (which some FreeIPA deployments interpret as
    "remove value None"), by applying a diff:
    - remove values via `o_delattr: ["attr=value", ...]`
    - add values via `o_addattr: ["attr=value", ...]`
    """

    if isinstance(current_values, str):
        current_list = [current_values]
    elif isinstance(current_values, list):
        current_list = [str(v) for v in current_values]
    else:
        current_list = []

    current_norm = sorted({_normalize_str(v) for v in current_list if _normalize_str(v)})
    new_norm = sorted({_normalize_str(v) for v in (new_values or []) if _normalize_str(v)})

    if current_norm == new_norm:
        return

    # Empty field means remove all existing values explicitly.
    if not new_norm:
        for v in current_norm:
            delattrs.append(f"{attr}={v}")
        return

    to_remove = [v for v in current_norm if v not in new_norm]
    to_add = [v for v in new_norm if v not in current_norm]

    for v in to_remove:
        delattrs.append(f"{attr}={v}")
    for v in to_add:
        # IMPORTANT: o_setattr replaces values for multi-valued attrs.
        addattrs.append(f"{attr}={v}")


def _get_full_user(username: str) -> FreeIPAUser | None:
    return FreeIPAUser.get(username)


def _detect_avatar_provider(user: object, *, size: int = 140) -> tuple[str | None, str | None]:
    """Return (provider_path, avatar_url) for the first provider that yields a URL.

    This follows django-avatar's provider ordering semantics.
    """

    providers = getattr(settings, "AVATAR_PROVIDERS", ()) or ()
    for provider_path in providers:
        try:
            provider_cls = import_string(provider_path)
        except Exception:
            continue

        get_url = getattr(provider_cls, "get_avatar_url", None)
        if not callable(get_url):
            continue

        try:
            url = get_url(user, size, size)
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

    # Only these two are supported in this project.
    return None


@login_required(login_url="/login/")
def profile(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    logger.debug("Self-service profile view: username=%s", username)
    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("login")

    data = getattr(fu, "_user_data", {})

    tz_name = timezone.get_current_timezone_name()
    now_local = timezone.localtime(timezone.now())

    groups = getattr(fu, "groups_list", []) or []

    context = {
        "fu": fu,
        "groups": sorted(groups),
        "groups_count": len(groups),
        "agreements_count": 0,
        "timezone": tz_name,
        "current_time": now_local,
        "pronouns": _value_to_text(_data_get(data, "fasPronoun", "")),
    }
    return render(request, "core/profile.html", context)


@login_required(login_url="/login/")
def avatar_manage(request: HttpRequest) -> HttpResponse:
    """Redirect the user to the appropriate place to manage their avatar."""

    provider_path, _ = _detect_avatar_provider(request.user)
    manage_url = _avatar_manage_url_for_provider(provider_path)
    if manage_url:
        return redirect(manage_url)

    messages.info(request, "Your current avatar provider does not support direct avatar updates here.")
    return redirect("settings-profile")


@login_required(login_url="/login/")
def groups(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    groups = sorted(getattr(fu, "groups_list", []) or []) if fu else []
    return render(request, "core/groups.html", {"groups": groups})


def _settings_context(active_tab: str):
    return {
        "active_tab": active_tab,
    }


def _value_to_text(value: object) -> str:
    if isinstance(value, list):
        # Prefer one-per-line for multi-valued attributes.
        return "\n".join([str(v) for v in value if _normalize_str(v)])
    return _normalize_str(value)


def _value_to_csv(value: object) -> str:
    if isinstance(value, list):
        return ", ".join([str(v).strip() for v in value if _normalize_str(v)])
    s = _normalize_str(value)
    if "\n" in s:
        parts = [p.strip() for p in s.replace("\r", "").split("\n") if p.strip()]
        return ", ".join(parts)
    return s


@login_required(login_url="/login/")
def settings_profile(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("profile")

    data = getattr(fu, "_user_data", {})

    initial = {
        "givenname": getattr(fu, "first_name", "") or _first(data, "givenname", "") or "",
        "sn": getattr(fu, "last_name", "") or _first(data, "sn", "") or "",
        "fasPronoun": _value_to_csv(_data_get(data, "fasPronoun", "")),
        "fasLocale": _first(data, "fasLocale", "") or "",
        "fasTimezone": _first(data, "fasTimezone", "") or "",
        "fasWebsiteUrl": _value_to_text(_data_get(data, "fasWebsiteUrl", "")),
        "fasRssUrl": _value_to_text(_data_get(data, "fasRssUrl", "")),
        "fasIRCNick": _value_to_text(_data_get(data, "fasIRCNick", "")),
        "fasMatrix": _first(data, "fasMatrix", "") or "",
        "fasGitHubUsername": _first(data, "fasGitHubUsername", "") or "",
        "fasGitLabUsername": _first(data, "fasGitLabUsername", "") or "",
        "fasIsPrivate": (_first(data, "fasIsPrivate", "FALSE") or "FALSE").upper() == "TRUE",
    }

    form = ProfileForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        direct_updates: dict[str, object] = {}
        addattrs: list[str] = []
        setattrs: list[str] = []
        delattrs: list[str] = []

        # Required-ish core identity fields
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

        # Fedora freeipa-fas fields
        _add_change_list_setattr(
            addattrs=addattrs,
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasPronoun",
            current_values=_data_get(data, "fasPronoun", []),
            new_values=_split_list_field(form.cleaned_data["fasPronoun"]),
        )
        _add_change_setattr(setattrs=setattrs, delattrs=delattrs, attr="fasLocale", current_value=initial.get("fasLocale"), new_value=form.cleaned_data["fasLocale"])
        _add_change_setattr(setattrs=setattrs, delattrs=delattrs, attr="fasTimezone", current_value=initial.get("fasTimezone"), new_value=form.cleaned_data["fasTimezone"])

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
        _add_change_setattr(setattrs=setattrs, delattrs=delattrs, attr="fasMatrix", current_value=initial.get("fasMatrix"), new_value=form.cleaned_data["fasMatrix"])
        _add_change_setattr(setattrs=setattrs, delattrs=delattrs, attr="fasGitHubUsername", current_value=initial.get("fasGitHubUsername"), new_value=form.cleaned_data["fasGitHubUsername"])
        _add_change_setattr(setattrs=setattrs, delattrs=delattrs, attr="fasGitLabUsername", current_value=initial.get("fasGitLabUsername"), new_value=form.cleaned_data["fasGitLabUsername"])

        # Bool stored as TRUE/FALSE in FreeIPA
        current_private = bool(initial.get("fasIsPrivate"))
        new_private = bool(form.cleaned_data["fasIsPrivate"])
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

    context = {"form": form, **_settings_context("profile")}
    return render(request, "core/settings_profile.html", context)


@login_required(login_url="/login/")
def settings_emails(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("profile")

    data = getattr(fu, "_user_data", {})

    initial = {
        "mail": getattr(fu, "email", "") or _first(data, "mail", "") or "",
        "fasRHBZEmail": _first(data, "fasRHBZEmail", "") or "",
    }

    form = EmailsForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        direct_updates: dict[str, object] = {}
        setattrs: list[str] = []
        delattrs: list[str] = []

        _add_change(updates=direct_updates, delattrs=delattrs, attr="mail", current_value=initial.get("mail"), new_value=form.cleaned_data["mail"])
        _add_change_setattr(
            setattrs=setattrs,
            delattrs=delattrs,
            attr="fasRHBZEmail",
            current_value=initial.get("fasRHBZEmail"),
            new_value=form.cleaned_data["fasRHBZEmail"],
        )
        try:
            if not direct_updates and not setattrs and not delattrs:
                messages.info(request, "No changes to save.")
                return redirect("settings-emails")

            skipped, applied = _update_user_attrs(username, direct_updates=direct_updates, setattrs=setattrs, delattrs=delattrs)
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
            return redirect("settings-emails")
        except Exception as e:
            logger.exception("Failed to update email settings username=%s", username)
            if settings.DEBUG:
                messages.error(request, f"Failed to update email settings (debug): {e}")
            else:
                messages.error(request, "Failed to update email settings due to an internal error.")

    context = {"form": form, **_settings_context("emails")}
    return render(request, "core/settings_emails.html", context)


def _split_lines(value: str) -> list[str]:
    lines = [line.strip() for line in (value or "").splitlines()]
    return [line for line in lines if line]


def _split_list_field(value: str) -> list[str]:
    # Allow comma-separated in addition to newlines.
    out: list[str] = []
    for line in _split_lines(value):
        for part in line.split(","):
            p = part.strip()
            if p:
                out.append(p)
    return out


def _form_label_for_attr(form, attr: str) -> str | None:
    if attr in getattr(form, "fields", {}):
        return form.fields[attr].label or attr
    # Case-insensitive fallback.
    lower = attr.lower()
    for k, field in getattr(form, "fields", {}).items():
        if k.lower() == lower:
            return field.label or k
    return None


@login_required(login_url="/login/")
def settings_keys(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    fu = _get_full_user(username)
    if not fu:
        messages.error(request, "Unable to load your FreeIPA profile.")
        return redirect("profile")

    data = getattr(fu, "_user_data", {})

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

    context = {"form": form, **_settings_context("keys")}
    return render(request, "core/settings_keys.html", context)


@login_required(login_url="/login/")
def settings_otp(request: HttpRequest) -> HttpResponse:
    """Best-effort OTP management.

    If FreeIPA's otptoken API isn't available in python-freeipa version, this page
    will fall back to read-only messaging.
    """

    username = request.user.get_username()
    form = OTPAddForm(request.POST or None)
    tokens = []
    created = None

    try:
        client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
        client.login(settings.FREEIPA_SERVICE_USER, settings.FREEIPA_SERVICE_PASSWORD)

        find = getattr(client, "otptoken_find", None)
        if callable(find):
            res = find(o_owner=username, o_all=True)
            tokens = res.get("result", []) if isinstance(res, dict) else []

        if request.method == "POST" and form.is_valid():
            add = getattr(client, "otptoken_add", None)
            if not callable(add):
                logger.info(
                    "OTP token API not available; cannot create token username=%s",
                    username,
                )
                messages.error(
                    request,
                    "OTP token creation is not available (python-freeipa does not expose the OTP API).",
                )
                context = {"form": form, "tokens": tokens, "created": created, **_settings_context("otp")}
                return render(request, "core/settings_otp.html", context)

            # Create a basic TOTP token. FreeIPA typically returns the secret.
            desc = form.cleaned_data.get("description") or f"TOTP for {username}"
            created = add(
                o_type="totp",
                o_owner=username,
                o_description=desc,
                o_all=True,
            )
            messages.success(request, "OTP token created. Capture the secret now; it may not be shown again.")
    except exceptions.FreeIPAError as e:
        logger.warning("OTP management failed username=%s error=%s", username, e)
        if request.method == "POST":
            messages.error(request, "Failed to manage OTP tokens due to a FreeIPA error.")
    except Exception as e:
        logger.exception("OTP management failed username=%s", username)
        if request.method == "POST":
            if settings.DEBUG:
                messages.error(request, f"Failed to manage OTP tokens (debug): {e}")
            else:
                messages.error(request, "Failed to manage OTP tokens due to an internal error.")

    context = {"form": form, "tokens": tokens, "created": created, **_settings_context("otp")}
    return render(request, "core/settings_otp.html", context)


@login_required(login_url="/login/")
def settings_password(request: HttpRequest) -> HttpResponse:
    username = request.user.get_username()
    form = PasswordChangeFreeIPAForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        current = form.cleaned_data["current_password"]
        new = form.cleaned_data["new_password"]

        try:
            client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
            client.login(username, current)

            passwd = getattr(client, "passwd", None)
            if callable(passwd):
                # Try common call signatures.
                try:
                    passwd(username, current, new)
                except TypeError:
                    passwd(username, o_password=current, o_new_password=new)
            else:
                # Fallback: if API method isn't exposed, try user_mod.
                client.user_mod(username, o_userpassword=new)

            # Best-effort invalidate user cache (credential change).
            try:
                _invalidate_user_cache(username)
            except Exception:
                pass

            messages.success(request, "Password changed.")
            return redirect("settings-password")
        except Exception as e:
            logger.exception("Failed to change password username=%s", username)
            if settings.DEBUG:
                messages.error(request, f"Failed to change password (debug): {e}")
            else:
                messages.error(request, "Failed to change password due to an internal error.")

    context = {"form": form, **_settings_context("password")}
    return render(request, "core/settings_password.html", context)


@login_required(login_url="/login/")
def settings_agreements(request: HttpRequest) -> HttpResponse:
    # Placeholder: agreements are not modeled yet.
    context = {"agreements": [], **_settings_context("agreements")}
    return render(request, "core/settings_agreements.html", context)
