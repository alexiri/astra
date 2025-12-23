from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, override
from urllib.parse import urlparse

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.utils import model_ngettext
from django.contrib.auth.models import Group as DjangoGroup
from django.contrib.auth.models import User as DjangoUser
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from core.agreements import missing_required_agreements_for_user_in_group
from core.views_utils import _normalize_str

from .backends import (
    FreeIPAFASAgreement,
    FreeIPAGroup,
    FreeIPAOperationFailed,
    FreeIPAUser,
    _invalidate_agreement_cache,
    _invalidate_agreements_list_cache,
)
from .listbacked_queryset import _ListBackedQuerySet
from .models import IPAFASAgreement, IPAGroup, IPAUser, MembershipType

logger = logging.getLogger(__name__)


class FreeIPAModelAdmin(admin.ModelAdmin):
    """Common admin UX for FreeIPA-backed (unmanaged) models.

    Django's default admin flows assume DB-backed objects and a bulk delete
    action that can reliably report success. FreeIPA operations can fail per
    object (permissions, server-side constraints), so we provide:

    - Consistent error surfacing for change forms and deletes.
    - A custom bulk delete action that reports per-object failures.
    """

    # Keep a dedicated name for our implementation, but we map it to the
    # standard 'delete_selected' action key in get_actions() so users get the
    # usual Django confirmation flow and wording.
    actions = ("delete_selected_freeipa_objects",)

    # Subclasses should set this to the matching FreeIPA backend class, e.g.
    # FreeIPAUser / FreeIPAGroup / FreeIPAFASAgreement.
    freeipa_backend: Any | None = None

    class Media:
        js = (
            "core/js/admin_duallistbox_init.js",
        )

    @override
    def get_queryset(self, request) -> Any:
        backend = getattr(self, "freeipa_backend", None)
        if backend is None:
            return super().get_queryset(request)

        from_freeipa: Callable[[Any], Any] | None = getattr(self.model, "from_freeipa", None)
        if not callable(from_freeipa):
            raise RuntimeError(f"{self.model.__name__} must define a classmethod from_freeipa()")

        items = [from_freeipa(obj) for obj in backend.all()]
        return _ListBackedQuerySet(self.model, items)

    @override
    def get_object(self, request, object_id, from_field=None) -> Any:
        backend = getattr(self, "freeipa_backend", None)
        if backend is None:
            return super().get_object(request, object_id, from_field=from_field)

        # Prefer the list-backed queryset when available. This preserves
        # Django's normal admin semantics (and test fixtures that only stub
        # `.all()`), while still allowing a fallback for cases where the
        # object isn't present in the listing.
        obj = super().get_object(request, object_id, from_field=from_field)
        if obj is not None:
            return obj

        from_freeipa: Callable[[Any], Any] | None = getattr(self.model, "from_freeipa", None)
        if not callable(from_freeipa):
            raise RuntimeError(f"{self.model.__name__} must define a classmethod from_freeipa()")

        freeipa_obj = backend.get(object_id)
        if not freeipa_obj:
            return None
        return from_freeipa(freeipa_obj)

    @override
    def get_search_results(self, request, queryset, search_term) -> tuple[Any, bool]:
        # For DB-backed models, defer to Django.
        if not isinstance(queryset, _ListBackedQuerySet):
            return super().get_search_results(request, queryset, search_term)

        if not search_term or not getattr(self, "search_fields", None):
            return queryset, False

        term = search_term.lower()

        def matches(obj: Any) -> bool:
            for raw_field in self.search_fields:
                if not raw_field:
                    continue

                lookup = raw_field[0]
                if lookup in {"^", "=", "@"}:
                    field = raw_field[1:]
                else:
                    lookup = ""
                    field = raw_field

                try:
                    value = getattr(obj, field, "")
                except Exception:
                    continue
                if value is None:
                    continue

                text = str(value).lower()
                if lookup == "=":
                    if text == term:
                        return True
                elif lookup == "^":
                    if text.startswith(term):
                        return True
                else:
                    # Default to case-insensitive substring match.
                    if term in text:
                        return True
            return False

        return _ListBackedQuerySet(self.model, [o for o in queryset if matches(o)]), False

    def _freeipa_object_id(self, obj: object) -> str:
        # Prefer model pk; fall back to common FreeIPA identifiers.
        for attr in ("pk", "username", "cn"):
            value = getattr(obj, attr, None)
            if value:
                return str(value)
        return str(obj)

    @override
    def delete_model(self, request, obj) -> None:
        backend = getattr(self, "freeipa_backend", None)
        if backend is None:
            return super().delete_model(request, obj)

        object_id = self._freeipa_object_id(obj)
        freeipa_obj = backend.get(object_id)
        if freeipa_obj:
            freeipa_obj.delete()

    @override
    def delete_queryset(self, request, queryset) -> None:
        backend = getattr(self, "freeipa_backend", None)
        if backend is None:
            return super().delete_queryset(request, queryset)

        # For our list-backed querysets, loop and call delete_model so we don't
        # rely on `_ListBackedQuerySet.delete()` (which is intentionally minimal
        # and not model-generic).
        for obj in list(queryset):
            self.delete_model(request, obj)

    @override
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None) -> Any:
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except FreeIPAOperationFailed as e:
            self.message_user(request, str(e), level=messages.ERROR)
            return HttpResponseRedirect(request.path)
        except Exception as e:
            logger.exception(
                "Unhandled exception in admin changeform_view model=%s object_id=%s",
                getattr(self.model, "__name__", "?"),
                object_id,
            )
            self.message_user(request, str(e), level=messages.ERROR)
            return HttpResponseRedirect(request.path)

    @override
    def delete_view(self, request, object_id, extra_context=None) -> Any:
        try:
            return super().delete_view(request, object_id, extra_context)
        except FreeIPAOperationFailed as e:
            self.message_user(request, str(e), level=messages.ERROR)
            return HttpResponseRedirect(self._changelist_url())
        except Exception as e:
            logger.exception(
                "Unhandled exception in admin delete_view model=%s object_id=%s",
                getattr(self.model, "__name__", "?"),
                object_id,
            )
            self.message_user(request, str(e), level=messages.ERROR)
            return HttpResponseRedirect(self._changelist_url())

    def _changelist_url(self) -> str:
        return reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")

    @override
    def get_actions(self, request):
        actions = super().get_actions(request)
        # Replace Django's built-in bulk delete action with our FreeIPA-aware
        # implementation, but keep the standard action key so Django renders the
        # usual confirmation page and UI label.
        actions.pop("delete_selected", None)

        # Move our action (generated by super().get_actions) to the standard
        # key. The action tuple contains the unbound method which Django can
        # call as func(modeladmin, request, queryset).
        freeipa_action = actions.pop("delete_selected_freeipa_objects", None)
        func = freeipa_action[0] if freeipa_action else type(self).delete_selected_freeipa_objects

        description = _("Delete selected %(verbose_name_plural)s") % {
            "verbose_name_plural": self.model._meta.verbose_name_plural,
        }
        actions["delete_selected"] = (func, "delete_selected", description)
        return actions

    def _object_key(self, obj) -> str:
        for attr in ("pk", "username", "cn"):
            value = getattr(obj, attr, None)
            if value:
                return str(value)
        return str(obj)

    def delete_selected_freeipa_objects(self, request, queryset):
        """Delete action with Django's confirmation flow + per-object failures.

        Mirrors Django's built-in delete action UX (confirmation page), but when
        confirmed it deletes objects one-by-one so we can surface partial failures
        instead of reporting a misleading blanket success.
        """

        opts = self.model._meta
        app_label = opts.app_label

        (
            deletable_objects,
            model_count,
            perms_needed,
            protected,
        ) = self.get_deleted_objects(queryset, request)

        if request.POST.get("post") and not protected:
            if perms_needed:
                raise PermissionDenied

            deleted_keys: list[str] = []
            deleted_objects: list[object] = []
            failed: dict[str, str] = {}

            for obj in list(queryset):
                key = self._object_key(obj)
                try:
                    self.delete_model(request, obj)
                    deleted_keys.append(key)
                    deleted_objects.append(obj)
                except Exception as e:
                    failed[key] = str(e)
                    logger.exception(
                        "Failed to delete FreeIPA-backed object model=%s key=%s",
                        getattr(self.model, "__name__", "?"),
                        key,
                    )

            # Django's log_deletions() is batch-oriented and is the supported API
            # in this Django version (there is no per-object log_deletion).
            # This should not convert successful deletes into failures.
            if deleted_objects:
                try:
                    # ContentType caches can survive across test DB setup and
                    # unmanaged models (especially with custom app_label) may
                    # not have ContentType rows until first use.
                    ContentType.objects.clear_cache()
                    ContentType.objects.get_for_model(self.model, for_concrete_model=False)
                    log_deletions = getattr(self, "log_deletions", None)
                    if callable(log_deletions):
                        log_deletions(request, _ListBackedQuerySet(self.model, deleted_objects))
                except Exception:
                    logger.exception(
                        "Failed to write admin deletion LogEntry rows model=%s count=%s",
                        getattr(self.model, "__name__", "?"),
                        len(deleted_objects),
                    )

            if deleted_keys:
                n = len(deleted_keys)
                self.message_user(
                    request,
                    _("Successfully deleted %(count)d %(items)s.")
                    % {"count": n, "items": model_ngettext(self.opts, n)},
                    messages.SUCCESS,
                )

            if failed:
                details = "; ".join(f"{k}: {v}" for k, v in sorted(failed.items()))
                self.message_user(
                    request,
                    f"Failed to delete {len(failed)} object(s): {details}",
                    messages.ERROR,
                )

            # Return None to display the change list page again.
            return None

        objects_name = model_ngettext(queryset)
        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": objects_name}
        else:
            title = _("Delete multiple objects")

        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "subtitle": None,
            "objects_name": str(objects_name),
            "deletable_objects": [deletable_objects],
            "model_count": dict(model_count).items(),
            "queryset": queryset,
            "perms_lacking": perms_needed,
            "protected": protected,
            "opts": opts,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "media": self.media,
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(
            request,
            self.delete_selected_confirmation_template
            or [
                f"admin/{app_label}/{opts.model_name}/delete_selected_confirmation.html",
                f"admin/{app_label}/delete_selected_confirmation.html",
                "admin/delete_selected_confirmation.html",
            ],
            context,
        )


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


class IPAUserBaseForm(forms.ModelForm):
    groups = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control alx-duallistbox", "size": 12}),
        help_text="Select the FreeIPA groups this user should be a member of.",
    )

    class Meta:
        model = IPAUser
        fields = ("username", "first_name", "last_name", "email", "is_active")

    @override
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These models are unmanaged and have no DB tables; skip DB-backed uniqueness checks.
        self._validate_unique = False

        groups = FreeIPAGroup.all()
        group_names = sorted({getattr(g, "cn", "") for g in groups if getattr(g, "cn", "")})
        self.fields["groups"].choices = [(name, name) for name in group_names]

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
                self.initial.setdefault("is_active", freeipa.is_active)
                current = sorted(freeipa.direct_groups_list)
                # If the server returns groups outside our enumerated list,
                # keep them selectable so we don't drop memberships on save.
                missing = [g for g in current if g not in dict(self.fields["groups"].choices)]
                if missing:
                    self.fields["groups"].choices = [(g, g) for g in (group_names + missing)]
                self.initial.setdefault("groups", current)

    @override
    def validate_unique(self):
        # No DB; uniqueness is enforced by FreeIPA.
        return


class IPAUserAddForm(IPAUserBaseForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Set only when creating a user.",
    )


class IPAUserChangeForm(IPAUserBaseForm):
    pass


class IPAGroupForm(forms.ModelForm):
    members = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control alx-duallistbox", "size": 14}),
        help_text="Select the users that should be members of this group.",
    )
    sponsors = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control alx-duallistbox", "size": 14}),
        help_text="Select the users that should be sponsors (memberManager) of this group.",
    )
    member_groups = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control alx-duallistbox", "size": 14}),
        help_text="Select the groups that should be nested members of this group.",
        label="Member groups",
    )
    sponsor_groups = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control alx-duallistbox", "size": 14}),
        help_text="Select the groups that should be sponsors (memberManager) of this group.",
        label="Sponsor groups",
    )
    fas_url = forms.CharField(
        required=False,
        label="FAS URL",
        help_text="Fedora Account System URL for this group",
        widget=forms.URLInput(attrs={"placeholder": "https://…"}),
    )
    fas_mailing_list = forms.CharField(
        required=False,
        label="FAS Mailing List",
        help_text="Fedora Account System mailing list for this group",
        widget=forms.EmailInput(attrs={"placeholder": "group@lists.example.org"}),
    )
    fas_irc_channels = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One per line (or comma-separated).",
        label="FAS IRC Channels",
    )
    fas_discussion_url = forms.CharField(
        required=False,
        label="FAS Discussion URL",
        help_text="Fedora Account System discussion URL for this group",
        widget=forms.URLInput(attrs={"placeholder": "https://…"}),
    )

    fas_group = forms.BooleanField(
        required=False,
        label="FAS Group",
        help_text="Enable or disable the fasGroup objectClass for this group (controls FAS attribute support)",
    )

    class Meta:
        model = IPAGroup
        fields = ("cn", "description", "fas_url", "fas_mailing_list", "fas_discussion_url", "fas_group")

    @override
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These models are unmanaged and have no DB tables; skip DB-backed uniqueness checks.
        self._validate_unique = False

        users = FreeIPAUser.all()
        usernames = sorted({getattr(u, "username", "") for u in users if getattr(u, "username", "")})
        self.fields["members"].choices = [(u, u) for u in usernames]
        self.fields["sponsors"].choices = [(u, u) for u in usernames]

        groups = FreeIPAGroup.all()
        group_names = sorted({getattr(g, "cn", "") for g in groups if getattr(g, "cn", "")})
        self.fields["member_groups"].choices = [(g, g) for g in group_names]
        self.fields["sponsor_groups"].choices = [(g, g) for g in group_names]

        # Group name is immutable in FreeIPA.
        if self.instance and getattr(self.instance, "cn", None):
            self.fields["cn"].disabled = True

        cn = getattr(self.instance, "cn", None)
        if cn:
            freeipa = FreeIPAGroup.get(cn)
            if freeipa:
                self.initial.setdefault("description", freeipa.description or "")
                current = sorted(freeipa.members)
                # Groups can contain entries that aren't part of the standard user listing.
                missing = [u for u in current if u not in dict(self.fields["members"].choices)]
                if missing:
                    self.fields["members"].choices = [(u, u) for u in (usernames + missing)]
                self.initial.setdefault("members", current)

                current_sponsors = sorted(freeipa.sponsors)
                missing_sponsors = [u for u in current_sponsors if u not in dict(self.fields["sponsors"].choices)]
                if missing_sponsors:
                    self.fields["sponsors"].choices = [(u, u) for u in (usernames + missing_sponsors)]
                self.initial.setdefault("sponsors", current_sponsors)

                current_member_groups = sorted(getattr(freeipa, "member_groups", []) or [])
                missing_groups = [g for g in current_member_groups if g not in dict(self.fields["member_groups"].choices)]
                if missing_groups:
                    self.fields["member_groups"].choices = [(g, g) for g in (group_names + missing_groups)]
                self.initial.setdefault("member_groups", current_member_groups)

                current_sponsor_groups = sorted(getattr(freeipa, "sponsor_groups", []) or [])
                missing_sponsor_groups = [g for g in current_sponsor_groups if g not in dict(self.fields["sponsor_groups"].choices)]
                if missing_sponsor_groups:
                    self.fields["sponsor_groups"].choices = [(g, g) for g in (group_names + missing_sponsor_groups)]
                self.initial.setdefault("sponsor_groups", current_sponsor_groups)
                self.initial.setdefault("fas_url", freeipa.fas_url or "")
                self.initial.setdefault("fas_mailing_list", freeipa.fas_mailing_list or "")
                self.initial.setdefault("fas_irc_channels", "\n".join(sorted(freeipa.fas_irc_channels)))
                self.initial.setdefault("fas_discussion_url", freeipa.fas_discussion_url or "")
                self.initial.setdefault("fas_group", freeipa.fas_group)
            # `fas_group` is a creation-time property; disallow toggling on edit.
            self.fields["fas_group"].disabled = True

    @override
    def validate_unique(self):
        # No DB; uniqueness is enforced by FreeIPA.
        return

    @staticmethod
    def _split_list_field(value: str) -> list[str]:
        out: list[str] = []
        for raw_line in (value or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for part in line.split(","):
                p = part.strip()
                if p:
                    out.append(p)
        return out

    @staticmethod
    def _validate_http_url(value: str, *, field_label: str) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        if len(v) > 255:
            raise forms.ValidationError(f"Invalid {field_label}: must be at most 255 characters")

        parsed = urlparse(v)
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise forms.ValidationError(f"Invalid {field_label}: URL must start with http:// or https://")
        if not parsed.netloc:
            raise forms.ValidationError(f"Invalid {field_label}: empty host name")
        return v

    def clean_fas_url(self) -> str:
        return self._validate_http_url(self.cleaned_data.get("fas_url", ""), field_label="FAS URL")

    def clean_fas_discussion_url(self) -> str:
        return self._validate_http_url(
            self.cleaned_data.get("fas_discussion_url", ""),
            field_label="FAS Discussion URL",
        )

    def clean_fas_mailing_list(self) -> str:
        v = (self.cleaned_data.get("fas_mailing_list") or "").strip()
        if not v:
            return ""

        return forms.EmailField(required=False).clean(v)

    def clean_fas_irc_channels(self) -> str:
        raw = self.cleaned_data.get("fas_irc_channels") or ""
        channels = []
        for ch in self._split_list_field(raw):
            if len(ch) > 64:
                raise forms.ValidationError("Invalid FAS IRC Channels: each channel must be at most 64 characters")
            if not ch.startswith("#"):
                raise forms.ValidationError("Invalid FAS IRC Channels: channels must start with '#'")
            channels.append(ch)

        # Keep stable ordering for diffs.
        deduped = sorted(set(channels), key=str.lower)
        return "\n".join(deduped)


class IPAFASAgreementForm(forms.ModelForm):
    groups = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control alx-duallistbox", "size": 14}),
        help_text="Select the FreeIPA groups this agreement applies to.",
    )
    users = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control alx-duallistbox", "size": 14}),
        help_text="Select the users who have consented to this agreement.",
    )
    enabled = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Enable or disable this agreement.",
    )

    class Meta:
        model = IPAFASAgreement
        fields = ("cn", "description", "enabled")

    @override
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These models are unmanaged and have no DB tables; skip DB-backed uniqueness checks.
        self._validate_unique = False

        if "description" in self.fields:
            self.fields["description"].label = "Text"

        groups = FreeIPAGroup.all()
        group_names = sorted(
            {
                getattr(g, "cn", "")
                for g in groups
                if getattr(g, "cn", "") and bool(getattr(g, "fas_group", False))
            }
        )
        self.fields["groups"].choices = [(name, name) for name in group_names]

        users = FreeIPAUser.all()
        usernames = sorted({getattr(u, "username", "") for u in users if getattr(u, "username", "")})
        self.fields["users"].choices = [(u, u) for u in usernames]

        # Agreement name is immutable in FreeIPA.
        if self.instance and getattr(self.instance, "cn", None):
            self.fields["cn"].disabled = True

        cn = getattr(self.instance, "cn", None)
        if cn:
            freeipa = FreeIPAFASAgreement.get(cn)
            if freeipa:
                self.initial.setdefault("description", freeipa.description)
                self.initial.setdefault("enabled", freeipa.enabled)

                current_groups = sorted(freeipa.groups)
                missing_groups = [g for g in current_groups if g not in dict(self.fields["groups"].choices)]
                if missing_groups:
                    self.fields["groups"].choices = [(g, g) for g in (group_names + missing_groups)]
                self.initial.setdefault("groups", current_groups)

                current_users = sorted(freeipa.users)
                missing_users = [u for u in current_users if u not in dict(self.fields["users"].choices)]
                if missing_users:
                    self.fields["users"].choices = [(u, u) for u in (usernames + missing_users)]
                self.initial.setdefault("users", current_users)

    @override
    def validate_unique(self):
        # No DB; uniqueness is enforced by FreeIPA.
        return


@admin.register(IPAUser)
class IPAUserAdmin(FreeIPAModelAdmin):
    form = IPAUserChangeForm
    freeipa_backend = FreeIPAUser
    list_display = ("username", "displayname", "email", "is_active", "is_staff")
    ordering = ("username",)
    search_fields = ("username", "displayname", "first_name", "last_name", "email")
    readonly_fields = ()

    @override
    def get_form(self, request, obj=None, change=False, **kwargs):
        defaults: dict[str, Any] = {"form": IPAUserChangeForm if obj else IPAUserAddForm}
        defaults.update(kwargs)
        return super().get_form(request, obj=obj, change=change, **defaults)

    @override
    def save_model(self, request, obj, form, change):
        username = form.cleaned_data.get("username") or getattr(obj, "username", None)
        if not username:
            return

        desired_groups = set(form.cleaned_data.get("groups") or [])
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

        current_groups = set(freeipa.direct_groups_list)
        for g in sorted(desired_groups - current_groups):
            missing = missing_required_agreements_for_user_in_group(username, g)
            if missing:
                raise FreeIPAOperationFailed(
                    f"Cannot add user '{username}' to group '{g}' until they have signed: {', '.join(missing)}"
                )
            freeipa.add_to_group(g)
        for g in sorted(current_groups - desired_groups):
            freeipa.remove_from_group(g)

@admin.register(IPAGroup)
class IPAGroupAdmin(FreeIPAModelAdmin):
    form = IPAGroupForm
    freeipa_backend = FreeIPAGroup
    list_display = ("cn", "description", "fas_group", "fas_url", "fas_mailing_list")
    ordering = ("cn",)
    search_fields = ("cn", "description")

    @override
    def save_model(self, request, obj, form, change):
        cn = form.cleaned_data.get("cn") or getattr(obj, "cn", None)
        if not cn:
            return

        desired_members = set(form.cleaned_data.get("members") or [])
        desired_sponsors = set(form.cleaned_data.get("sponsors") or [])
        desired_member_groups = set(form.cleaned_data.get("member_groups") or [])
        desired_sponsor_groups = set(form.cleaned_data.get("sponsor_groups") or [])
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
                current_fas = bool(freeipa.fas_group)
                if not current_fas:
                    raise RuntimeError(
                        "FreeIPA server did not create a fasGroup at creation time; toggling is not supported"
                    )
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
                current_fas = bool(freeipa.fas_group)
                if fas_group != current_fas:
                    logger.info(
                        "Ignoring fas_group toggle for existing group %s: current=%s requested=%s",
                        cn,
                        current_fas,
                        fas_group,
                    )
            except Exception:
                pass

        current_members = set(freeipa.members)
        for u in sorted(desired_members - current_members):
            missing = missing_required_agreements_for_user_in_group(u, cn)
            if missing:
                raise FreeIPAOperationFailed(
                    f"Cannot add user '{u}' to group '{cn}' until they have signed: {', '.join(missing)}"
                )
            freeipa.add_member(u)
        for u in sorted(current_members - desired_members):
            freeipa.remove_member(u)

        current_sponsors = set(freeipa.sponsors)
        for u in sorted(desired_sponsors - current_sponsors):
            freeipa.add_sponsor(u)
        for u in sorted(current_sponsors - desired_sponsors):
            freeipa.remove_sponsor(u)

        current_sponsor_groups = set(getattr(freeipa, "sponsor_groups", []) or [])
        for group_cn in sorted(desired_sponsor_groups - current_sponsor_groups):
            freeipa.add_sponsor_group(group_cn)
        for group_cn in sorted(current_sponsor_groups - desired_sponsor_groups):
            freeipa.remove_sponsor_group(group_cn)

        current_member_groups = set(getattr(freeipa, "member_groups", []) or [])
        for group_cn in sorted(desired_member_groups - current_member_groups):
            freeipa.add_member_group(group_cn)
        for group_cn in sorted(current_member_groups - desired_member_groups):
            freeipa.remove_member_group(group_cn)

@admin.register(IPAFASAgreement)
class IPAFASAgreementAdmin(FreeIPAModelAdmin):
    form = IPAFASAgreementForm
    freeipa_backend = FreeIPAFASAgreement
    list_display = ("cn", "enabled")
    ordering = ("cn",)
    search_fields = ("cn", "description")

    @override
    def save_model(self, request, obj, form, change):
        try:
            cn: str = form.cleaned_data.get("cn") or obj.cn
            description: str = _normalize_str(form.cleaned_data.get("description"))
            enabled: bool = form.cleaned_data.get("enabled", False)
            selected_groups = set(form.cleaned_data.get("groups") or [])
            selected_users = set(form.cleaned_data.get("users") or [])

            # Treat disabled agreements as non-applicable for group membership.
            # The FreeIPA plugin may still enforce agreements linked to groups,
            # so we remove group links when the agreement is disabled.
            if not enabled:
                selected_groups = set()

            if not change:
                freeipa = FreeIPAFASAgreement.create(cn, description=description or None)
            else:
                freeipa = FreeIPAFASAgreement.get(cn)
                if freeipa is None:
                    raise FreeIPAOperationFailed(f"Agreement not found after edit: {cn}")
                if freeipa.description != description:
                    freeipa.set_description(description or None)

            current_groups = set(freeipa.groups)
            for group_cn in sorted(selected_groups - current_groups):
                freeipa.add_group(group_cn)
            for group_cn in sorted(current_groups - selected_groups):
                freeipa.remove_group(group_cn)

            current_users = set(freeipa.users)
            for username in sorted(selected_users - current_users):
                freeipa.add_user(username)
            for username in sorted(current_users - selected_users):
                freeipa.remove_user(username)

            if freeipa.enabled != enabled:
                freeipa.set_enabled(enabled)

            _invalidate_agreement_cache(cn)
            _invalidate_agreements_list_cache()
        except FreeIPAOperationFailed:
            raise
        except Exception as e:
            logger.exception("Failed to save FAS agreement cn=%s", getattr(obj, "cn", None) or form.cleaned_data.get("cn"))
            raise FreeIPAOperationFailed(str(e))


@admin.register(MembershipType)
class MembershipTypeAdmin(admin.ModelAdmin):
    class MembershipTypeAdminForm(forms.ModelForm):
        group_cn = forms.ChoiceField(
            required=False,
            label="Group",
            help_text="Optional: associate this membership type with a FreeIPA group.",
        )

        class Meta:
            model = MembershipType
            fields = "__all__"

        @override
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            groups = FreeIPAGroup.all()
            group_names = sorted({g.cn for g in groups if g.cn})

            current = (self.initial.get("group_cn") or "").strip()
            if not current and self.instance and self.instance.group_cn:
                current = str(self.instance.group_cn or "").strip()
            if current and current not in group_names:
                group_names.append(current)

            self.fields["group_cn"].choices = [("", "---------"), *[(name, name) for name in group_names]]

    form = MembershipTypeAdminForm

    list_display = (
        "code",
        "name",
        "group_cn",
        "isIndividual",
        "isOrganization",
        "sort_order",
        "enabled",
    )
    list_filter = ("enabled", "isIndividual", "isOrganization")
    ordering = ("sort_order", "code")
    search_fields = ("code", "name")

    @override
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj=obj))
        if obj is not None and "code" not in readonly:
            readonly.append("code")
        return tuple(readonly)

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
