from __future__ import annotations

import datetime
from io import BytesIO
from typing import override

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.utils import timezone
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


class MembershipRequest(models.Model):
    requested_username = models.CharField(max_length=255)
    membership_type = models.ForeignKey(MembershipType, on_delete=models.PROTECT)
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["requested_username"],
                name="uniq_membershiprequest_requested_username",
            ),
        ]
        indexes = [
            models.Index(fields=["requested_at"], name="mr_req_at"),
        ]
        ordering = ("-requested_at",)

    def __str__(self) -> str:
        return f"{self.requested_username} → {self.membership_type_id}"


class MembershipLog(models.Model):
    class Action(models.TextChoices):
        requested = "requested", "Requested"
        approved = "approved", "Approved"
        rejected = "rejected", "Rejected"
        ignored = "ignored", "Ignored"
        expiry_changed = "expiry_changed", "Expiry changed"
        terminated = "terminated", "Terminated"

    actor_username = models.CharField(max_length=255)
    target_username = models.CharField(max_length=255)
    membership_type = models.ForeignKey(MembershipType, on_delete=models.PROTECT)
    requested_group_cn = models.CharField(max_length=255, blank=True, default="")
    action = models.CharField(max_length=32, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    rejection_reason = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["target_username", "created_at"], name="ml_tgt_at"),
            models.Index(fields=["target_username", "action", "created_at"], name="ml_tgt_act_at"),
            models.Index(fields=["expires_at"], name="ml_exp_at"),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.action}: {self.target_username} ({self.membership_type_id})"

    @classmethod
    def expiry_for_approval_at(
        cls,
        *,
        approved_at: datetime.datetime,
        previous_expires_at: datetime.datetime | None = None,
    ) -> datetime.datetime:
        # If we're extending an existing membership, preserve the existing
        # expiration timestamp as the base so the new term starts when the
        # previous one ends.
        if previous_expires_at is not None and previous_expires_at > approved_at:
            base = previous_expires_at
        else:
            # For a new approval, treat the approval as granting the rest of the
            # day, so the initial expiration is end-of-day (UTC) on the
            # corresponding date.
            base = datetime.datetime.combine(
                approved_at.astimezone(datetime.UTC).date(),
                datetime.time(23, 59, 59),
                tzinfo=datetime.UTC,
            )

        return base + datetime.timedelta(days=settings.MEMBERSHIP_VALIDITY_DAYS)

    @classmethod
    def create_for_request(
        cls,
        *,
        actor_username: str,
        target_username: str,
        membership_type: MembershipType,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.requested,
        )

    @classmethod
    def create_for_approval(
        cls,
        *,
        actor_username: str,
        target_username: str,
        membership_type: MembershipType,
        previous_expires_at: datetime.datetime | None = None,
    ) -> MembershipLog:
        approved_at = timezone.now()
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.approved,
            expires_at=cls.expiry_for_approval_at(approved_at=approved_at, previous_expires_at=previous_expires_at),
        )

    @classmethod
    def create_for_expiry_change(
        cls,
        *,
        actor_username: str,
        target_username: str,
        membership_type: MembershipType,
        expires_at: datetime.datetime,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.expiry_changed,
            expires_at=expires_at,
        )

    @classmethod
    def create_for_termination(
        cls,
        *,
        actor_username: str,
        target_username: str,
        membership_type: MembershipType,
    ) -> MembershipLog:
        terminated_at = timezone.now()
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.terminated,
            expires_at=terminated_at,
        )

    @classmethod
    def create_for_rejection(
        cls,
        *,
        actor_username: str,
        target_username: str,
        membership_type: MembershipType,
        rejection_reason: str,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.rejected,
            rejection_reason=rejection_reason,
        )

    @classmethod
    def create_for_ignore(
        cls,
        *,
        actor_username: str,
        target_username: str,
        membership_type: MembershipType,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.ignored,
        )
