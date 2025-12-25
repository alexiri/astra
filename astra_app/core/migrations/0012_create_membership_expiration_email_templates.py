from __future__ import annotations

from django.db import migrations


TEMPLATE_EXPIRING_SOON = "membership-expiring-soon"
TEMPLATE_EXPIRED = "membership-expired"


def create_membership_expiration_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    EmailTemplate.objects.update_or_create(
        name=TEMPLATE_EXPIRING_SOON,
        language="",
        default_template=None,
        defaults={
            "subject": "Membership expiring soon",
            "content": (
                "== AlmaLinux Account Services ==\n\n"
                "Hello {{ username }},\n\n"
                "Your membership ({{ membership_type }}) is expiring soon.\n\n"
                "To extend it, log in and submit a renewal request here:\n\n"
                "  {{ extend_url }}\n\n"
                "-- The AlmaLinux Team\n"
            ),
            "html_content": (
                "<p><strong>AlmaLinux Account Services</strong></p>"
                "<p>Hello {{ username }},</p>"
                "<p>Your membership (<strong>{{ membership_type }}</strong>) is expiring soon.</p>"
                "<p>To extend it, log in and submit a renewal request here:</p>"
                "<p><a href=\"{{ extend_url }}\">{{ extend_url }}</a></p>"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
            "description": "Membership expiration warning",
        },
    )

    EmailTemplate.objects.update_or_create(
        name=TEMPLATE_EXPIRED,
        language="",
        default_template=None,
        defaults={
            "subject": "Membership expired",
            "content": (
                "== AlmaLinux Account Services ==\n\n"
                "Hello {{ username }},\n\n"
                "Your membership ({{ membership_type }}) has expired.\n\n"
                "To renew it, log in and submit a renewal request here:\n\n"
                "  {{ extend_url }}\n\n"
                "-- The AlmaLinux Team\n"
            ),
            "html_content": (
                "<p><strong>AlmaLinux Account Services</strong></p>"
                "<p>Hello {{ username }},</p>"
                "<p>Your membership (<strong>{{ membership_type }}</strong>) has expired.</p>"
                "<p>To renew it, log in and submit a renewal request here:</p>"
                "<p><a href=\"{{ extend_url }}\">{{ extend_url }}</a></p>"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
            "description": "Membership expired notification",
        },
    )


def noop_reverse(apps, schema_editor):
    # Keep templates if migration is rolled back.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_membershiplog_actions_expiry_change_and_terminate"),
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(create_membership_expiration_templates, noop_reverse),
    ]
