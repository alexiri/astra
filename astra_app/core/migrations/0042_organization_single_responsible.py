from __future__ import annotations

from django.db import migrations, models


def migrate_representatives_to_representative(apps, schema_editor) -> None:
    Organization = apps.get_model("core", "Organization")

    for org in Organization.objects.all():
        reps = org.representatives
        if isinstance(reps, list) and reps:
            username = str(reps[0] or "").strip()
            if username:
                Organization.objects.filter(pk=org.pk).update(representative=username)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0041_election_artifact_files"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="representative",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.RunPython(migrate_representatives_to_representative, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="organization",
            name="representatives",
        ),
    ]
