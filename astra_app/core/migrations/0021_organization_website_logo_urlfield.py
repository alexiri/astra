from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_membershiptype_description_and_votes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="website_logo",
            field=models.URLField(blank=True, default="", max_length=2048),
        ),
    ]
