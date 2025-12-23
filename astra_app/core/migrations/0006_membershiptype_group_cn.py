from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_create_membershiptype"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershiptype",
            name="group_cn",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Group"),
        ),
    ]
