from __future__ import annotations

from django.db import migrations


def create_password_reset_email_templates(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    EmailTemplate.objects.update_or_create(
        name="password-reset",
        defaults={
            "description": "Password reset email",
            "subject": "Reset your password",
            "html_content": (
                "<p>Hello {{ username }},</p>\n"
                "<p>You requested a password reset for your AlmaLinux account.</p>\n"
                "<p>Use this link to set a new password (valid for about {{ ttl_minutes }} minutes, until {{ valid_until_utc }} UTC):</p>\n"
                "<p><a href=\"{{ reset_url }}\">Reset your password</a></p>\n"
                "<p>If you did not request this, you can ignore this email.</p>\n"
            ),
            "content": (
                "Hello {{ username }},\n\n"
                "You requested a password reset for your AlmaLinux account.\n\n"
                "Reset link (valid for about {{ ttl_minutes }} minutes, until {{ valid_until_utc }} UTC):\n"
                "{{ reset_url }}\n\n"
                "If you did not request this, you can ignore this email.\n"
            ),
        },
    )

    EmailTemplate.objects.update_or_create(
        name="password-reset-success",
        defaults={
            "description": "Password reset success email",
            "subject": "Your password has been reset",
            "html_content": (
                "<p>Hello {{ username }},</p>\n"
                "<p>Your AlmaLinux account password has been reset successfully.</p>\n"
                "<p>If you did not do this, please contact support immediately.</p>\n"
                "<p>You can log in here:</p>\n"
                "<p><a href=\"{{ login_url }}\">Log in</a></p>\n"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
            "content": (
                "Hello {{ username }},\n\n"
                "Your AlmaLinux account password has been reset successfully.\n\n"
                "If you did not do this, please contact support immediately.\n\n"
                "Log in: {{ login_url }}\n\n"
                "-- The AlmaLinux Team\n"
            ),
        },
    )


def delete_password_reset_email_templates(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name__in=["password-reset", "password-reset-success"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_update_membership_expiration_email_templates_add_expires_at"),
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(create_password_reset_email_templates, delete_password_reset_email_templates),
    ]
