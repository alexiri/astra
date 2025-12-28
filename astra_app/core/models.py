from __future__ import annotations

import datetime
from io import BytesIO
from typing import override

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.db.models import Q
from django.utils import timezone
from PIL import Image


def organization_logo_upload_to(instance: Organization, filename: str) -> str:
    # Always store organizations' logos with a deterministic name.
    # Access control (bucket policy / auth) must be the security boundary.
    return f"organizations/logos/{instance.pk}.png"


class IPAUser(models.Model):
    # NOTE: Keep this model unmanaged; it mirrors FreeIPA users.
    username = models.CharField(max_length=255, primary_key=True)
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
    displayname = models.CharField(max_length=255, blank=True, default="", verbose_name="Display name")
    email = models.EmailField(blank=True, default="")
    fasstatusnote = models.TextField(blank=True, default="", verbose_name="Note")
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
            fasstatusnote=user.fasstatusnote or "",
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
    description = models.TextField(blank=True, default="")
    votes = models.PositiveIntegerField(blank=True, default=0)
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
    name = models.CharField(max_length=255)

    business_contact_name = models.CharField(max_length=255, blank=True, default="")
    business_contact_email = models.EmailField(blank=True, default="")
    business_contact_phone = models.CharField(max_length=64, blank=True, default="")

    pr_marketing_contact_name = models.CharField(max_length=255, blank=True, default="")
    pr_marketing_contact_email = models.EmailField(blank=True, default="")
    pr_marketing_contact_phone = models.CharField(max_length=64, blank=True, default="")

    technical_contact_name = models.CharField(max_length=255, blank=True, default="")
    technical_contact_email = models.EmailField(blank=True, default="")
    technical_contact_phone = models.CharField(max_length=64, blank=True, default="")

    membership_level = models.ForeignKey(
        MembershipType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="organizations",
        limit_choices_to={"isOrganization": True},
    )

    website_logo = models.URLField(blank=True, default="", max_length=2048)

    website = models.URLField(blank=True, default="")
    logo = models.ImageField(
        upload_to=organization_logo_upload_to,
        blank=True,
        null=True,
    )

    additional_information = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    representatives = models.JSONField(blank=True, default=list)

    class Meta:
        ordering = ("name", "id")

    def __str__(self) -> str:
        return f"{self.name}"

    @override
    def save(self, *args, **kwargs) -> None:
        if self.pk is None and self.logo:
            # The storage path is based on the autoincrement PK; ensure we have
            # one before writing the file.
            pending_logo = self.logo
            self.logo = None
            super().save(*args, **kwargs)
            self.logo = pending_logo

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
        # generates organizations/logos/{pk}.png.
        self.logo.save(f"{self.pk}.png", content, save=False)


class OrganizationSponsorship(models.Model):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="sponsorship",
    )
    membership_type = models.ForeignKey(MembershipType, on_delete=models.PROTECT)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["expires_at"], name="orgs_exp_at"),
        ]

    def __str__(self) -> str:
        return f"{self.organization_id} ({self.membership_type_id})"


class MembershipRequest(models.Model):
    class Status(models.TextChoices):
        pending = "pending", "Pending"
        approved = "approved", "Approved"
        rejected = "rejected", "Rejected"
        ignored = "ignored", "Ignored"

    requested_username = models.CharField(max_length=255, blank=True, default="")
    requested_organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="membership_requests",
    )
    requested_organization_code = models.CharField(max_length=64, blank=True, default="")
    requested_organization_name = models.CharField(max_length=255, blank=True, default="")
    membership_type = models.ForeignKey(MembershipType, on_delete=models.PROTECT)
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.pending, db_index=True)
    decided_at = models.DateTimeField(blank=True, null=True)
    decided_by_username = models.CharField(max_length=255, blank=True, default="")
    responses = models.JSONField(blank=True, default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["requested_username", "membership_type"],
                condition=Q(status="pending", requested_organization__isnull=True) & ~Q(requested_username=""),
                name="uniq_membershiprequest_open_user_type",
            ),
            models.UniqueConstraint(
                fields=["requested_organization", "membership_type"],
                condition=Q(status="pending", requested_organization__isnull=False),
                name="uniq_membershiprequest_open_org_type",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        Q(requested_organization__isnull=True)
                        & Q(requested_organization_code="")
                        & ~Q(requested_username="")
                    )
                    | (
                        Q(requested_username="")
                        & (Q(requested_organization__isnull=False) | ~Q(requested_organization_code=""))
                    )
                ),
                name="chk_membershiprequest_exactly_one_target",
            ),
        ]
        indexes = [
            models.Index(fields=["requested_at"], name="mr_req_at"),
            models.Index(fields=["status", "requested_at"], name="mr_status_at"),
            models.Index(fields=["requested_username", "status"], name="mr_user_status"),
            models.Index(fields=["requested_organization", "status"], name="mr_org_status"),
            models.Index(fields=["requested_organization_code", "status"], name="mr_org_code_status"),
        ]
        ordering = ("-requested_at",)

    @override
    def save(self, *args, **kwargs) -> None:
        if self.requested_organization_id is not None and not self.requested_organization_code:
            self.requested_organization_code = str(self.requested_organization_id)
            self.requested_organization_name = self.requested_organization.name
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.requested_username == "":
            code = self.requested_organization_code or (self.requested_organization_id or "")
            return f"org:{code} → {self.membership_type_id}"
        return f"{self.requested_username} → {self.membership_type_id}"


class Membership(models.Model):
    target_username = models.CharField(max_length=255)
    membership_type = models.ForeignKey(MembershipType, on_delete=models.PROTECT)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["target_username", "membership_type"],
                name="uniq_membership_target_username_type",
            ),
        ]
        indexes = [
            models.Index(fields=["target_username"], name="m_tgt"),
            models.Index(fields=["expires_at"], name="m_exp_at"),
        ]
        ordering = ("target_username", "membership_type_id")

    def __str__(self) -> str:
        return f"{self.target_username} ({self.membership_type_id})"


class MembershipLog(models.Model):
    class Action(models.TextChoices):
        requested = "requested", "Requested"
        approved = "approved", "Approved"
        rejected = "rejected", "Rejected"
        ignored = "ignored", "Ignored"
        expiry_changed = "expiry_changed", "Expiry changed"
        terminated = "terminated", "Terminated"

    actor_username = models.CharField(max_length=255)
    target_username = models.CharField(max_length=255, blank=True, default="")
    target_organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="membership_logs",
    )
    target_organization_code = models.CharField(max_length=64, blank=True, default="")
    target_organization_name = models.CharField(max_length=255, blank=True, default="")
    membership_type = models.ForeignKey(MembershipType, on_delete=models.PROTECT)
    membership_request = models.ForeignKey(
        MembershipRequest,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="logs",
    )
    requested_group_cn = models.CharField(max_length=255, blank=True, default="")
    action = models.CharField(max_length=32, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    rejection_reason = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        Q(target_username="")
                        & (Q(target_organization__isnull=False) | ~Q(target_organization_code=""))
                    )
                    | (
                        ~Q(target_username="")
                        & Q(target_organization__isnull=True)
                        & Q(target_organization_code="")
                    )
                ),
                name="chk_membershiplog_exactly_one_target",
            )
        ]
        indexes = [
            models.Index(fields=["target_username", "created_at"], name="ml_tgt_at"),
            models.Index(fields=["target_username", "action", "created_at"], name="ml_tgt_act_at"),
            models.Index(fields=["target_organization", "created_at"], name="ml_org_at"),
            models.Index(fields=["target_organization", "action", "created_at"], name="ml_org_act_at"),
            models.Index(fields=["target_organization_code", "created_at"], name="ml_org_code_at"),
            models.Index(fields=["target_organization_code", "action", "created_at"], name="ml_org_code_act_at"),
            models.Index(fields=["expires_at"], name="ml_exp_at"),
        ]
        ordering = ("-created_at",)

    @override
    def save(self, *args, **kwargs) -> None:
        if self.target_organization_id is not None and not self.target_organization_code:
            self.target_organization_code = str(self.target_organization_id)
            self.target_organization_name = self.target_organization.name
        super().save(*args, **kwargs)

        if self.target_organization_id is not None:
            if self.action not in {
                self.Action.approved,
                self.Action.expiry_changed,
                self.Action.terminated,
            }:
                return

            OrganizationSponsorship.objects.update_or_create(
                organization_id=self.target_organization_id,
                defaults={
                    "membership_type": self.membership_type,
                    "expires_at": self.expires_at,
                },
            )
            return

        if self.target_organization_code:
            # Organization-target logs without a live FK should never affect current-state tables.
            return

        if self.action not in {
            self.Action.approved,
            self.Action.expiry_changed,
            self.Action.terminated,
        }:
            return

        # Membership is the current-state table for a user+membership_type.
        # Rows may be expired until the cleanup cron deletes them.
        Membership.objects.update_or_create(
            target_username=self.target_username,
            membership_type=self.membership_type,
            defaults={
                "expires_at": self.expires_at,
            },
        )

    def __str__(self) -> str:
        if self.target_username == "":
            code = self.target_organization_code or (self.target_organization_id or "")
            return f"{self.action}: org:{code} ({self.membership_type_id})"
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
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.requested,
        )

    @classmethod
    def create_for_org_request(
        cls,
        *,
        actor_username: str,
        target_organization: Organization,
        membership_type: MembershipType,
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username="",
            target_organization=target_organization,
            target_organization_code=str(target_organization.pk),
            target_organization_name=target_organization.name,
            membership_type=membership_type,
            membership_request=membership_request,
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
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        approved_at = timezone.now()
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.approved,
            expires_at=cls.expiry_for_approval_at(approved_at=approved_at, previous_expires_at=previous_expires_at),
        )

    @classmethod
    def create_for_org_approval(
        cls,
        *,
        actor_username: str,
        target_organization: Organization,
        membership_type: MembershipType,
        previous_expires_at: datetime.datetime | None = None,
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        approved_at = timezone.now()
        return cls.objects.create(
            actor_username=actor_username,
            target_username="",
            target_organization=target_organization,
            target_organization_code=str(target_organization.pk),
            target_organization_name=target_organization.name,
            membership_type=membership_type,
            membership_request=membership_request,
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
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.expiry_changed,
            expires_at=expires_at,
        )

    @classmethod
    def create_for_org_expiry_change(
        cls,
        *,
        actor_username: str,
        target_organization: Organization,
        membership_type: MembershipType,
        expires_at: datetime.datetime,
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username="",
            target_organization=target_organization,
            target_organization_code=str(target_organization.pk),
            target_organization_name=target_organization.name,
            membership_type=membership_type,
            membership_request=membership_request,
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
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        terminated_at = timezone.now()
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.terminated,
            expires_at=terminated_at,
        )

    @classmethod
    def create_for_org_termination(
        cls,
        *,
        actor_username: str,
        target_organization: Organization,
        membership_type: MembershipType,
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        terminated_at = timezone.now()
        return cls.objects.create(
            actor_username=actor_username,
            target_username="",
            target_organization=target_organization,
            target_organization_code=str(target_organization.pk),
            target_organization_name=target_organization.name,
            membership_type=membership_type,
            membership_request=membership_request,
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
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.rejected,
            rejection_reason=rejection_reason,
        )

    @classmethod
    def create_for_org_rejection(
        cls,
        *,
        actor_username: str,
        target_organization: Organization,
        membership_type: MembershipType,
        rejection_reason: str,
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username="",
            target_organization=target_organization,
            target_organization_code=str(target_organization.pk),
            target_organization_name=target_organization.name,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.rejected,
            rejection_reason=rejection_reason,
            expires_at=None,
        )

    @classmethod
    def create_for_ignore(
        cls,
        *,
        actor_username: str,
        target_username: str,
        membership_type: MembershipType,
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username=target_username,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.ignored,
        )

    @classmethod
    def create_for_org_ignore(
        cls,
        *,
        actor_username: str,
        target_organization: Organization,
        membership_type: MembershipType,
        membership_request: MembershipRequest | None = None,
    ) -> MembershipLog:
        return cls.objects.create(
            actor_username=actor_username,
            target_username="",
            target_organization=target_organization,
            target_organization_code=str(target_organization.pk),
            target_organization_name=target_organization.name,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=cls.Action.ignored,
            expires_at=None,
        )


class FreeIPAPermissionGrant(models.Model):
    """Grant an arbitrary Django permission string to a FreeIPA user or group.

    This intentionally does not use Django's auth.Permission model because:
    - Our users and groups are backed by FreeIPA, not Django DB rows.
    - We want grants like "astra.add_membership" without needing a model.
    """

    class PrincipalType(models.TextChoices):
        user = "user", "User"
        group = "group", "Group"

    permission = models.CharField(max_length=150, db_index=True)
    principal_type = models.CharField(max_length=10, choices=PrincipalType.choices, db_index=True)
    principal_name = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Permission Grant"
        verbose_name_plural = "Permission Grants"
        constraints = [
            models.UniqueConstraint(
                fields=["permission", "principal_type", "principal_name"],
                name="uniq_freeipa_permission_grant",
            )
        ]
        indexes = [
            models.Index(fields=["principal_type", "principal_name"], name="idx_perm_grant_principal"),
        ]

    def __str__(self) -> str:
        return f"{self.permission} -> {self.principal_type}:{self.principal_name}"

    @override
    def save(self, *args, **kwargs) -> None:
        # Normalize for stable matching (FreeIPA names are case-insensitive in practice).
        self.permission = str(self.permission or "").strip().lower()
        self.principal_name = str(self.principal_name or "").strip().lower()
        super().save(*args, **kwargs)
