from __future__ import annotations

from django.db import migrations


def _seed_mailmerge_permission(apps, schema_editor) -> None:
    FreeIPAPermissionGrant = apps.get_model("core", "FreeIPAPermissionGrant")

    FreeIPAPermissionGrant.objects.get_or_create(
        permission="astra.add_mailmerge",
        principal_type="group",
        principal_name="membership-committee",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0030_membershiptype_acceptance_template"),
    ]

    operations = [
        migrations.RunPython(_seed_mailmerge_permission, migrations.RunPython.noop),
    ]
