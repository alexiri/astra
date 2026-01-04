from __future__ import annotations

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SendMailPermissionMigrationTests(TransactionTestCase):
    def test_permission_grants_migrate_to_sendmail_codename(self) -> None:
        executor = MigrationExecutor(connection)

        before = ("core", "0043_update_email_templates_and_remove_membership_request_approved")
        executor.migrate([before])

        before_state = executor.loader.project_state([before])
        Grant = before_state.apps.get_model("core", "FreeIPAPermissionGrant")

        # Add an extra old grant to prove we update all principals, not just the seeded one.
        Grant.objects.create(
            permission="astra.add_mailmerge",
            principal_type="group",
            principal_name="example-group",
        )

        # Create a conflicting already-new grant to ensure the migration handles duplicates.
        Grant.objects.get_or_create(
            permission="astra.add_sendmail",
            principal_type="group",
            principal_name="membership-committee",
        )

        leaves = [node for node in executor.loader.graph.leaf_nodes() if node[0] == "core"]
        self.assertEqual(len(leaves), 1)
        after = leaves[0]
        executor.migrate([after])

        executor = MigrationExecutor(connection)
        after_state = executor.loader.project_state([after])
        GrantAfter = after_state.apps.get_model("core", "FreeIPAPermissionGrant")

        self.assertFalse(GrantAfter.objects.filter(permission="astra.add_mailmerge").exists())

        # Seeded grant and our extra grant should now be under the new codename.
        self.assertTrue(
            GrantAfter.objects.filter(
                permission="astra.add_sendmail",
                principal_type="group",
                principal_name="membership-committee",
            ).exists()
        )
        self.assertTrue(
            GrantAfter.objects.filter(
                permission="astra.add_sendmail",
                principal_type="group",
                principal_name="example-group",
            ).exists()
        )

        # Conflicting already-new row should have been de-duped.
        self.assertEqual(
            GrantAfter.objects.filter(
                permission="astra.add_sendmail",
                principal_type="group",
                principal_name="membership-committee",
            ).count(),
            1,
        )
