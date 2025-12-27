from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


def _membershiprequest_responses_dict_to_list(apps, schema_editor) -> None:
    MembershipRequest = apps.get_model("core", "MembershipRequest")
    for mr in MembershipRequest.objects.all().only("pk", "responses"):
        r = mr.responses
        if r is None:
            mr.responses = []
            mr.save(update_fields=["responses"])
            continue
        if isinstance(r, list):
            continue
        if isinstance(r, dict):
            mr.responses = [{str(k): "" if v is None else str(v)} for k, v in r.items()]
            mr.save(update_fields=["responses"])
            continue
        mr.responses = [{"value": str(r)}]
        mr.save(update_fields=["responses"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_create_freeipa_permission_grants"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="membershiprequest",
            name="uniq_membershiprequest_requested_username",
        ),
        migrations.AddField(
            model_name="membershiprequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("ignored", "Ignored"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="membershiprequest",
            name="decided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="membershiprequest",
            name="decided_by_username",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="membershiprequest",
            name="responses",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(_membershiprequest_responses_dict_to_list, reverse_code=migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="membershiprequest",
            constraint=models.UniqueConstraint(
                fields=("requested_username", "membership_type"),
                condition=Q(status="pending"),
                name="uniq_membershiprequest_open_user_type",
            ),
        ),
        migrations.AddIndex(
            model_name="membershiprequest",
            index=models.Index(fields=["status", "requested_at"], name="mr_status_at"),
        ),
        migrations.AddIndex(
            model_name="membershiprequest",
            index=models.Index(fields=["requested_username", "status"], name="mr_user_status"),
        ),
        migrations.AddField(
            model_name="membershiplog",
            name="membership_request",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="logs",
                to="core.membershiprequest",
            ),
        ),
    ]
