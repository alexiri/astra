from __future__ import annotations

from django.db import migrations


TEMPLATE_EXPIRING_SOON = "membership-expiring-soon"
TEMPLATE_EXPIRED = "membership-expired"


def update_membership_expiration_templates(apps, schema_editor):
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
                "Your membership ({{ membership_type }}) is expiring in {{ days}} day{{ days|pluralize }}.\n"
                "Expiration: {{ expires_at }}\n\n"
                "To extend it, log in and submit a renewal request here:\n\n"
                "  {{ extend_url }}\n\n"
                "-- The AlmaLinux Team\n"
            ),
            "html_content": (
                "<p><strong>AlmaLinux Account Services</strong></p>"
                "<p>Hello {{ username }},</p>"
                "<p>Your membership (<strong>{{ membership_type }}</strong>) is expiring in {{ days}} day{{ days|pluralize }}.</p>"
                "<p><strong>Expiration:</strong> {{ expires_at }}</p>"
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
                "Your membership ({{ membership_type }}) has expired.\n"
                "Expiration: {{ expires_at }}\n\n"
                "To renew it, log in and submit a renewal request here:\n\n"
                "  {{ extend_url }}\n\n"
                "-- The AlmaLinux Team\n"
            ),
            "html_content": (
                "<p><strong>AlmaLinux Account Services</strong></p>"
                "<p>Hello {{ username }},</p>"
                "<p>Your membership (<strong>{{ membership_type }}</strong>) has expired.</p>"
                "<p><strong>Expiration:</strong> {{ expires_at }}</p>"
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
        ("core", "0012_create_membership_expiration_email_templates"),
    ]

    operations = [
        migrations.RunPython(update_membership_expiration_templates, noop_reverse),
    ]
