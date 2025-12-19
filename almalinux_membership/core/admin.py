from __future__ import annotations

import logging
from django import forms
from django.contrib import admin
from django.utils.html import format_html
import json
from django.contrib.auth.models import Group as DjangoGroup
from django.contrib.auth.models import User as DjangoUser
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from .backends import (
    FreeIPAGroup,
    FreeIPAUser,
    _with_freeipa_service_client_retry,
    _invalidate_group_cache,
    _invalidate_groups_list_cache,
)
from .listbacked_queryset import _ListBackedQuerySet
from .models import IPAGroup, IPAUser

logger = logging.getLogger(__name__)

def _override_post_office_log_admin():
    """Disable manual creation of django-post-office Log rows in admin.

    This is a temporary local workaround until https://github.com/ui/django-post_office/pull/503 is merged and released.
    """

    try:
        from django.contrib.admin.sites import NotRegistered
        from post_office.admin import LogAdmin as PostOfficeLogAdmin
        from post_office.models import Log
    except Exception:
        return

    class ReadOnlyAddLogAdmin(PostOfficeLogAdmin):
        def has_add_permission(self, request):
            return False
        def has_change_permission(self, request, obj=None):
            return False
        def has_delete_permission(self, request, obj=None):
            return False

    try:
        admin.site.unregister(Log)
    except NotRegistered:
        pass

    admin.site.register(Log, ReadOnlyAddLogAdmin)


_override_post_office_log_admin()


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _override_django_ses_admin():
    """Register django-ses models with sensible admin defaults.

    Note: Django admin LogEntry writes require a DB-backed user row.
    This project authenticates via FreeIPA, but the middleware
    `core.middleware_admin_log.AdminShadowUserLogEntryMiddleware` provides a
    minimal DB "shadow user" in /admin/ so auditing works normally.
    """

    try:
        from django.contrib.admin.sites import NotRegistered
        from django_ses.models import BlacklistedEmail, SESStat
    except Exception:
        return

    class SESStatAdmin(admin.ModelAdmin):
        list_display = ("date", "delivery_attempts", "bounces", "complaints", "rejects")
        ordering = ("-date",)

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    class BlacklistedEmailAdmin(admin.ModelAdmin):
        list_display = ("email",)
        search_fields = ("email",)
        ordering = ("email",)

    try:
        admin.site.unregister(SESStat)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(BlacklistedEmail)
    except NotRegistered:
        pass

    admin.site.register(SESStat, SESStatAdmin)
    admin.site.register(BlacklistedEmail, BlacklistedEmailAdmin)


_override_django_ses_admin()


class IPAUserForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Set only when creating a user.",
    )
    groups = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="One FreeIPA group per line.",
    )

    class Meta:
        model = IPAUser
        fields = ("username", "first_name", "last_name", "email", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These models are unmanaged and have no DB tables; skip DB-backed uniqueness checks.
        self._validate_unique = False

        # Username is immutable in FreeIPA.
        if self.instance and getattr(self.instance, "username", None):
            self.fields["username"].disabled = True

        username = getattr(self.instance, "username", None)
        if username:
            freeipa = FreeIPAUser.get(username)
            if freeipa:
                self.initial.setdefault("first_name", freeipa.first_name or "")
                self.initial.setdefault("last_name", freeipa.last_name or "")
                self.initial.setdefault("email", freeipa.email or "")
                self.initial.setdefault("is_active", bool(getattr(freeipa, "is_active", True)))
                self.initial.setdefault("groups", "\n".join(sorted(getattr(freeipa, "groups_list", []) or [])))

    def validate_unique(self):
        # No DB; uniqueness is enforced by FreeIPA.
        return


class IPAGroupForm(forms.ModelForm):
    members = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="One username per line.",
    )
    fas_url = forms.CharField(
        required=False,
        label="FAS URL",
        help_text="Fedora Account System URL for this group",
    )
    fas_mailing_list = forms.CharField(
        required=False,
        label="FAS Mailing List",
        help_text="Fedora Account System mailing list for this group",
    )
    fas_irc_channels = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One IRC channel per line",
        label="FAS IRC Channels",
    )
    fas_discussion_url = forms.CharField(
        required=False,
        label="FAS Discussion URL",
        help_text="Fedora Account System discussion URL for this group",
    )

    fas_group = forms.BooleanField(
        required=False,
        label="FAS Group ObjectClass",
        help_text="Enable or disable the fasGroup objectClass for this group (controls FAS attribute support)",
    )

    class Meta:
        model = IPAGroup
        fields = ("cn", "description", "fas_url", "fas_mailing_list", "fas_discussion_url", "fas_group")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These models are unmanaged and have no DB tables; skip DB-backed uniqueness checks.
        self._validate_unique = False

        # Group name is immutable in FreeIPA.
        if self.instance and getattr(self.instance, "cn", None):
            self.fields["cn"].disabled = True

        cn = getattr(self.instance, "cn", None)
        if cn:
            freeipa = FreeIPAGroup.get(cn)
            if freeipa:
                self.initial.setdefault("description", getattr(freeipa, "description", "") or "")
                self.initial.setdefault("members", "\n".join(sorted(getattr(freeipa, "members", []) or [])))
                self.initial.setdefault("fas_url", getattr(freeipa, "fas_url", "") or "")
                self.initial.setdefault("fas_mailing_list", getattr(freeipa, "fas_mailing_list", "") or "")
                self.initial.setdefault("fas_irc_channels", "\n".join(sorted(getattr(freeipa, "fas_irc_channels", []) or [])))
                self.initial.setdefault("fas_discussion_url", getattr(freeipa, "fas_discussion_url", "") or "")
                self.initial.setdefault("fas_group", getattr(freeipa, "fas_group", False))
            # `fas_group` is a creation-time property; disallow toggling on edit.
            self.fields["fas_group"].disabled = True

    def validate_unique(self):
        # No DB; uniqueness is enforced by FreeIPA.
        return


@admin.register(IPAUser)
class IPAUserAdmin(admin.ModelAdmin):
    form = IPAUserForm
    list_display = ("username", "first_name", "last_name", "email", "is_active", "is_staff")
    ordering = ("username",)
    readonly_fields = ("attributes",)

    def get_queryset(self, request):
        users = FreeIPAUser.all()
        items = [IPAUser.from_freeipa(u) for u in users]
        return _ListBackedQuerySet(IPAUser, items)

    def get_object(self, request, object_id, from_field=None):
        freeipa = FreeIPAUser.get(object_id)
        if not freeipa:
            return None
        return IPAUser.from_freeipa(freeipa)

    def get_search_results(self, request, queryset, search_term):
        if not search_term:
            return queryset, False

        term = search_term.lower()

        def hit(u: IPAUser) -> bool:
            return any(
                (getattr(u, f, "") or "").lower().find(term) != -1
                for f in ("username", "first_name", "last_name", "email")
            )

        return _ListBackedQuerySet(IPAUser, [u for u in queryset if hit(u)]), False

    def attributes(self, obj):
        if not obj:
            return ""
        fu = FreeIPAUser.get(obj.username)
        data = getattr(fu, "_user_data", {}) if fu else {}
        try:
            dumped = json.dumps(data, indent=2, sort_keys=True, default=str)
        except Exception:
            dumped = str(data)
        return format_html('<pre style="white-space:pre-wrap;max-height:40em;overflow:auto;">{}</pre>', dumped)
    attributes.short_description = "All FreeIPA attributes"

    def save_model(self, request, obj, form, change):
        username = form.cleaned_data.get("username") or getattr(obj, "username", None)
        if not username:
            return

        desired_groups = set(_split_lines(form.cleaned_data.get("groups", "")))
        password = form.cleaned_data.get("password")

        if not change:
            freeipa = FreeIPAUser.create(
                username,
                first_name=form.cleaned_data.get("first_name") or "",
                last_name=form.cleaned_data.get("last_name") or "",
                email=form.cleaned_data.get("email") or "",
                password=password or None,
            )
        else:
            freeipa = FreeIPAUser.get(username)
            if not freeipa:
                return
            freeipa.first_name = form.cleaned_data.get("first_name") or ""
            freeipa.last_name = form.cleaned_data.get("last_name") or ""
            freeipa.email = form.cleaned_data.get("email") or ""
            freeipa.is_active = bool(form.cleaned_data.get("is_active"))
            freeipa.save()

        current_groups = set(getattr(freeipa, "groups_list", []) or [])
        for g in sorted(desired_groups - current_groups):
            freeipa.add_to_group(g)
        for g in sorted(current_groups - desired_groups):
            freeipa.remove_from_group(g)

    def delete_model(self, request, obj):
        freeipa = FreeIPAUser.get(obj.username)
        if freeipa:
            freeipa.delete()


@admin.register(IPAGroup)
class IPAGroupAdmin(admin.ModelAdmin):
    form = IPAGroupForm
    list_display = ("cn", "description", "fas_group", "fas_url", "fas_mailing_list")
    ordering = ("cn",)

    def get_queryset(self, request):
        groups = FreeIPAGroup.all()
        items = [IPAGroup.from_freeipa(g) for g in groups]
        return _ListBackedQuerySet(IPAGroup, items)

    def get_object(self, request, object_id, from_field=None):
        freeipa = FreeIPAGroup.get(object_id)
        if not freeipa:
            return None
        return IPAGroup.from_freeipa(freeipa)

    def get_search_results(self, request, queryset, search_term):
        if not search_term:
            return queryset, False

        term = search_term.lower()

        def hit(g: IPAGroup) -> bool:
            return any(
                (getattr(g, f, "") or "").lower().find(term) != -1
                for f in ("cn", "description")
            )

        return _ListBackedQuerySet(IPAGroup, [g for g in queryset if hit(g)]), False

    def save_model(self, request, obj, form, change):
        cn = form.cleaned_data.get("cn") or getattr(obj, "cn", None)
        if not cn:
            return

        desired_members = set(_split_lines(form.cleaned_data.get("members", "")))
        description = form.cleaned_data.get("description") or ""
        fas_url = form.cleaned_data.get("fas_url") or ""
        fas_mailing_list = form.cleaned_data.get("fas_mailing_list") or ""
        fas_irc_channels = set(_split_lines(form.cleaned_data.get("fas_irc_channels", "")))
        fas_discussion_url = form.cleaned_data.get("fas_discussion_url") or ""
        fas_group = form.cleaned_data.get("fas_group", False)

        if not change:
            freeipa = FreeIPAGroup.create(cn, description=description or None, fas_group=fas_group)
            # Enforce creation-time setting: if caller asked for a FAS-enabled
            # group but the FreeIPA server did not expose it immediately, fail
            # because toggling via group_mod is unsupported on some deployments.
            if fas_group:
                # Re-fetch authoritative state and verify.
                freeipa = FreeIPAGroup.get(cn)
                current_fas = bool(getattr(freeipa, "fas_group", False))
                if not current_fas:
                    raise RuntimeError("FreeIPA server did not create a fasGroup at creation time; toggling is not supported")
        else:
            freeipa = FreeIPAGroup.get(cn)
            if not freeipa:
                return
            changed = False
            if freeipa.description != description:
                freeipa.description = description
                changed = True
            if (freeipa.fas_url or "") != (fas_url or ""):
                freeipa.fas_url = fas_url or None
                changed = True
            if (freeipa.fas_mailing_list or "") != (fas_mailing_list or ""):
                freeipa.fas_mailing_list = fas_mailing_list or None
                changed = True
            if sorted(freeipa.fas_irc_channels or []) != sorted(list(fas_irc_channels) if fas_irc_channels else []):
                freeipa.fas_irc_channels = list(fas_irc_channels) if fas_irc_channels else []
                changed = True
            if (freeipa.fas_discussion_url or "") != (fas_discussion_url or ""):
                freeipa.fas_discussion_url = fas_discussion_url or None
                changed = True
            if changed:
                freeipa.save()

        # `fas_group` is a creation-time-only property. Do not attempt to
        # toggle it for existing groups via `group_mod` as many FreeIPA
        # deployments do not support that reliably. If an edit attempted to
        # change this value, ignore it and log at INFO level for visibility.
        if change:
            try:
                current_fas = bool(getattr(freeipa, "fas_group", False))
                if fas_group != current_fas:
                    logger.info(
                        "Ignoring fas_group toggle for existing group %s: current=%s requested=%s",
                        cn,
                        current_fas,
                        fas_group,
                    )
            except Exception:
                pass

        current_members = set(getattr(freeipa, "members", []) or [])
        for u in sorted(desired_members - current_members):
            freeipa.add_member(u)
        for u in sorted(current_members - desired_members):
            freeipa.remove_member(u)

    def delete_model(self, request, obj):
        freeipa = FreeIPAGroup.get(obj.cn)
        if freeipa:
            freeipa.delete()


# Replace DB-backed auth models in admin with FreeIPA-backed listings.
try:
    admin.site.unregister(DjangoUser)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(DjangoGroup)
except admin.sites.NotRegistered:
    pass

# django-avatar registers an Avatar admin that depends on Django's User admin
# being registered (it uses autocomplete_fields=['user']). This project
# intentionally unregisters the DB-backed User/Group admin in favor of FreeIPA
# listings, so we also remove the django-avatar admin integration.
try:
    from avatar.models import Avatar

    try:
        admin.site.unregister(Avatar)
    except admin.sites.NotRegistered:
        pass
except ImportError:
    pass


# Keep the traditional admin URLs working.
if not getattr(admin.site, "_freeipa_aliases_patched", False):
    _orig_get_urls = admin.site.get_urls

    def _get_urls_with_freeipa_aliases():
        def redirect_to_ipa_users(request):
            return HttpResponseRedirect(reverse("admin:auth_ipauser_changelist"))

        def redirect_to_ipa_groups(request):
            return HttpResponseRedirect(reverse("admin:auth_ipagroup_changelist"))

        custom = [
            path("auth/user/", admin.site.admin_view(redirect_to_ipa_users)),
            path("auth/group/", admin.site.admin_view(redirect_to_ipa_groups)),
        ]
        return custom + _orig_get_urls()

    admin.site.get_urls = _get_urls_with_freeipa_aliases
    admin.site._freeipa_aliases_patched = True
