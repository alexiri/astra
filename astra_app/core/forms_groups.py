from __future__ import annotations

from urllib.parse import urlparse

from django import forms


class GroupEditForm(forms.Form):
    description = forms.CharField(
        required=False,
        label="Description",
        max_length=255,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    fas_url = forms.CharField(
        required=False,
        label="URL",
        max_length=255,
        widget=forms.URLInput(attrs={"class": "form-control", "placeholder": "https://…"}),
    )
    fas_mailing_list = forms.CharField(
        required=False,
        label="Mailing list",
        max_length=255,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "group@lists.example.org"}),
    )
    fas_discussion_url = forms.CharField(
        required=False,
        label="Discussion URL",
        max_length=255,
        widget=forms.URLInput(attrs={"class": "form-control", "placeholder": "https://…"}),
    )
    fas_irc_channels = forms.CharField(
        required=False,
        label="IRC channels",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        help_text="One per line (or comma-separated).",
    )

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

    @staticmethod
    def _validate_http_url(value: str, *, field_label: str) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        if len(v) > 255:
            raise forms.ValidationError(f"Invalid {field_label}: must be at most 255 characters")

        parsed = urlparse(v)
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise forms.ValidationError(f"Invalid {field_label}: URL must start with http:// or https://")
        if not parsed.netloc:
            raise forms.ValidationError(f"Invalid {field_label}: empty host name")
        return v

    def clean_description(self) -> str:
        return str(self.cleaned_data.get("description") or "").strip()

    def clean_fas_url(self) -> str:
        return self._validate_http_url(str(self.cleaned_data.get("fas_url") or ""), field_label="URL")

    def clean_fas_discussion_url(self) -> str:
        return self._validate_http_url(
            str(self.cleaned_data.get("fas_discussion_url") or ""),
            field_label="Discussion URL",
        )

    def clean_fas_mailing_list(self) -> str:
        v = str(self.cleaned_data.get("fas_mailing_list") or "").strip()
        if not v:
            return ""
        return forms.EmailField(required=False).clean(v)

    def clean_fas_irc_channels(self) -> list[str]:
        raw = str(self.cleaned_data.get("fas_irc_channels") or "")
        channels: list[str] = []
        for ch in self._split_list_field(raw):
            if len(ch) > 64:
                raise forms.ValidationError("Invalid IRC channels: each channel must be at most 64 characters")
            if not ch.startswith("#"):
                raise forms.ValidationError("Invalid IRC channels: channels must start with '#'")
            channels.append(ch)
        # Preserve user intent but avoid duplicates.
        seen: set[str] = set()
        unique: list[str] = []
        for ch in channels:
            if ch in seen:
                continue
            seen.add(ch)
            unique.append(ch)
        return unique
