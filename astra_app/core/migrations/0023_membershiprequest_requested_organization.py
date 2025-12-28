from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0022_alter_freeipapermissiongrant_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membershiprequest",
            name="requested_username",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="membershiprequest",
            name="requested_organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="membership_requests",
                to="core.organization",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="membershiprequest",
            name="uniq_membershiprequest_open_user_type",
        ),
        migrations.AddConstraint(
            model_name="membershiprequest",
            constraint=models.UniqueConstraint(
                condition=Q(("status", "pending"), ("requested_organization__isnull", True)) & ~Q(("requested_username", "")),
                fields=("requested_username", "membership_type"),
                name="uniq_membershiprequest_open_user_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="membershiprequest",
            constraint=models.UniqueConstraint(
                condition=Q(("status", "pending"), ("requested_organization__isnull", False)),
                fields=("requested_organization", "membership_type"),
                name="uniq_membershiprequest_open_org_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="membershiprequest",
            constraint=models.CheckConstraint(
                condition=(
                    (Q(("requested_organization__isnull", True)) & ~Q(("requested_username", "")))
                    | (Q(("requested_organization__isnull", False)) & Q(("requested_username", "")))
                ),
                name="chk_membershiprequest_exactly_one_target",
            ),
        ),
        migrations.AddIndex(
            model_name="membershiprequest",
            index=models.Index(fields=["requested_organization", "status"], name="mr_org_status"),
        ),
    ]
