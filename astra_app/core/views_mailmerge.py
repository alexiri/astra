from __future__ import annotations

import csv
import io
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.validators import validate_email
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from post_office import mail
from post_office.models import EmailTemplate

from core.backends import FreeIPAGroup, FreeIPAUser
from core.permissions import ASTRA_ADD_MAILMERGE, json_permission_required
from core.templated_email import (
    create_email_template_unique,
    render_template_string,
    render_templated_email_preview,
    render_templated_email_preview_response,
    update_email_template,
)

logger = logging.getLogger(__name__)


_CSV_SESSION_KEY = "mailmerge_csv_payload_v1"
_PREVIEW_CONTEXT_SESSION_KEY = "mailmerge_preview_first_context_v1"


@dataclass(frozen=True)
class RecipientPreview:
    variables: list[tuple[str, str]]
    recipient_count: int
    first_context: dict[str, str]


def _normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return "field"
    if normalized[0].isdigit():
        return f"field_{normalized}"
    return normalized


def _unique_identifiers(names: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: dict[str, int] = {}
    for raw in names:
        base = _normalize_identifier(raw)
        n = seen.get(base, 0)
        if n == 0:
            out.append(base)
        else:
            out.append(f"{base}_{n + 1}")
        seen[base] = n + 1
    return out


def _context_for_freeipa_user(user: FreeIPAUser) -> dict[str, str]:
    return {
        "username": str(user.username or ""),
        "email": str(user.email or ""),
        "first_name": str(user.first_name or ""),
        "last_name": str(user.last_name or ""),
        "displayname": str(user.displayname or ""),
        "gecos": str(user.gecos or ""),
        "commonname": str(user.commonname or ""),
        "full_name": str(user.get_full_name() or ""),
    }


def _preview_for_group(group_cn: str) -> tuple[RecipientPreview, list[dict[str, str]]]:
    group = FreeIPAGroup.get(group_cn)
    if group is None:
        raise ValueError("Group not found.")

    usernames = sorted(group.member_usernames_recursive(), key=str.lower)
    recipients: list[dict[str, str]] = []
    for username in usernames:
        user = FreeIPAUser.get(username)
        if user is None:
            continue
        ctx = _context_for_freeipa_user(user)
        if not ctx["email"].strip():
            continue
        recipients.append(ctx)

    variables = [
        ("username", recipients[0]["username"] if recipients else ""),
        ("displayname", recipients[0]["displayname"] if recipients else ""),
        ("first_name", recipients[0]["first_name"] if recipients else ""),
        ("last_name", recipients[0]["last_name"] if recipients else ""),
        ("email", recipients[0]["email"] if recipients else ""),
        ("full_name", recipients[0]["full_name"] if recipients else ""),
    ]

    preview = RecipientPreview(
        variables=variables,
        recipient_count=len(recipients),
        first_context=recipients[0] if recipients else {},
    )
    return preview, recipients


def _detect_csv_email_var(var_names: list[str]) -> str | None:
    for v in var_names:
        if v == "email":
            return v
    return None


def _parse_csv_upload(file_obj) -> tuple[RecipientPreview, list[dict[str, str]], dict[str, str]]:
    raw = file_obj.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    sio = io.StringIO(text)
    dict_reader = csv.DictReader(sio)

    if not dict_reader.fieldnames:
        raise ValueError("CSV is empty.")

    headers = [str(h or "").strip() for h in dict_reader.fieldnames]
    if not any(headers):
        raise ValueError("CSV header row is missing.")

    var_names = _unique_identifiers(headers)
    header_to_var = {h: v for h, v in zip(headers, var_names, strict=False)}

    email_var = _detect_csv_email_var(var_names)
    if email_var is None:
        raise ValueError("CSV must contain an Email column.")

    recipients: list[dict[str, str]] = []
    for row in dict_reader:
        ctx: dict[str, str] = {}
        for header, value in (row or {}).items():
            if header is None:
                continue
            var = header_to_var.get(str(header).strip())
            if not var:
                continue
            ctx[var] = str(value or "").strip()

        if not ctx.get(email_var, "").strip():
            continue
        recipients.append(ctx)

    first = recipients[0] if recipients else {}
    variables = [(v, first.get(v, "")) for v in var_names]
    preview = RecipientPreview(variables=variables, recipient_count=len(recipients), first_context=first)
    return preview, recipients, header_to_var


def _preview_from_csv_session_payload(payload: dict[str, object]) -> tuple[RecipientPreview, list[dict[str, str]]]:
    recipients_raw = payload.get("recipients")
    if not isinstance(recipients_raw, list):
        raise ValueError("Saved CSV recipients are unavailable.")

    recipients: list[dict[str, str]] = []
    for item in recipients_raw:
        if not isinstance(item, dict):
            continue
        recipients.append({str(k): str(v or "").strip() for k, v in item.items()})

    if not recipients:
        preview = RecipientPreview(variables=[], recipient_count=0, first_context={})
        return preview, recipients

    first = recipients[0]
    # Preserve variable order if we have a mapping; otherwise show keys from first row.
    header_to_var_raw = payload.get("header_to_var")
    if isinstance(header_to_var_raw, dict):
        ordered_vars = list(header_to_var_raw.values())
    else:
        ordered_vars = list(first.keys())

    # De-dup while preserving order.
    seen: set[str] = set()
    var_names: list[str] = []
    for v in ordered_vars:
        sv = str(v)
        if not sv or sv in seen:
            continue
        seen.add(sv)
        var_names.append(sv)

    variables = [(v, first.get(v, "")) for v in var_names]
    preview = RecipientPreview(variables=variables, recipient_count=len(recipients), first_context=first)
    return preview, recipients


def _group_select_choices() -> list[tuple[str, str]]:
    groups = FreeIPAGroup.all()
    groups_sorted = sorted(groups, key=lambda g: str(g.cn).lower())
    choices: list[tuple[str, str]] = [("", "(Select a group)")]
    for g in groups_sorted:
        cn = str(g.cn or "").strip()
        if not cn:
            continue
        label = cn
        if str(g.description or "").strip():
            label = f"{cn} — {g.description}"
        choices.append((cn, label))
    return choices


def _parse_email_list(raw: str) -> list[str]:
    items = [s.strip() for s in str(raw or "").split(",")]
    emails: list[str] = []
    for item in items:
        if not item:
            continue
        validate_email(item)
        emails.append(item)
    return emails


class MailMergeForm(forms.Form):
    RECIPIENT_MODE_GROUP = "group"
    RECIPIENT_MODE_CSV = "csv"

    recipient_mode = forms.ChoiceField(
        required=False,
        choices=[(RECIPIENT_MODE_GROUP, "Group"), (RECIPIENT_MODE_CSV, "CSV")],
    )

    group_cn = forms.ChoiceField(required=False, choices=[], widget=forms.Select(attrs={"class": "form-control"}))
    csv_file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv,text/csv"}),
    )

    cc = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "cc1@example.com, cc2@example.com"}),
    )
    bcc = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "bcc1@example.com, bcc2@example.com"}),
    )

    email_template_id = forms.IntegerField(required=False)
    subject = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    html_content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 12, "class": "form-control"}),
    )
    text_content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 12, "class": "form-control"}),
    )

    action = forms.CharField(required=False)
    save_as_name = forms.CharField(required=False)

    def __init__(self, *args, group_choices: list[tuple[str, str]] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group_cn"].choices = group_choices or [("", "(Select a group)")]

    def clean_cc(self) -> list[str]:
        try:
            return _parse_email_list(str(self.cleaned_data.get("cc") or ""))
        except Exception as e:
            raise forms.ValidationError(f"Invalid CC address list: {e}") from e

    def clean_bcc(self) -> list[str]:
        try:
            return _parse_email_list(str(self.cleaned_data.get("bcc") or ""))
        except Exception as e:
            raise forms.ValidationError(f"Invalid BCC address list: {e}") from e


@permission_required(ASTRA_ADD_MAILMERGE, login_url=reverse_lazy("users"))
def mail_merge(request: HttpRequest) -> HttpResponse:
    group_choices = _group_select_choices()

    created_template_id: int | None = None

    preview: RecipientPreview | None = None
    recipients: list[dict[str, str]] = []
    header_to_var: dict[str, str] | None = None

    initial: dict[str, object] = {}

    if request.method == "POST":
        form = MailMergeForm(request.POST, request.FILES, group_choices=group_choices)
        if form.is_valid():
            group_cn = str(form.cleaned_data.get("group_cn") or "").strip()
            csv_file = form.cleaned_data.get("csv_file")
            recipient_mode = str(form.cleaned_data.get("recipient_mode") or "").strip().lower()

            cc = form.cleaned_data.get("cc") or []
            bcc = form.cleaned_data.get("bcc") or []

            try:
                if recipient_mode == MailMergeForm.RECIPIENT_MODE_GROUP:
                    if not group_cn:
                        raise ValueError("Select a group.")
                    preview, recipients = _preview_for_group(group_cn)
                elif recipient_mode == MailMergeForm.RECIPIENT_MODE_CSV:
                    if csv_file is not None:
                        preview, recipients, header_to_var = _parse_csv_upload(csv_file)
                        request.session[_CSV_SESSION_KEY] = json.dumps(
                            {
                                "header_to_var": header_to_var,
                                "recipients": recipients,
                            }
                        )
                    else:
                        raw_payload = request.session.get(_CSV_SESSION_KEY)
                        if not raw_payload:
                            raise ValueError("Upload a CSV.")
                        payload = json.loads(str(raw_payload))
                        if not isinstance(payload, dict):
                            raise ValueError("Upload a CSV.")
                        preview, recipients = _preview_from_csv_session_payload(payload)
                else:
                    raise ValueError("Choose Group or CSV recipients.")
            except ValueError as e:
                messages.error(request, str(e))
                preview = None
                recipients = []

            if preview and preview.first_context:
                request.session[_PREVIEW_CONTEXT_SESSION_KEY] = json.dumps(preview.first_context)

            action = str(form.cleaned_data.get("action") or "").strip().lower()
            subject = str(form.cleaned_data.get("subject") or "")
            html_content = str(form.cleaned_data.get("html_content") or "")
            text_content = str(form.cleaned_data.get("text_content") or "")

            selected_template_id = form.cleaned_data.get("email_template_id")
            selected_template = None
            if selected_template_id:
                selected_template = EmailTemplate.objects.filter(pk=selected_template_id).first()

            if action == "save" and selected_template is not None:
                update_email_template(
                    template=selected_template,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                )
                messages.success(request, f"Saved template: {selected_template.name}.")
            elif action == "save" and selected_template is None:
                messages.error(request, "Select a template to save, or use Save as.")

            if action == "save_as":
                raw_name = str(form.cleaned_data.get("save_as_name") or "").strip()
                if not raw_name:
                    messages.error(request, "Provide a template name for Save as.")
                else:
                    selected_template = create_email_template_unique(
                        raw_name=raw_name,
                        subject=subject,
                        html_content=html_content,
                        text_content=text_content,
                    )
                    messages.success(request, f"Created template: {selected_template.name}.")
                    created_template_id = selected_template.pk

            if action == "send":
                if preview is None or not recipients:
                    messages.error(request, "No recipients to send to.")
                else:
                    sent = 0
                    failures = 0
                    for recipient in recipients:
                        to_email = str(recipient.get("email") or "").strip()
                        if not to_email:
                            continue
                        try:
                            mail.send(
                                recipients=[to_email],
                                subject=render_template_string(subject, recipient),
                                message=render_template_string(text_content, recipient),
                                html_message=render_template_string(html_content, recipient),
                                cc=cc,
                                bcc=bcc,
                            )
                            sent += 1
                        except Exception:
                            failures += 1
                            logger.exception("Mail merge send failed email=%s", to_email)

                    if sent:
                        messages.success(request, f"Queued {sent} email{'s' if sent != 1 else ''}.")
                    if failures:
                        messages.error(request, f"Failed to queue {failures} email{'s' if failures != 1 else ''}.")

            # Re-render the page with current field values.
            initial.update(
                {
                    "recipient_mode": recipient_mode,
                    "group_cn": group_cn,
                    "cc": ", ".join(cc),
                    "bcc": ", ".join(bcc),
                    "email_template_id": selected_template.pk if selected_template else selected_template_id,
                    "subject": subject,
                    "html_content": html_content,
                    "text_content": text_content,
                }
            )

            # The template dropdown uses form.data/form.initial (not a bound field), so
            # keep form.initial in sync with our computed state.
            form.initial.update(initial)
        else:
            messages.error(request, "Fix the form errors and try again.")
            initial.update(request.POST.dict())
            form.initial.update(initial)
    else:
        form = MailMergeForm(initial=initial, group_choices=group_choices)

    # Compute templates at the end so any newly-created template is visible
    # immediately after Save as.
    templates = list(EmailTemplate.objects.all().order_by("name"))

    first_context = preview.first_context if preview else {}

    rendered_preview = {"subject": "", "html": "", "text": ""}
    if first_context and form.is_bound and form.is_valid():
        try:
            rendered_preview.update(
                render_templated_email_preview(
                    subject=str(form.cleaned_data.get("subject") or ""),
                    html_content=str(form.cleaned_data.get("html_content") or ""),
                    text_content=str(form.cleaned_data.get("text_content") or ""),
                    context=first_context,
                )
            )
        except ValueError as e:
            messages.error(request, f"Template error: {e}")

    return render(
        request,
        "core/mail_merge.html",
        {
            "form": form,
            "templates": templates,
            "preview": preview,
            "rendered_preview": rendered_preview,
            "csv_session_key": _CSV_SESSION_KEY,
            "has_saved_csv_recipients": bool(request.session.get(_CSV_SESSION_KEY)),
            "created_template_id": created_template_id,
        },
    )


@require_POST
@json_permission_required(ASTRA_ADD_MAILMERGE)
def mail_merge_render_preview(request: HttpRequest) -> JsonResponse:
    raw_context = request.session.get(_PREVIEW_CONTEXT_SESSION_KEY)
    if not raw_context:
        return JsonResponse({"error": "Load recipients first."}, status=400)

    try:
        context = json.loads(str(raw_context))
    except Exception:
        return JsonResponse({"error": "Preview context is unavailable."}, status=400)

    if not isinstance(context, dict):
        return JsonResponse({"error": "Preview context is invalid."}, status=400)

    return render_templated_email_preview_response(
        request=request,
        context={str(k): str(v) for k, v in context.items()},
    )
