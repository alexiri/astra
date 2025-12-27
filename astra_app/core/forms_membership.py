from __future__ import annotations

from dataclasses import dataclass

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from core.membership import (
    get_extendable_membership_type_codes_for_username,
    get_valid_membership_type_codes_for_username,
)
from core.models import MembershipRequest, MembershipType


@dataclass(frozen=True, slots=True)
class _QuestionSpec:
    name: str
    title: str
    required: bool

    @property
    def field_name(self) -> str:
        return f"q_{self.name.lower().replace(' ', '_')}"


class MembershipRequestForm(forms.Form):
    _INDIVIDUAL_QUESTIONS: tuple[_QuestionSpec, ...] = (
        _QuestionSpec(
            name="Contributions",
            title=(
                "Please provide summary of contributions to the AlmaLinux Community, including links if appropriate."
            ),
            required=True,
        ),
    )

    _MIRROR_QUESTIONS: tuple[_QuestionSpec, ...] = (
        _QuestionSpec(name="Domain", title="Domain name of the mirror", required=True),
        _QuestionSpec(
            name="Pull request",
            title="Please provide a link to your pull request on https://github.com/AlmaLinux/mirrors/",
            required=True,
        ),
        _QuestionSpec(
            name="Additional info",
            title="Please, provide any additional information membership committee should know",
            required=False,
        ),
    )

    membership_type = forms.ModelChoiceField(
        queryset=MembershipType.objects.filter(enabled=True).order_by("sort_order", "code"),
        empty_label=None,
        to_field_name="code",
    )

    q_contributions = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 6}))
    q_domain = forms.CharField(required=False)
    q_pull_request = forms.CharField(required=False)
    q_additional_info = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, username: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.fields["membership_type"].widget.attrs.update({"class": "form-control w-100"})
        self.fields["q_contributions"].widget.attrs.update({"class": "form-control w-100"})
        self.fields["q_domain"].widget.attrs.update({"class": "form-control w-100"})
        self.fields["q_pull_request"].widget.attrs.update({"class": "form-control w-100"})
        self.fields["q_additional_info"].widget.attrs.update({"class": "form-control w-100"})

        # Use titles as user-facing labels.
        for spec in (*self._INDIVIDUAL_QUESTIONS, *self._MIRROR_QUESTIONS):
            self.fields[spec.field_name].label = spec.title
            self.fields[spec.field_name].required = False

        valid_codes = get_valid_membership_type_codes_for_username(username)
        extendable_codes = get_extendable_membership_type_codes_for_username(username)
        self._blocked_membership_type_codes = valid_codes - extendable_codes

        self._pending_membership_type_codes = set(
            MembershipRequest.objects.filter(
                requested_username=username,
                status=MembershipRequest.Status.pending,
            ).values_list("membership_type_id", flat=True)
        )
        self.fields["membership_type"].queryset = (
            MembershipType.objects.filter(enabled=True).filter(Q(isIndividual=True) | Q(code="mirror"))
            .exclude(code__in=self._blocked_membership_type_codes)
            .exclude(code__in=self._pending_membership_type_codes)
            .order_by("sort_order", "code")
        )

    def clean_membership_type(self) -> MembershipType:
        membership_type: MembershipType = self.cleaned_data["membership_type"]
        if membership_type.code in self._blocked_membership_type_codes:
            raise ValidationError("You already have a valid membership of that type.")
        if membership_type.code in self._pending_membership_type_codes:
            raise ValidationError("You already have a pending request of that type.")
        return membership_type

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()
        membership_type: MembershipType | None = cleaned.get("membership_type")
        if membership_type is None:
            return cleaned

        if membership_type.code == "mirror":
            specs = self._MIRROR_QUESTIONS
        else:
            specs = self._INDIVIDUAL_QUESTIONS

        for spec in specs:
            raw = cleaned.get(spec.field_name)
            value = str(raw or "").strip()
            cleaned[spec.field_name] = value
            if spec.required and not value:
                self.add_error(spec.field_name, "This field is required.")

        return cleaned

    def responses(self) -> list[dict[str, str]]:
        membership_type: MembershipType = self.cleaned_data["membership_type"]
        specs = self._MIRROR_QUESTIONS if membership_type.code == "mirror" else self._INDIVIDUAL_QUESTIONS
        out: list[dict[str, str]] = []
        for spec in specs:
            value = str(self.cleaned_data.get(spec.field_name) or "").strip()
            if value or spec.required:
                out.append({spec.name: value})
        return out


class MembershipRejectForm(forms.Form):
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class MembershipUpdateExpiryForm(forms.Form):
    expires_on = forms.DateField(required=True, widget=forms.DateInput(attrs={"type": "date"}))
