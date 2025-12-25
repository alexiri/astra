from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_alter_organization_logo"),
    ]

    operations = [
        migrations.CreateModel(
            name="MembershipRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requested_username", models.CharField(max_length=255)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                (
                    "membership_type",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.membershiptype"),
                ),
            ],
            options={
                "ordering": ("-requested_at",),
            },
        ),
        migrations.CreateModel(
            name="MembershipLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_username", models.CharField(max_length=255)),
                ("target_username", models.CharField(max_length=255)),
                ("requested_group_cn", models.CharField(blank=True, default="", max_length=255)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("requested", "Requested"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("ignored", "Ignored"),
                        ],
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("rejection_reason", models.TextField(blank=True, default="")),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                (
                    "membership_type",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.membershiptype"),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="membershiprequest",
            constraint=models.UniqueConstraint(
                fields=("requested_username",),
                name="uniq_membershiprequest_requested_username",
            ),
        ),
        migrations.AddIndex(
            model_name="membershiprequest",
            index=models.Index(fields=["requested_at"], name="mr_req_at"),
        ),
        migrations.AddIndex(
            model_name="membershiplog",
            index=models.Index(fields=["target_username", "created_at"], name="ml_tgt_at"),
        ),
        migrations.AddIndex(
            model_name="membershiplog",
            index=models.Index(
                fields=["target_username", "action", "created_at"],
                name="ml_tgt_act_at",
            ),
        ),
        migrations.AddIndex(
            model_name="membershiplog",
            index=models.Index(fields=["expires_at"], name="ml_exp_at"),
        ),
    ]
