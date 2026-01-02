from __future__ import annotations

from django.db import migrations


def create_election_voting_credential_template(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")
    EmailTemplate.objects.update_or_create(
        name="election-voting-credential",
        defaults={
            "subject": "Voting credential for {{ election_name }}",
            "content": (
                "Hello {{ username }},\n"
                "\n"
                "Your voting credential for {{ election_name }} is:\n"
                "\n"
                "{{ credential_public_id }}\n"
                "\n"
                "Vote here (credential is prefilled in your browser; the credential is NOT sent to the server in the URL):\n"
                "{{ vote_url_with_credential_fragment }}\n"
                "\n"
                "Keep this credential private. Anyone with the credential can submit a ballot.\n"
                "Submitting again with the same credential replaces your previous ballot.\n"
            ),
            "html_content": (
                "<p>Hello {{ username }},</p>"
                "<p>Your voting credential for <strong>{{ election_name }}</strong> is:</p>"
                "<p><code style=\"font-size: 1.1em;\">{{ credential_public_id }}</code></p>"
                "<p>Vote here (credential is prefilled in your browser; the credential is NOT sent to the server in the URL):<br>"
                "<a href=\"{{ vote_url_with_credential_fragment }}\">{{ vote_url_with_credential_fragment }}</a></p>"
                "<p><strong>Keep this credential private.</strong> Anyone with the credential can submit a ballot.</p>"
                "<p>Submitting again with the same credential replaces your previous ballot.</p>"
            ),
        },
    )


def noop_reverse(*_args, **_kwargs) -> None:
    # Keep templates on rollback to avoid losing admin edits.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_election_candidate_ballot_auditlogentry_and_more"),
    ]

    operations = [
        migrations.RunPython(
            create_election_voting_credential_template,
            reverse_code=noop_reverse,
        ),
    ]
