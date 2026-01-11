from __future__ import annotations

import django.core.validators
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0047_add_membership_request_rfi_email_templates"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="auditlogentry",
            options={"ordering": ("timestamp", "id"), "verbose_name_plural": "Audit log entries"},
        ),
        migrations.AlterField(
            model_name="election",
            name="quorum",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="Minimum turnout percentage required to conclude the election without extension.",
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AddField(
            model_name="membershiprequest",
            name="on_hold_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name="membershiprequest",
            name="uniq_membershiprequest_open_user_type",
        ),
        migrations.RemoveConstraint(
            model_name="membershiprequest",
            name="uniq_membershiprequest_open_org_type",
        ),
        migrations.AddConstraint(
            model_name="membershiprequest",
            constraint=models.UniqueConstraint(
                fields=("requested_username", "membership_type"),
                condition=Q(status__in=["pending", "on_hold"], requested_organization__isnull=True)
                & ~Q(requested_username=""),
                name="uniq_membershiprequest_open_user_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="membershiprequest",
            constraint=models.UniqueConstraint(
                fields=("requested_organization", "membership_type"),
                condition=Q(status__in=["pending", "on_hold"], requested_organization__isnull=False),
                name="uniq_membershiprequest_open_org_type",
            ),
        ),
        migrations.AlterField(
            model_name="membershiplog",
            name="action",
            field=models.CharField(
                choices=[
                    ("requested", "Requested"),
                    ("on_hold", "On Hold"),
                    ("resubmitted", "Resubmitted"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("ignored", "Ignored"),
                    ("rescinded", "Rescinded"),
                    ("expiry_changed", "Expiry changed"),
                    ("terminated", "Terminated"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="membershiprequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("on_hold", "On Hold"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("ignored", "Ignored"),
                    ("rescinded", "Rescinded"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
    ]
