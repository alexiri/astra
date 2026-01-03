from __future__ import annotations

from django.db import migrations, models

import core.models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0040_add_election_deleted_and_eligible_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="election",
            name="public_ballots_file",
            field=models.FileField(
                blank=True,
                default="",
                upload_to=core.models.election_artifact_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="election",
            name="public_audit_file",
            field=models.FileField(
                blank=True,
                default="",
                upload_to=core.models.election_artifact_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="election",
            name="artifacts_generated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
