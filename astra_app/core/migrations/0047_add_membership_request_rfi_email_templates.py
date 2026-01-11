from __future__ import annotations

from django.db import migrations

from core.migration_helpers.email_template_text import text_from_html


def add_membership_request_rfi_and_embargoed_templates(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    templates: list[dict[str, str]] = [
        {
            "name": "membership-request-rejected-embargoed",
            "description": "Membership request rejected (embargoed country)",
            "subject": "Update on your AlmaLinux Foundation application",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Thank you for applying for <strong>{{ membership_type }}</strong> membership with the AlmaLinux OS Foundation.</p>\n"
                "<p>Unfortunately, due to current legal and regulatory restrictions under United States law (the Foundation is registered "
                "as a U.S. 501(c) non-profit organization), we are unable to recognize or maintain memberships or sponsorships involving "
                "certain jurisdictions.</p>\n"
                "<p>As a result, we must decline your application at this time. This decision is based solely on legal compliance "
                "requirements and is not a reflection of you or your interest in the AlmaLinux community.</p>\n"
                "<p>If applicable regulations change in the future, we would welcome the opportunity to review a new application.</p>\n"
                "<p>If you believe this decision may be in error or would like further clarification, please contact "
                "<a href=\"mailto:membership@almalinux.org\">membership@almalinux.org</a>.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "membership-request-rfi",
            "description": "Membership request request-for-information (RFI)",
            "subject": "Action required: more information needed for your membership application",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Thank you for applying for <strong>{{ membership_type }}</strong> membership with the AlmaLinux OS Foundation.</p>\n"
                "<p>To complete our review, we need a bit more information from you:</p>\n"
                "<p>{{ rfi_message }}</p>\n"
                "<p>Your application will remain pending until we receive this information.</p>\n"
                "<p>Please update your application at the following link:</p>\n"
                "<p><a href=\"{{ application_url }}\">{{ application_url }}</a></p>\n"
                "<p>If you would like any further clarification, please contact <a href=\"mailto:membership@almalinux.org\">membership@almalinux.org</a>.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "membership-request-rejected-rfi-unanswered",
            "description": "Membership request rejected (RFI unanswered)",
            "subject": "Update on your membership application",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Thank you for applying for <strong>{{ membership_type }}</strong> membership with the AlmaLinux OS Foundation.</p>\n"
                "<p>We previously requested additional information to complete our review, but did not receive a response. "
                "As a result, we are unable to approve your application at this time.</p>\n"
                "<p>Community involvement is central to our mission, and we encourage you to continue engaging with the AlmaLinux community "
                "and consider applying again in the future.</p>\n"
                "<hr>\n"
                "<h3>What does community involvement look like?</h3>\n"
                "<p>Contributions of any size matter to us. Examples include:</p>\n"
                "<ul>\n"
                "<li>Participating in our Mattermost chat or IRC</li>\n"
                "<li>Helping other users in community forums or on social media</li>\n"
                "<li>Reporting issues, submitting patches, or contributing upstream</li>\n"
                "</ul>\n"
                "<p>If you are looking for ideas, our wiki includes suggestions for how to get involved, "
                "and we are happy to support new contribution efforts.</p>\n"
                "<p>When you decide to apply again, feel free to reach out to "
                "<a href=\"mailto:membership@almalinux.org\">membership@almalinux.org</a> and tell us more about "
                "your background and community involvement. We are always happy to answer questions.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
    ]

    for spec in templates:
        html_content = spec["html_content"]
        EmailTemplate.objects.update_or_create(
            name=spec["name"],
            defaults={
                "description": spec["description"],
                "subject": spec["subject"],
                "html_content": html_content,
                "content": text_from_html(html_content),
            },
        )


def noop_reverse(apps, schema_editor) -> None:
    # Keep templates on rollback to avoid losing admin edits.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0046_remove_organization_notes"),
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(
            add_membership_request_rfi_and_embargoed_templates,
            reverse_code=noop_reverse,
        ),
    ]
