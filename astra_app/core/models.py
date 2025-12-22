from __future__ import annotations

from django.db import models


class IPAUser(models.Model):
    # NOTE: Keep this model unmanaged; it mirrors FreeIPA users.
    username = models.CharField(max_length=255, primary_key=True)
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
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
    def from_freeipa(cls, user) -> "IPAUser":
        # `user` is a core.backends.FreeIPAUser
        return cls(
            username=user.username,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
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
    def from_freeipa(cls, group) -> "IPAGroup":
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
    def from_freeipa(cls, agreement) -> "IPAFASAgreement":
        # `agreement` is a core.backends.FreeIPAFASAgreement
        # Coerce to concrete types so the Django admin list display doesn't
        # receive MagicMock values from tests or partial stubs.
        return cls(
            cn=agreement.cn,
            description=str(getattr(agreement, "description", "") or ""),
            enabled=bool(getattr(agreement, "enabled", True)),
        )
