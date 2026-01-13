from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def _forward_rename_quota_reached(apps, schema_editor) -> None:
    AuditLogEntry = apps.get_model("core", "AuditLogEntry")
    AuditLogEntry.objects.filter(event_type="quota_reached").update(event_type="quorum_reached")


def _reverse_rename_quota_reached(apps, schema_editor) -> None:
    AuditLogEntry = apps.get_model("core", "AuditLogEntry")
    AuditLogEntry.objects.filter(event_type="quorum_reached").update(event_type="quota_reached")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_create_election_vote_receipt_email_template"),
    ]

    operations = [
        migrations.AlterField(
            model_name="election",
            name="number_of_seats",
            field=models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)]),
        ),
        migrations.AddField(
            model_name="election",
            name="quorum",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text="Minimum turnout percentage (0-100) required to conclude the election without extension.",
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.RemoveField(
            model_name="candidate",
            name="ordering",
        ),
        migrations.AlterModelOptions(
            name="candidate",
            options={"ordering": ("freeipa_username", "id")},
        ),
        migrations.RunPython(_forward_rename_quota_reached, _reverse_rename_quota_reached),
    ]
