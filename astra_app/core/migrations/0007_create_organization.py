from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_membershiptype_group_cn"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("code", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("logo", models.ImageField(blank=True, null=True, upload_to="organizations/logos/")),
                ("contact", models.EmailField(blank=True, default="", max_length=254)),
                ("website", models.URLField(blank=True, default="")),
                ("notes", models.TextField(blank=True, default="")),
                ("representatives", models.JSONField(blank=True, default=list)),
            ],
            options={
                "ordering": ("name", "code"),
            },
        ),
    ]
