from __future__ import annotations

from functools import lru_cache
import locale
import zoneinfo
import re
from urllib.parse import urlparse

from django import forms

import pyotp


# Noggin-inspired nickname validation (adapted for our simpler fields)
_IRC_NICK_RE = re.compile(r"^[a-z_\[\]\\^{}|`-][a-z0-9_\[\]\\^{}|`-]*$", re.IGNORECASE)
_MATRIX_LOCALPART_RE = re.compile(r"^[a-z0-9.=_/-]+$", re.IGNORECASE)
_SERVER_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*(:[0-9]+)?$", re.IGNORECASE)

# GitHub username rules (close enough for validation UX)
_GITHUB_USERNAME_RE = re.compile(r"^(?!-)(?!.*--)[A-Za-z0-9-]{1,39}(?<!-)$")

# GitLab username rules are more permissive; keep basic constraints.
_GITLAB_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,253}[A-Za-z0-9])?$")


def _get_timezones() -> set[str]:
    return zoneinfo.available_timezones()


@lru_cache(maxsize=1)
def get_timezone_options() -> list[str]:
    # Stable ordering for template rendering.
    return sorted(_get_timezones())


@lru_cache(maxsize=1)
def get_locale_options() -> list[str]:
    # Build a suggestion list from Python's locale alias registry.
    # Keep it permissive: this is for dropdown hints only; validation remains in clean_fasLocale.
    aliases = getattr(locale, "locale_alias", {}) or {}
    candidates: set[str] = set()

    def _add(raw: str):
        v = (raw or "").strip()
        if not v:
            return
        # Normalize common forms; strip encoding and modifiers for concise suggestions.
        v = locale.normalize(v)
        v = v.split(".", 1)[0]
        v = v.split("@", 1)[0]
        v = v.strip()
        if v and len(v) <= 64:
            candidates.add(v)

    for k, v in aliases.items():
        _add(k)
        _add(v)

    return sorted(candidates)

def _is_valid_locale_code(value: str) -> bool:
    # Use Python's locale alias registry. This is not the same as "installed locales",
    # but it is an official reference source and avoids hardcoding.
    v = (value or "").strip()
    if not v:
        return True

    # Normalize common inputs like en_US.UTF-8 -> en_US.utf8
    normalized = locale.normalize(v)

    # locale.locale_alias keys are lower-case.
    candidates = {
        v.lower(),
        normalized.lower(),
        normalized.split(".", 1)[0].lower(),
    }
    aliases = getattr(locale, "locale_alias", {}) or {}
    return any(c in aliases for c in candidates)


class _StyledForm(forms.Form):
    """Apply AdminLTE-friendly CSS classes to widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, (forms.Textarea, forms.TextInput, forms.PasswordInput, forms.EmailInput, forms.URLInput, forms.ClearableFileInput)):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def full_clean(self):
        super().full_clean()
        # After validation, mark invalid widgets so AdminLTE/Bootstrap highlight them.
        for name in self.errors.keys():
            if name not in self.fields:
                continue
            widget = self.fields[name].widget
            css = widget.attrs.get("class", "")
            if "is-invalid" not in css:
                widget.attrs["class"] = (css + " is-invalid").strip()


class ProfileForm(_StyledForm):
    # Core identity fields
    givenname = forms.CharField(
        label="First Name",
        required=True,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    sn = forms.CharField(
        label="Last Name",
        required=True,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )

    # Fedora freeipa-fas schema (attribute names are case-insensitive in LDAP)
    fasPronoun = forms.CharField(
        label="Pronouns",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "she / her / hers, they / them / theirs",
                "autocomplete": "off",
                "list": "pronoun-options",
                "autocapitalize": "off",
            }
        ),
        help_text="Comma-separated.",
    )
    fasLocale = forms.ChoiceField(
        label="Locale",
        required=False,
        help_text="Example: en_US",
        choices=(),
    )
    fasTimezone = forms.ChoiceField(
        label="Timezone",
        required=False,
        help_text="IANA timezone like Europe/Paris",
        choices=(),
    )

    fasWebsiteUrl = forms.CharField(
        label="Website or Blog URL",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    fasRssUrl = forms.CharField(
        label="RSS URL",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    fasIRCNick = forms.CharField(
        label="Chat Nicknames",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=(
            "One per line (or comma-separated). "
            "Use URL-style values to specify protocol: "
            "irc:/nick or irc://server/nick; "
            "matrix:/nick or matrix://server/nick. "
            "(Tip: Matrix handles like @nick:server are accepted too.)"
        ),
    )

    fasGitHubUsername = forms.CharField(
        label="GitHub Username",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    fasGitLabUsername = forms.CharField(
        label="GitLab Username",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )

    fasIsPrivate = forms.BooleanField(label="Private", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def _current_value(name: str) -> str:
            if self.is_bound:
                # Bound forms should validate against the known choices.
                return ""
            v = self.initial.get(name)
            return (v or "").strip()

        def _choices(options: list[str], *, current: str) -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = [("", "—")]
            if current and current not in options:
                out.append((current, current))
            out.extend([(v, v) for v in options])
            return out

        locale_current = _current_value("fasLocale")
        timezone_current = _current_value("fasTimezone")

        self.fields["fasLocale"].choices = _choices(get_locale_options(), current=locale_current)
        self.fields["fasTimezone"].choices = _choices(get_timezone_options(), current=timezone_current)

    @staticmethod
    def _split_list_field(value: str) -> list[str]:
        out: list[str] = []
        for raw_line in (value or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for part in line.split(","):
                p = part.strip()
                if p:
                    out.append(p)
        return out

    @classmethod
    def _rejoin_lines(cls, items: list[str]) -> str:
        return "\n".join(items)

    @classmethod
    def _validate_http_urls(cls, value: str, *, field_label: str) -> str:
        # Matches freeipa-fas `fasutils.URL`: scheme must be http/https, host must be non-empty.
        # Also matches `baseruserfas.URL(... normalizer=value.strip(), maxlength=255)` per item.
        urls = [u.strip() for u in cls._split_list_field(value)]
        normalized: list[str] = []
        for u in urls:
            if not u:
                continue
            if len(u) > 255:
                raise forms.ValidationError(f"Invalid {field_label}: each URL must be at most 255 characters")
            parsed = urlparse(u)
            scheme = (parsed.scheme or "").lower()
            if scheme not in {"http", "https"}:
                raise forms.ValidationError(f"Invalid {field_label}: URL must start with http:// or https://")
            if not parsed.netloc:
                raise forms.ValidationError(f"Invalid {field_label}: empty host name")
            normalized.append(u)
        return cls._rejoin_lines(normalized)

    @classmethod
    def _validate_multivalued_maxlen(cls, value: str, *, field_label: str, maxlen: int) -> str:
        items = [i.strip() for i in cls._split_list_field(value)]
        normalized: list[str] = []
        for i in items:
            if not i:
                continue
            if len(i) > maxlen:
                raise forms.ValidationError(f"Invalid {field_label}: each value must be at most {maxlen} characters")
            normalized.append(i)
        return cls._rejoin_lines(normalized)

    @classmethod
    def _validate_gpg_key_ids(cls, value: str) -> str:
        # Matches baseruserfas: Str("fasgpgkeyid*", minlength=16, maxlength=40)
        items = [i.strip() for i in cls._split_list_field(value)]
        normalized: list[str] = []
        for i in items:
            if not i:
                continue
            if len(i) < 16 or len(i) > 40:
                raise forms.ValidationError("Invalid GPG Key IDs: each value must be 16 to 40 characters")
            normalized.append(i)
        return cls._rejoin_lines(normalized)

    def clean_fasWebsiteUrl(self):
        return self._validate_http_urls(self.cleaned_data.get("fasWebsiteUrl", ""), field_label="Website URL")

    def clean_fasRssUrl(self):
        return self._validate_http_urls(self.cleaned_data.get("fasRssUrl", ""), field_label="RSS URL")

    def clean_fasIRCNick(self):
        # baseruserfas: Str("fasircnick*", maxlength=64)
        # Noggin-style: store chat identities as URL-ish strings (irc/matrix).
        raw = self._validate_multivalued_maxlen(self.cleaned_data.get("fasIRCNick", ""), field_label="IRC nick", maxlen=64)
        items = [i.strip() for i in self._split_list_field(raw)]
        normalized: list[str] = []
        for item in items:
            if not item:
                continue
            compact = item.replace(" ", "")
            parsed = urlparse(compact)
            scheme = (parsed.scheme or "").lower()

            nick = ""
            server = ""

            if scheme in {"irc", "matrix"}:
                nick = (parsed.path or "").lstrip("/")
                if not nick and parsed.fragment:
                    nick = parsed.fragment.lstrip("#@")
                nick = nick.lstrip("@").strip()
                server = (parsed.netloc or "").strip()
            else:
                # Heuristics for common inputs:
                # - Matrix: @nick:server
                # - IRC legacy: nick or nick:server or nick@server
                if compact.startswith("@") and ":" in compact:
                    scheme = "matrix"
                    value = compact.lstrip("@").strip()
                    nick, _, server = value.partition(":")
                else:
                    scheme = "irc"
                    value = compact.lstrip("@").strip()
                    if ":" in value:
                        nick, _, server = value.partition(":")
                    elif "@" in value:
                        nick, _, server = value.partition("@")
                    else:
                        nick, server = value, ""

            if scheme == "irc":
                if not _IRC_NICK_RE.match(nick):
                    raise forms.ValidationError("This does not look like a valid IRC nickname.")
                if server and not _SERVER_RE.match(server):
                    raise forms.ValidationError("This does not look like a valid IRC server name.")
            elif scheme == "matrix":
                if not _MATRIX_LOCALPART_RE.match(nick):
                    raise forms.ValidationError("This does not look like a valid Matrix username.")
                if server and not _SERVER_RE.match(server):
                    raise forms.ValidationError("This does not look like a valid Matrix server name.")
            else:
                raise forms.ValidationError(f"Unsupported chat protocol: '{scheme}'")

            # Normalize to Noggin's stored form:
            # - matrix:/nick (no server) or matrix://server/nick
            # - irc:/nick (no server) or irc://server/nick
            if server:
                normalized.append(f"{scheme}://{server}/{nick}")
            else:
                normalized.append(f"{scheme}:/{nick}")

        return self._rejoin_lines(normalized)

    def clean_fasPronoun(self):
        # Matches baseruserfas: Str("faspronoun*", maxlength=64)
        return self._validate_multivalued_maxlen(self.cleaned_data.get("fasPronoun", ""), field_label="Pronouns", maxlen=64)

    def clean_fasLocale(self):
        # Matches baseruserfas: Str("faslocale?", maxlength=64)
        value = (self.cleaned_data.get("fasLocale") or "").strip()
        if len(value) > 64:
            raise forms.ValidationError("Locale must be at most 64 characters")
        if value and not _is_valid_locale_code(value):
            raise forms.ValidationError("Locale must be a valid locale short-code")
        return value

    def clean_fasTimezone(self):
        # Matches baseruserfas: Str("fastimezone?", maxlength=64)
        value = (self.cleaned_data.get("fasTimezone") or "").strip()
        if len(value) > 64:
            raise forms.ValidationError("Timezone must be at most 64 characters")
        if value:
            tzs = _get_timezones()
            if value not in tzs:
                raise forms.ValidationError("Timezone must be a valid IANA timezone")
        return value

    def clean_fasGitHubUsername(self):
        # Matches baseruserfas normalizer=lambda value: value.strip(), maxlength=255
        value = (self.cleaned_data.get("fasGitHubUsername") or "").strip()
        value = value.lstrip("@").strip()
        if value and not _GITHUB_USERNAME_RE.match(value):
            raise forms.ValidationError("GitHub username is not valid")
        return value

    def clean_fasGitLabUsername(self):
        # Matches baseruserfas normalizer=lambda value: value.strip(), maxlength=255
        value = (self.cleaned_data.get("fasGitLabUsername") or "").strip()
        value = value.lstrip("@").strip()
        if value and not _GITLAB_USERNAME_RE.match(value):
            raise forms.ValidationError("GitLab username is not valid")
        return value

class EmailsForm(_StyledForm):
    mail = forms.EmailField(label="E-mail Address", required=True)
    fasRHBZEmail = forms.EmailField(label="Red Hat Bugzilla Email", required=False, max_length=255)

    def clean_fasRHBZEmail(self):
        # Matches freeipa-fas userfas.check_fasuser_attr and baseruserfas normalizer strip
        value = (self.cleaned_data.get("fasRHBZEmail") or "").strip()
        return value


class KeysForm(_StyledForm):
    fasGPGKeyId = forms.CharField(
        label="GPG Key IDs",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One per line.",
    )
    ipasshpubkey = forms.CharField(
        label="SSH Public Keys",
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="One per block/line.",
    )

    def clean_fasGPGKeyId(self):
        # baseruserfas constraints: each entry 16..40 chars
        return ProfileForm._validate_gpg_key_ids(self.cleaned_data.get("fasGPGKeyId", ""))


class OTPAddForm(_StyledForm):
    description = forms.CharField(
        label="Token name",
        required=False,
        help_text="Optional: helps you identify this token.",
    )
    password = forms.CharField(
        label="Enter your current password",
        required=True,
        widget=forms.PasswordInput,
        help_text="Please reauthenticate so we know it is you.",
    )
    otp = forms.CharField(
        label="One-Time Password",
        required=False,
        help_text="If your account already has OTP enabled, enter your current OTP.",
    )


class OTPConfirmForm(_StyledForm):
    secret = forms.CharField(widget=forms.HiddenInput, required=True)
    description = forms.CharField(widget=forms.HiddenInput, required=False)
    code = forms.CharField(
        label="Verification Code",
        required=True,
        help_text="Generate a code in your authenticator app and enter it here.",
    )

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        secret = (self.cleaned_data.get("secret") or "").strip()
        if not secret:
            raise forms.ValidationError("Could not find the token secret")

        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            raise forms.ValidationError("The code is wrong, please try again.")
        return code


class OTPTokenActionForm(_StyledForm):
    token = forms.CharField(widget=forms.HiddenInput, required=True)


class OTPTokenRenameForm(_StyledForm):
    token = forms.CharField(widget=forms.HiddenInput, required=True)
    description = forms.CharField(required=False)


class PasswordChangeFreeIPAForm(_StyledForm):
    current_password = forms.CharField(label="Current Password", widget=forms.PasswordInput)
    otp = forms.CharField(
        label="One-Time Password",
        required=False,
        help_text="If your account has OTP enabled, enter your current OTP.",
    )
    new_password = forms.CharField(label="New Password", widget=forms.PasswordInput)
    confirm_new_password = forms.CharField(label="Confirm New Password", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get("new_password")
        confirm = cleaned.get("confirm_new_password")
        if new and confirm and new != confirm:
            raise forms.ValidationError("New password fields do not match.")
        return cleaned
