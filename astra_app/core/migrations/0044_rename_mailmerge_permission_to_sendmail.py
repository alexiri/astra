from __future__ import annotations

from django.db import migrations


_OLD_PERMISSION = "astra.add_mailmerge"
_NEW_PERMISSION = "astra.add_sendmail"


def _rename_permission_forward(apps, schema_editor) -> None:
    FreeIPAPermissionGrant = apps.get_model("core", "FreeIPAPermissionGrant")

    for grant in FreeIPAPermissionGrant.objects.filter(permission=_OLD_PERMISSION).iterator():
        already_exists = FreeIPAPermissionGrant.objects.filter(
            permission=_NEW_PERMISSION,
            principal_type=grant.principal_type,
            principal_name=grant.principal_name,
        ).exists()

        if already_exists:
            grant.delete()
            continue

        grant.permission = _NEW_PERMISSION
        grant.save(update_fields=["permission"])


def _rename_permission_reverse(apps, schema_editor) -> None:
    FreeIPAPermissionGrant = apps.get_model("core", "FreeIPAPermissionGrant")

    for grant in FreeIPAPermissionGrant.objects.filter(permission=_NEW_PERMISSION).iterator():
        already_exists = FreeIPAPermissionGrant.objects.filter(
            permission=_OLD_PERMISSION,
            principal_type=grant.principal_type,
            principal_name=grant.principal_name,
        ).exists()

        if already_exists:
            grant.delete()
            continue

        grant.permission = _OLD_PERMISSION
        grant.save(update_fields=["permission"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0043_update_email_templates_and_remove_membership_request_approved"),
    ]

    operations = [
        migrations.RunPython(_rename_permission_forward, _rename_permission_reverse),
    ]
