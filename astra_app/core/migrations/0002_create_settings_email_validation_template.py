from __future__ import annotations

from django.db import migrations


TEMPLATE_NAME = "settings-email-validation"


def create_settings_email_validation_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    subject = "Verify your email address"
    content = (
        "== AlmaLinux Accounts ==\n\n"
        "Hello {{ name }},\n\n"
        "To validate the email address {{ address }}, click on the link below:\n\n"
        "  {{ validate_url }}\n\n"
        "If you did not set the email address {{ address }} in your account {{ username }}, you can ignore this email.\n\n"
        "-- The AlmaLinux Team\n"
    )
    html_content = (
        "<p><strong>AlmaLinux Accounts</strong></p>"
        "<p>Hello {{ name }},</p>"
        "<p>To validate the email address {{ address }}, click on the link below:</p>"
        "<p><a href=\"{{ validate_url }}\">{{ validate_url }}</a></p>"
        "<p>If you did not set the email address {{ address }} in your account {{ username }}, you can ignore this email.</p>"
        "<p><em>The AlmaLinux Team</em></p>"
    )

    EmailTemplate.objects.update_or_create(
        name=TEMPLATE_NAME,
        language="",
        default_template=None,
        defaults={
            "subject": subject,
            "content": content,
            "html_content": html_content,
            "description": "Email address validation for profile changes",
        },
    )


def noop_reverse(apps, schema_editor):
    # Keep templates if migration is rolled back.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_create_registration_email_template"),
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(create_settings_email_validation_template, noop_reverse),
    ]
