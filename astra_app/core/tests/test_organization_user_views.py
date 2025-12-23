from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.backends import FreeIPAUser


class OrganizationUserViewsTests(TestCase):
    _test_media_root = Path(mkdtemp(prefix="alx_test_media_"))
    def _login_as_freeipa_user(self, username: str) -> None:
        session = self.client.session
        session["_freeipa_username"] = username
        session.save()

    def test_representative_can_view_org_pages_notes_hidden(self) -> None:
        from core.models import Organization

        Organization.objects.create(
            code="almalinux",
            name="AlmaLinux",
            contact="contact@almalinux.org",
            website="https://almalinux.org/",
            notes="secret internal",
            representatives=["bob"],
        )

        bob = FreeIPAUser("bob", {"uid": ["bob"], "memberof_group": []})
        self._login_as_freeipa_user("bob")

        with patch("core.backends.FreeIPAUser.get", return_value=bob):
            resp = self.client.get(reverse("organizations"))
            self.assertEqual(resp.status_code, 200)

            resp = self.client.get(reverse("organization-detail", args=["almalinux"]))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "AlmaLinux")
            self.assertNotContains(resp, "secret internal")

            # Navbar should include Organizations link for authenticated users.
            self.assertContains(resp, reverse("organizations"))

    def test_representative_can_edit_org_data_notes_hidden(self) -> None:
        from core.models import Organization

        Organization.objects.create(
            code="almalinux",
            name="AlmaLinux",
            contact="contact@almalinux.org",
            website="https://almalinux.org/",
            notes="secret internal",
            representatives=["bob"],
        )

        bob = FreeIPAUser("bob", {"uid": ["bob"], "memberof_group": []})
        self._login_as_freeipa_user("bob")

        with patch("core.backends.FreeIPAUser.get", return_value=bob):
            resp = self.client.get(reverse("organization-edit", args=["almalinux"]))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "AlmaLinux")
            self.assertNotContains(resp, "notes")
            self.assertNotContains(resp, "secret internal")

            resp = self.client.post(
                reverse("organization-edit", args=["almalinux"]),
                data={
                    "name": "AlmaLinux Updated",
                    "contact": "hello@almalinux.org",
                    "website": "https://example.com/",
                },
                follow=False,
            )
        self.assertEqual(resp.status_code, 302)

        org = Organization.objects.get(code="almalinux")
        self.assertEqual(org.name, "AlmaLinux Updated")
        self.assertEqual(org.contact, "hello@almalinux.org")
        self.assertEqual(org.website, "https://example.com/")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
        MEDIA_ROOT=_test_media_root,
    )
    def test_representative_logo_upload_is_png_named_by_code(self) -> None:
        from PIL import Image

        from core.models import Organization

        Organization.objects.create(
            code="almalinux",
            name="AlmaLinux",
            representatives=["bob"],
        )

        bob = FreeIPAUser("bob", {"uid": ["bob"], "memberof_group": []})
        self._login_as_freeipa_user("bob")

        jpeg = BytesIO()
        Image.new("RGB", (2, 2), color=(200, 10, 10)).save(jpeg, format="JPEG")
        logo_upload = SimpleUploadedFile(
            "logo.jpg",
            jpeg.getvalue(),
            content_type="image/jpeg",
        )

        with patch("core.backends.FreeIPAUser.get", return_value=bob):
            resp = self.client.post(
                reverse("organization-edit", args=["almalinux"]),
                data={
                    "name": "AlmaLinux",
                    "contact": "",
                    "website": "",
                    "logo": logo_upload,
                },
                follow=False,
            )
        self.assertEqual(resp.status_code, 302)

        org = Organization.objects.get(code="almalinux")
        self.assertTrue(org.logo.name.endswith("organizations/logos/almalinux.png"))

        org.logo.open("rb")
        try:
            self.assertEqual(org.logo.read(8), b"\x89PNG\r\n\x1a\n")
        finally:
            org.logo.close()

    def test_non_representative_cannot_view_org_detail(self) -> None:
        from core.models import Organization

        Organization.objects.create(
            code="almalinux",
            name="AlmaLinux",
            contact="contact@almalinux.org",
            website="https://almalinux.org/",
            notes="secret internal",
            representatives=["bob"],
        )

        alice = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": []})
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp = self.client.get(reverse("organization-detail", args=["almalinux"]))

        self.assertEqual(resp.status_code, 404)

    def test_non_representative_cannot_edit_org(self) -> None:
        from core.models import Organization

        Organization.objects.create(
            code="almalinux",
            name="AlmaLinux",
            contact="contact@almalinux.org",
            website="https://almalinux.org/",
            notes="secret internal",
            representatives=["bob"],
        )

        alice = FreeIPAUser("alice", {"uid": ["alice"], "memberof_group": []})
        self._login_as_freeipa_user("alice")

        with patch("core.backends.FreeIPAUser.get", return_value=alice):
            resp = self.client.get(reverse("organization-edit", args=["almalinux"]))
        self.assertEqual(resp.status_code, 404)
