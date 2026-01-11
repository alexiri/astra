from __future__ import annotations

from django.db import migrations


def fix_membership_reason_template_escaping(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    def update_template(*, name: str, html_old: str, html_new: str, text_old: str, text_new: str) -> None:
        tpl = EmailTemplate.objects.filter(name=name).first()
        if tpl is None:
            return

        html_content = str(tpl.html_content or "")
        text_content = str(tpl.content or "")

        updated_fields: list[str] = []

        if html_old in html_content and html_new not in html_content:
            html_content = html_content.replace(html_old, html_new)
            tpl.html_content = html_content
            updated_fields.append("html_content")

        if text_old in text_content and text_new not in text_content:
            text_content = text_content.replace(text_old, text_new)
            tpl.content = text_content
            updated_fields.append("content")

        if updated_fields:
            tpl.save(update_fields=updated_fields)

    update_template(
        name="membership-request-rejected",
        html_old="{{ rejection_reason }}",
        html_new="{{ rejection_reason_html }}",
        text_old="{{ rejection_reason }}",
        text_new="{{ rejection_reason_text }}",
    )

    update_template(
        name="membership-request-rfi",
        html_old="{{ rfi_message }}",
        html_new="{{ rfi_message_html }}",
        text_old="{{ rfi_message }}",
        text_new="{{ rfi_message_text }}",
    )


def noop_reverse(apps, schema_editor) -> None:
    return


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0048_membership_request_on_hold_and_rescinded"),
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(
            fix_membership_reason_template_escaping,
            reverse_code=noop_reverse,
        )
    ]
