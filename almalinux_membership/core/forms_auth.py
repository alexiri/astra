from __future__ import annotations

from django import forms


class ExpiredPasswordChangeForm(forms.Form):
    username = forms.CharField(label="Username", required=True)
    current_password = forms.CharField(label="Current Password", widget=forms.PasswordInput, required=True)
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
