from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0033_create_election_voting_credential_email_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="election",
            name="url",
            field=models.URLField(blank=True, default="", max_length=2048),
        ),
        migrations.AddField(
            model_name="candidate",
            name="nominated_by",
            field=models.CharField(
                default="",
                help_text="FreeIPA username of the person who nominated this candidate.",
                max_length=255,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="candidate",
            name="url",
            field=models.URLField(blank=True, default="", max_length=2048),
        ),
    ]
