from __future__ import annotations

import datetime

from django import forms
from django.forms import modelformset_factory
from django.utils import timezone

from core.models import Candidate, Election, ExclusionGroup


class ElectionDetailsForm(forms.ModelForm):
    class Meta:
        model = Election
        fields = [
            "name",
            "description",
            "url",
            "start_datetime",
            "end_datetime",
            "number_of_seats",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
            "start_datetime": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "end_datetime": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "number_of_seats": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()

        start_dt = cleaned.get("start_datetime")
        end_dt = cleaned.get("end_datetime")

        if isinstance(start_dt, datetime.datetime) and timezone.is_naive(start_dt):
            cleaned["start_datetime"] = timezone.make_aware(start_dt)
        if isinstance(end_dt, datetime.datetime) and timezone.is_naive(end_dt):
            cleaned["end_datetime"] = timezone.make_aware(end_dt)

        start_dt = cleaned.get("start_datetime")
        end_dt = cleaned.get("end_datetime")
        if isinstance(start_dt, datetime.datetime) and isinstance(end_dt, datetime.datetime):
            if end_dt <= start_dt:
                self.add_error("end_datetime", "End must be after start.")

        return cleaned


class ElectionVotingEmailForm(forms.Form):
    email_template_id = forms.IntegerField(required=False)

    subject = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    html_content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
    )

    text_content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
    )


class CandidateWizardForm(forms.ModelForm):
    freeipa_username = forms.ChoiceField(required=True, choices=[], widget=forms.Select(attrs={"class": "form-control alx-select2"}))
    nominated_by = forms.ChoiceField(required=True, choices=[], widget=forms.Select(attrs={"class": "form-control alx-select2"}))

    class Meta:
        model = Candidate
        fields = [
            "freeipa_username",
            "nominated_by",
            "description",
            "url",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
        }


CandidateWizardFormSet = modelformset_factory(
    Candidate,
    form=CandidateWizardForm,
    can_delete=True,
    extra=1,
)


class ExclusionGroupWizardForm(forms.ModelForm):
    candidate_usernames = forms.MultipleChoiceField(
        required=False,
        choices=[],
        widget=forms.SelectMultiple(attrs={"class": "form-control", "multiple": "multiple", "size": "6"}),
        help_text="Select candidates included in this group.",
    )

    class Meta:
        model = ExclusionGroup
        fields = [
            "name",
            "max_elected",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Employees of X",
                }
            ),
            "max_elected": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }


ExclusionGroupWizardFormSet = modelformset_factory(
    ExclusionGroup,
    form=ExclusionGroupWizardForm,
    can_delete=True,
    extra=1,
)
