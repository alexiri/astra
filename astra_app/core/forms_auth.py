from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm


class FreeIPAAuthenticationForm(AuthenticationForm):
    """AuthenticationForm with a separate OTP field.

    Noggin-style behavior: if OTP is provided, append it to the password before
    calling Django's authenticate().
    """

    otp = forms.CharField(label="One-Time Password", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        # Ensure the OTP is applied before AuthenticationForm runs authenticate().
        password = (self.cleaned_data.get("password") or "")
        otp = (self.cleaned_data.get("otp") or "").strip()
        if password and otp:
            self.cleaned_data["password"] = f"{password}{otp}"
        return super().clean()


class ExpiredPasswordChangeForm(forms.Form):
    username = forms.CharField(label="Username", required=True)
    current_password = forms.CharField(label="Current Password", widget=forms.PasswordInput, required=True)
    otp = forms.CharField(label="One-Time Password", required=False)
    new_password = forms.CharField(label="New Password", widget=forms.PasswordInput, required=True)
    confirm_new_password = forms.CharField(label="Confirm New Password", widget=forms.PasswordInput, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get("new_password")
        confirm = cleaned.get("confirm_new_password")
        if new and confirm and new != confirm:
            raise forms.ValidationError("New password fields do not match.")
        return cleaned


class SyncTokenForm(forms.Form):
    """Noggin-style OTP token sync form.

    Used when a user's token has drifted and they can no longer log in.
    This posts to FreeIPA's /ipa/session/sync_token endpoint.
    """

    username = forms.CharField(label="Username", required=True)
    password = forms.CharField(label="Password", widget=forms.PasswordInput, required=True)
    first_code = forms.CharField(label="First OTP", required=True)
    second_code = forms.CharField(label="Second OTP", required=True)
    token = forms.CharField(label="Token ID", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["first_code"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["second_code"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["token"].help_text = "Optional. Leave empty to sync the default token." 

