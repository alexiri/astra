from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_remove_membershiprequest_uniq_membershiprequest_open_user_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membershiplog",
            name="target_username",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="membershiplog",
            name="target_organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="membership_logs",
                to="core.organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="membershiplog",
            constraint=models.CheckConstraint(
                condition=(
                    (Q(target_organization__isnull=True) & ~Q(target_username=""))
                    | (Q(target_organization__isnull=False) & Q(target_username=""))
                ),
                name="chk_membershiplog_exactly_one_target",
            ),
        ),
        migrations.AddIndex(
            model_name="membershiplog",
            index=models.Index(fields=["target_organization", "created_at"], name="ml_org_at"),
        ),
        migrations.AddIndex(
            model_name="membershiplog",
            index=models.Index(fields=["target_organization", "action", "created_at"], name="ml_org_act_at"),
        ),
    ]
