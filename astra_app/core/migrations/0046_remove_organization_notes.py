from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0045_create_membership_notes"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organization",
            name="notes",
        ),
    ]
