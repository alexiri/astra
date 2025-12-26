from __future__ import annotations

from django.db import migrations


def create_membership_committee_pending_requests_email_template(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    EmailTemplate.objects.update_or_create(
        name="membership-committee-pending-requests",
        defaults={
            "description": "Notify the membership committee about pending membership requests",
            "subject": "Pending membership request{{ pending_count|pluralize}} ({{ pending_count }})",
            "html_content": (
                "<p>Hello Membership Committee,</p>\n"
                "<p>There {{ pending_count|pluralize:'is,are' }} <strong>{{ pending_count }}</strong> pending membership request{{ pending_count|pluralize}}.</p>\n"
                "<p>Please review {{ pending_count|pluralize:'it,them' }} here:</p>\n"
                "<p><a href=\"{{ requests_url }}\">{{ requests_url }}</a></p>\n"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
            "content": (
                "Hello Membership Committee,\n\n"
                "There {{ pending_count|pluralize:'is,are' }} {{ pending_count }} pending membership request{{ pending_count|pluralize}}.\n\n"
                "Please review {{ pending_count|pluralize:'it,them' }} here: {{ requests_url }}\n\n"
                "-- The AlmaLinux Team\n"
            ),
        },
    )


def delete_membership_committee_pending_requests_email_template(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.filter(name="membership-committee-pending-requests").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_create_membership_state"),
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(
            create_membership_committee_pending_requests_email_template,
            delete_membership_committee_pending_requests_email_template,
        ),
    ]
