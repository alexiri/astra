from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0039_add_election_quorum_remove_candidate_ordering"),
    ]

    operations = [
        migrations.AddField(
            model_name="election",
            name="eligible_group_cn",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Optional FreeIPA group CN. When set, only members of this group will receive voting credentials."
                ),
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="election",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("open", "Open"),
                    ("closed", "Closed"),
                    ("tallied", "Tallied"),
                    ("deleted", "Deleted"),
                ],
                default="draft",
                max_length=16,
            ),
        ),
    ]
