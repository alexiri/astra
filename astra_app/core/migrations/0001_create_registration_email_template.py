from __future__ import annotations

from django.db import migrations


TEMPLATE_NAME = "registration-email-validation"


def create_registration_email_template(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    subject = "Verify your email address"
    content = (
        "== AlmaLinux Accounts ==\n\n"
        "Hello {{ username }},\n\n"
        "This email address has been used to sign up for an AlmaLinux Account.\n\n"
        "If you did not create an account for username {{ username }}, you can ignore this email.\n\n"
        "To activate your account with username {{ username }}, click on the link below:\n\n"
        "  {{ activate_url }}\n\n"
        "This link will be valid for {{ ttl_minutes }} minutes (until {{ valid_until_utc }} UTC).\n"
        "If the link has expired, you can request a new one here:\n\n"
        "  {{ confirm_url }}\n\n"
        "-- The AlmaLinux Team\n"
    )
    html_content = (
        "<p><strong>AlmaLinux Accounts</strong></p>"
        "<p>Hello {{ username }},</p>"
        "<p>This email address has been used to sign up for an AlmaLinux Account.</p>"
        "<p>If you did not create an account for username {{ username }}, you can ignore this email.</p>"
        "<p>To activate your account with username {{ username }}, click on the link below:</p>"
        "<p><a href=\"{{ activate_url }}\">{{ activate_url }}</a></p>"
        "<p>This link will be valid for {{ ttl_minutes }} minutes (until {{ valid_until_utc }} UTC). "
        "If the link has expired, you can request a new one here: "
        "<a href=\"{{ confirm_url }}\">{{ confirm_url }}</a></p>"
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
            "description": "Registration email validation",
        },
    )


def noop_reverse(apps, schema_editor):
    # Keep the template even if migration is rolled back.
    # (Better to not delete potentially customized templates.)
    pass


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(create_registration_email_template, noop_reverse),
    ]
