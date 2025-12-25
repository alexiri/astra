from __future__ import annotations

from collections.abc import Iterable

from django.db import migrations, models


def _backfill_membership_state(apps, schema_editor) -> None:
    Membership = apps.get_model("core", "Membership")
    MembershipLog = apps.get_model("core", "MembershipLog")

    logs: Iterable[object] = (
        MembershipLog.objects.filter(action__in=["approved", "expiry_changed", "terminated"])
        .order_by("target_username", "membership_type_id", "-created_at")
        .iterator()
    )

    seen: set[tuple[str, str]] = set()

    for log in logs:
        key = (log.target_username, log.membership_type_id)
        if key in seen:
            continue
        seen.add(key)

        # Active rows only: if the latest state change is termination, ensure
        # there is no active membership row.
        if log.action == "terminated":
            continue

        Membership.objects.update_or_create(
            target_username=log.target_username,
            membership_type_id=log.membership_type_id,
            defaults={
                "expires_at": log.expires_at,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_create_password_reset_email_template"),
    ]

    operations = [
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_username", models.CharField(max_length=255)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("membership_type", models.ForeignKey(on_delete=models.deletion.PROTECT, to="core.membershiptype")),
            ],
            options={
                "ordering": ("target_username", "membership_type_id"),
            },
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(
                fields=("target_username", "membership_type"),
                name="uniq_membership_target_username_type",
            ),
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(fields=["target_username"], name="m_tgt"),
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(fields=["expires_at"], name="m_exp_at"),
        ),
        migrations.RunPython(_backfill_membership_state, migrations.RunPython.noop),
    ]
