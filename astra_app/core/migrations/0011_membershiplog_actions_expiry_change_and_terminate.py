from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_create_membership_email_templates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membershiplog",
            name="action",
            field=models.CharField(
                choices=[
                    ("requested", "Requested"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("ignored", "Ignored"),
                    ("expiry_changed", "Expiry changed"),
                    ("terminated", "Terminated"),
                ],
                max_length=32,
            ),
        ),
    ]
