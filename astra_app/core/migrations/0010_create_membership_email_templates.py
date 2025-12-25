from __future__ import annotations

from django.db import migrations


TEMPLATE_SUBMITTED = "membership-request-submitted"
TEMPLATE_APPROVED = "membership-request-approved"
TEMPLATE_REJECTED = "membership-request-rejected"


def create_membership_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    EmailTemplate.objects.update_or_create(
        name=TEMPLATE_SUBMITTED,
        language="",
        default_template=None,
        defaults={
            "subject": "Membership request received",
            "content": (
                "== AlmaLinux Account Services ==\n\n"
                "Hello {{ username }},\n\n"
                "We received your membership request ({{ membership_type }}).\n\n"
                "The membership committee will review it shortly.\n\n"
                "-- The AlmaLinux Team\n"
            ),
            "html_content": (
                "<p><strong>AlmaLinux Account Services</strong></p>"
                "<p>Hello {{ username }},</p>"
                "<p>We received your membership request (<strong>{{ membership_type }}</strong>).</p>"
                "<p>The membership committee will review it shortly.</p>"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
            "description": "Membership request submitted",
        },
    )

    EmailTemplate.objects.update_or_create(
        name=TEMPLATE_APPROVED,
        language="",
        default_template=None,
        defaults={
            "subject": "Membership approved",
            "content": (
                "== AlmaLinux Account Services ==\n\n"
                "Hello {{ username }},\n\n"
                "Your membership request ({{ membership_type }}) has been approved.\n\n"
                "-- The AlmaLinux Team\n"
            ),
            "html_content": (
                "<p><strong>AlmaLinux Account Services</strong></p>"
                "<p>Hello {{ username }},</p>"
                "<p>Your membership request (<strong>{{ membership_type }}</strong>) has been approved.</p>"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
            "description": "Membership request approved",
        },
    )

    EmailTemplate.objects.update_or_create(
        name=TEMPLATE_REJECTED,
        language="",
        default_template=None,
        defaults={
            "subject": "Membership request rejected",
            "content": (
                "== AlmaLinux Account Services ==\n\n"
                "Hello {{ username }},\n\n"
                "Your membership request ({{ membership_type }}) has been rejected.\n\n"
                "Reason: {{ rejection_reason }}\n\n"
                "-- The AlmaLinux Team\n"
            ),
            "html_content": (
                "<p><strong>AlmaLinux Account Services</strong></p>"
                "<p>Hello {{ username }},</p>"
                "<p>Your membership request (<strong>{{ membership_type }}</strong>) has been rejected.</p>"
                "<p><strong>Reason:</strong> {{ rejection_reason }}</p>"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
            "description": "Membership request rejected",
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_create_membership_request_and_log"),
    ]

    operations = [
        migrations.RunPython(create_membership_templates, noop_reverse),
    ]
