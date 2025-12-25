from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from core.membership import (
    get_extendable_membership_type_codes_for_username,
    get_valid_membership_type_codes_for_username,
)
from core.models import MembershipType


class MembershipRequestForm(forms.Form):
    membership_type = forms.ModelChoiceField(
        queryset=MembershipType.objects.filter(enabled=True, isIndividual=True).order_by("sort_order", "code"),
        empty_label=None,
        to_field_name="code",
    )

    def __init__(self, *args, username: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        valid_codes = get_valid_membership_type_codes_for_username(username)
        extendable_codes = get_extendable_membership_type_codes_for_username(username)
        self._blocked_membership_type_codes = valid_codes - extendable_codes
        self.fields["membership_type"].queryset = (
            MembershipType.objects.filter(enabled=True, isIndividual=True)
            .exclude(code__in=self._blocked_membership_type_codes)
            .order_by("sort_order", "code")
        )

    def clean_membership_type(self) -> MembershipType:
        membership_type: MembershipType = self.cleaned_data["membership_type"]
        if membership_type.code in self._blocked_membership_type_codes:
            raise ValidationError("You already have a valid membership of that type.")
        return membership_type


class MembershipRejectForm(forms.Form):
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class MembershipUpdateExpiryForm(forms.Form):
    expires_on = forms.DateField(required=True, widget=forms.DateInput(attrs={"type": "date"}))
