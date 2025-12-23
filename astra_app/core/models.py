from __future__ import annotations

from io import BytesIO
from typing import override

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from PIL import Image


def organization_logo_upload_to(instance: Organization, filename: str) -> str:
    # Always store organizations' logos with a deterministic name.
    # Access control (bucket policy / auth) must be the security boundary.
    return f"organizations/logos/{instance.code}.png"


class IPAUser(models.Model):
    # NOTE: Keep this model unmanaged; it mirrors FreeIPA users.
    username = models.CharField(max_length=255, primary_key=True)
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
    displayname = models.CharField(max_length=255, blank=True, default="", verbose_name="Display name")
    email = models.EmailField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    class Meta:
        managed = False
        # Make it appear where Django's default User model is listed.
        app_label = "auth"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.username

    @classmethod
    def from_freeipa(cls, user) -> IPAUser:
        # `user` is a core.backends.FreeIPAUser
        return cls(
            username=user.username,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            displayname=user.displayname or "",
            email=user.email or "",
            is_active=bool(getattr(user, "is_active", True)),
            is_staff=bool(getattr(user, "is_staff", False)),
        )


class IPAGroup(models.Model):
    # NOTE: Keep this model unmanaged; it mirrors FreeIPA groups.
    cn = models.CharField(max_length=255, primary_key=True)
    description = models.TextField(blank=True, default="")
    fas_url = models.URLField(blank=True, default="", verbose_name="FAS URL")
    fas_mailing_list = models.EmailField(blank=True, default="", verbose_name="FAS Mailing List")
    fas_discussion_url = models.URLField(blank=True, default="", verbose_name="FAS Discussion URL")
    fas_group = models.BooleanField(default=False, verbose_name="FAS Group")

    class Meta:
        managed = False
        app_label = "auth"
        verbose_name = "group"
        verbose_name_plural = "groups"

    def __str__(self) -> str:
        return self.cn

    @classmethod
    def from_freeipa(cls, group) -> IPAGroup:
        # `group` is a core.backends.FreeIPAGroup
        return cls(
            cn=group.cn,
            description=getattr(group, "description", "") or "",
            fas_url=getattr(group, "fas_url", "") or "",
            fas_mailing_list=getattr(group, "fas_mailing_list", "") or "",
            fas_discussion_url=getattr(group, "fas_discussion_url", "") or "",
            fas_group=getattr(group, "fas_group", False),
        )


class IPAFASAgreement(models.Model):
    # NOTE: Keep this model unmanaged; it mirrors FreeIPA fasagreement entries.
    cn = models.CharField(max_length=255, primary_key=True, verbose_name="Agreement name")
    description = models.TextField(blank=True, default="")
    enabled = models.BooleanField(default=True)

    class Meta:
        managed = False
        # Keep these in the same admin section as other FreeIPA-backed objects.
        app_label = "auth"
        verbose_name = "Agreement"
        verbose_name_plural = "Agreements"

    def __str__(self) -> str:
        return self.cn

    @classmethod
    def from_freeipa(cls, agreement) -> IPAFASAgreement:
        # `agreement` is a core.backends.FreeIPAFASAgreement
        # Coerce to concrete types so the Django admin list display doesn't
        # receive MagicMock values from tests or partial stubs.
        return cls(
            cn=agreement.cn,
            description=str(getattr(agreement, "description", "") or ""),
            enabled=bool(getattr(agreement, "enabled", True)),
        )


class MembershipType(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    group_cn = models.CharField(max_length=255, blank=True, default="", verbose_name="Group")
    isIndividual = models.BooleanField(default=False)
    isOrganization = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "code")

    def __str__(self) -> str:
        return f"{self.name}"


class Organization(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to=organization_logo_upload_to, blank=True, null=True)
    contact = models.EmailField(blank=True, default="")
    website = models.URLField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    representatives = models.JSONField(blank=True, default=list)

    class Meta:
        ordering = ("name", "code")

    def __str__(self) -> str:
        return f"{self.name}"

    @override
    def save(self, *args, **kwargs) -> None:
        self._convert_new_logo_upload_to_png()
        super().save(*args, **kwargs)

    def _convert_new_logo_upload_to_png(self) -> None:
        if not self.logo:
            return

        # Only convert when a new file is uploaded in this save.
        # For existing stored files, avoid implicitly downloading/re-uploading.
        if not hasattr(self.logo, "_file") or self.logo._file is None:
            return
        if not isinstance(self.logo._file, UploadedFile):
            return

        uploaded = self.logo._file
        uploaded.seek(0)
        img = Image.open(uploaded)
        img.load()

        # Normalize to PNG. Preserve alpha when possible.
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        content = ContentFile(buf.getvalue())

        # The upload_to callable ignores the provided filename and always
        # generates organizations/logos/{code}.png.
        self.logo.save(f"{self.code}.png", content, save=False)
