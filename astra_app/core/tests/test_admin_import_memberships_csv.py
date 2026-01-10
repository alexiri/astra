from __future__ import annotations

import csv
import datetime
import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.backends import FreeIPAUser
from core.membership import get_valid_memberships_for_username
from core.models import Membership, MembershipLog, MembershipRequest, MembershipType, Note


class AdminImportMembershipsCSVTests(TestCase):
    def _login_as_freeipa_admin(self, username: str = "alex") -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_dry_run_does_not_apply_changes(self) -> None:
        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        csv_content = (
            b"Name,Email,Active Member,Membership Start Date,Membership Type,Committee Notes,Why?\n"
            b"Alice,alice@example.org,Active Member,2024-01-02,individual,Imported note,Because\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
        ):
            url = reverse("admin:core_membershipcsvimportlink_import")
            resp = self.client.post(
                url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(MembershipLog.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(MembershipRequest.objects.count(), 0)
        self.assertEqual(Note.objects.count(), 0)

    def test_import_page_loads_on_get(self) -> None:
        self._login_as_freeipa_admin("alex")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )

        with patch("core.backends.FreeIPAUser.get", return_value=admin_user):
            url = reverse("admin:core_membershipcsvimportlink_import")
            resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)

    def test_live_import_creates_membership_and_unmatched_export(self) -> None:
        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        csv_content = (
            b"Name,Email,Active Member,Membership Start Date,Membership Type,Committee Notes,Why?\n"
            b"Alice,alice@example.org,Active Member,2024-01-02,individual,Imported note,Because\n"
            b"Bob,bob@example.org,Active Member,2024-01-02,individual,,\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                    # Map the membership question to a specific CSV column.
                    "q_contributions_column": "Why?",
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            # Unmatched export should be available already during the preview step.
            download_url = preview_resp.context.get("unmatched_download_url")
            self.assertTrue(download_url)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)

        # Membership created via log re-save using the provided start date.
        membership = Membership.objects.get(target_username="alice", membership_type_id="individual")
        expected_start = datetime.datetime(2024, 1, 2, 0, 0, 0, tzinfo=datetime.UTC)
        self.assertEqual(membership.created_at, expected_start)

        # Request responses captured.
        req = MembershipRequest.objects.get(requested_username="alice", membership_type_id="individual")
        self.assertEqual(req.responses, [{"Contributions": "Because"}])

        # Committee note stored on the membership request.
        self.assertTrue(
            Note.objects.filter(
                membership_request=req,
                username="alex",
                content="[Import] Imported note",
            ).exists()
        )

        with patch("core.backends.FreeIPAUser.get", side_effect=_get_user):
            download_resp = self.client.get(download_url)
        self.assertEqual(download_resp.status_code, 200)

        decoded = download_resp.content.decode("utf-8")
        self.assertIn("bob@example.org", decoded)

        reader = csv.DictReader(io.StringIO(decoded))
        self.assertEqual(
            reader.fieldnames,
            [
                "Name",
                "Email",
                "Active Member",
                "Membership Start Date",
                "Membership Type",
                "Committee Notes",
                "Why?",
                "reason",
            ],
        )

        rows = list(reader)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Name"], "Bob")
        self.assertEqual(rows[0]["Email"], "bob@example.org")
        self.assertEqual(rows[0]["Active Member"], "Active Member")
        self.assertEqual(rows[0]["Membership Start Date"], "2024-01-02")
        self.assertEqual(rows[0]["Membership Type"], "individual")
        self.assertEqual(rows[0]["Committee Notes"], "")
        self.assertEqual(rows[0]["Why?"], "")
        self.assertEqual(rows[0]["reason"], "No FreeIPA user with this email")

    def test_live_import_mirror_question_columns_are_used(self) -> None:
        MembershipType.objects.update_or_create(
            code="mirror",
            defaults={
                "name": "Mirror",
                "group_cn": "almalinux-mirror",
                "isIndividual": False,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        csv_content = (
            b"Email,Active Member,Membership Start Date,Membership Type,Domain,Pull request,Additional info\n"
            b"alice@example.org,Active Member,2024-01-02,mirror,mirror.example.org,https://github.com/AlmaLinux/mirrors/pull/1,Some notes\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "mirror",
                    "import_file": uploaded,
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "mirror"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)

        req = MembershipRequest.objects.get(requested_username="alice", membership_type_id="mirror")
        self.assertEqual(
            req.responses,
            [
                {"Domain": "mirror.example.org"},
                {"Pull request": "https://github.com/AlmaLinux/mirrors/pull/1"},
                {"Additional info": "Some notes"},
            ],
        )

    def test_live_import_without_active_member_column_imports_rows(self) -> None:
        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        # This CSV intentionally omits an Active Member column. In this format,
        # every row should be treated as eligible for import.
        csv_content = (
            b"Email,Start date,Notes\n"
            b"alice@example.org,2024-01-02,Imported note\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Membership.objects.filter(target_username="alice", membership_type_id="individual").exists()
        )
    def test_live_import_old_start_date_still_creates_valid_membership(self) -> None:
        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        # The profile view only shows unexpired memberships. If the CSV start
        # date is a "member since" value far in the past, the import must not
        # backdate the approval time used for expiry calculations.
        old_start_date = (timezone.now() - datetime.timedelta(days=800)).date().isoformat().encode("utf-8")
        csv_content = b"Email,Start date,Notes\n" + b"alice@example.org," + old_start_date + b",Imported note\n"
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Membership.objects.filter(target_username="alice", membership_type_id="individual").exists())
        self.assertEqual(len(get_valid_memberships_for_username("alice")), 1)

    def test_live_import_does_not_skip_expired_membership_row(self) -> None:
        membership_type, _ = MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        Membership.objects.create(
            target_username="alice",
            membership_type=membership_type,
            expires_at=timezone.now() - datetime.timedelta(days=1),
        )

        self._login_as_freeipa_admin("alex")

        old_start_date = (timezone.now() - datetime.timedelta(days=800)).date().isoformat().encode("utf-8")
        csv_content = b"Email,Start date,Notes\n" + b"alice@example.org," + old_start_date + b",Imported note\n"
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(get_valid_memberships_for_username("alice")), 1)

    def test_live_import_reuses_existing_pending_request_without_null_requested_at(self) -> None:
        """CSV import should be idempotent when a pending request already exists."""

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        # Existing pending request which the import should reuse.
        existing = MembershipRequest.objects.create(
            requested_username="alice",
            membership_type_id="individual",
            status=MembershipRequest.Status.pending,
            responses=[{"Existing": "Yes"}],
        )
        # Make the timestamp deterministic.
        MembershipRequest.objects.filter(pk=existing.pk).update(
            requested_at=datetime.datetime(2023, 12, 1, 0, 0, 0, tzinfo=datetime.UTC)
        )

        csv_content = (
            b"Email,Start date,Notes,Why?\n"
            b"alice@example.org,2024-01-02,Imported note,Because\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)

        # Still one request, not a duplicate.
        self.assertEqual(
            MembershipRequest.objects.filter(
                requested_username="alice",
                membership_type_id="individual",
                status=MembershipRequest.Status.pending,
            ).count(),
            0,
        )

        req = MembershipRequest.objects.get(pk=existing.pk)
        expected_start = datetime.datetime(2024, 1, 2, 0, 0, 0, tzinfo=datetime.UTC)
        self.assertEqual(req.requested_at, expected_start)
        # Responses are merged.
        self.assertIn({"Existing": "Yes"}, req.responses)
        self.assertIn({"Why?": "Because"}, req.responses)

        self.assertTrue(
            Membership.objects.filter(target_username="alice", membership_type_id="individual").exists()
        )

    def test_live_import_succeeds_if_user_already_in_freeipa_group(self) -> None:
        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        csv_content = (
            b"Email,Start date,Notes\n"
            b"alice@example.org,2024-01-02,Imported note\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        # alice is already in the target group.
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": ["almalinux-individual"],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Membership.objects.filter(target_username="alice", membership_type_id="individual").exists()
        )

    def test_group_add_failure_does_not_set_note(self) -> None:
        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        csv_content = (
            b"Email,Start date,Notes\n"
            b"alice@example.org,2024-01-02,Imported note\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True, side_effect=RuntimeError("boom")),
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )

            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)
        req = MembershipRequest.objects.filter(requested_username="alice", membership_type_id="individual").first()
        if req is not None:
            self.assertFalse(
                Note.objects.filter(
                    membership_request=req,
                    username="alex",
                    content="[Import] Imported note",
                ).exists()
            )
        self.assertFalse(
            Membership.objects.filter(target_username="alice", membership_type_id="individual").exists()
        )

    def test_live_import_creates_request_and_requested_log(self) -> None:
        """CSV import should follow the same workflow as user requests.

        Specifically: create a MembershipRequest + a "requested" MembershipLog,
        then approve it (without emailing the user).
        """

        MembershipType.objects.update_or_create(
            code="individual",
            defaults={
                "name": "Individual",
                "group_cn": "almalinux-individual",
                "isIndividual": True,
                "isOrganization": False,
                "enabled": True,
                "sort_order": 0,
            },
        )

        self._login_as_freeipa_admin("alex")

        csv_content = (
            b"Email,Start date,Notes\n"
            b"alice@example.org,2024-01-02,Imported note\n"
        )
        uploaded = SimpleUploadedFile("members.csv", csv_content, content_type="text/csv")

        admin_user = FreeIPAUser(
            "alex",
            {
                "uid": ["alex"],
                "mail": ["alex@example.org"],
                "memberof_group": ["admins"],
            },
        )
        alice_user = FreeIPAUser(
            "alice",
            {
                "uid": ["alice"],
                "mail": ["alice@example.org"],
                "memberof_group": [],
            },
        )

        def _get_user(username: str) -> FreeIPAUser | None:
            if username == "alex":
                return admin_user
            if username == "alice":
                return alice_user
            return None

        with (
            patch("core.membership_csv_import.FreeIPAUser.all", return_value=[admin_user, alice_user]),
            patch("core.membership_csv_import.FreeIPAUser.get", side_effect=_get_user),
            patch("core.backends.FreeIPAUser.get", side_effect=_get_user),
            patch("core.membership_csv_import.missing_required_agreements_for_user_in_group", return_value=[]),
            patch.object(FreeIPAUser, "add_to_group", autospec=True),
            patch("post_office.mail.send", autospec=True) as send_mail,
        ):
            import_url = reverse("admin:core_membershipcsvimportlink_import")
            preview_resp = self.client.post(
                import_url,
                data={
                    "resource": "0",
                    "format": "0",
                    "membership_type": "individual",
                    "import_file": uploaded,
                },
                follow=False,
            )
            self.assertEqual(preview_resp.status_code, 200)
            confirm_form = preview_resp.context.get("confirm_form")
            self.assertIsNotNone(confirm_form)

            process_url = reverse("admin:core_membershipcsvimportlink_process_import")
            confirm_data = dict(confirm_form.initial)
            confirm_data["membership_type"] = "individual"
            resp = self.client.post(process_url, data=confirm_data, follow=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(MembershipRequest.objects.filter(requested_username="alice", membership_type_id="individual").exists())
        self.assertTrue(
            MembershipLog.objects.filter(
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.requested,
            ).exists()
        )
        self.assertTrue(
            MembershipLog.objects.filter(
                target_username="alice",
                membership_type_id="individual",
                action=MembershipLog.Action.approved,
            ).exists()
        )
        send_mail.assert_not_called()
