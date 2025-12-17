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
        )
