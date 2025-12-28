from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_membershiplog_target_organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationSponsorship",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "membership_type",
                    models.ForeignKey(on_delete=models.deletion.PROTECT, to="core.membershiptype"),
                ),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="sponsorship",
                        to="core.organization",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="organizationsponsorship",
            index=models.Index(fields=["expires_at"], name="orgs_exp_at"),
        ),
    ]
