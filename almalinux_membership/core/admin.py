from __future__ import annotations

from django import forms
from django.contrib import admin
from django.utils.html import format_html
import json
from django.contrib.auth.models import Group as DjangoGroup
from django.contrib.auth.models import User as DjangoUser
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from .backends import FreeIPAGroup, FreeIPAUser
from .models import IPAGroup, IPAUser


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

class _ListBackedQuerySet:
    """Minimal QuerySet-like wrapper for Django admin changelist.

    Django admin's changelist expects something sliceable with .count() and
    basic iteration semantics. This avoids hitting the DB for unmanaged models.
    """

    def __init__(self, model, items):
        self.model = model
        self._items = list(items)
        # Admin inspects `qs.query.select_related`.
        self.query = type("_Q", (), {"select_related": False, "order_by": []})()

    def all(self):
        return self

    def select_related(self, *fields):
        self.query.select_related = True
        return self

    def filter(self, *args, **kwargs):
        # Django admin may call .filter(Q(...)) even when our backend isn't ORM.
        # We ignore positional Q objects and apply only simple kwarg equality.
        def matches(item):
            for key, expected in kwargs.items():
                field = key.split("__", 1)[0]
                if field in {"pk", "id"}:
                    actual = getattr(item, "pk", getattr(item, "id", None))
                else:
                    actual = getattr(item, field, None)
                if actual != expected:
                    return False
            return True

        if not kwargs:
            return self

        return _ListBackedQuerySet(self.model, [i for i in self._items if matches(i)])

    def order_by(self, *fields):
        items = list(self._items)
        self.query.order_by = list(fields or [])
        # Apply sorts from right to left to mimic multi-key ordering.
        for field in reversed(fields or []):
            reverse_sort = False
            name = field
            if isinstance(name, str) and name.startswith("-"):
                reverse_sort = True
                name = name[1:]
            items.sort(key=lambda o: getattr(o, name, ""), reverse=reverse_sort)
        return _ListBackedQuerySet(self.model, items)

    def count(self):
        return len(self._items)

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, key):
        return self._items[key]

    def _clone(self):
        clone = _ListBackedQuerySet(self.model, list(self._items))
        clone.query.select_related = getattr(self.query, "select_related", False)
        clone.query.order_by = list(getattr(self.query, "order_by", []))
        return clone

    def distinct(self, *args, **kwargs):
        return self

    def get(self, **kwargs):
        matches = list(self.filter(**kwargs))
        if not matches:
            raise self.model.DoesNotExist()
        if len(matches) > 1:
            raise self.model.MultipleObjectsReturned()
        return matches[0]


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class _NoAdminLogMixin:
    """Disable DB-backed admin LogEntry writes.

    Django admin normally writes to `django_admin_log` with a FK to
    `AUTH_USER_MODEL` (default `auth.User`). Since this project uses FreeIPA
    users without a local DB row, those FK writes fail.
    """

    def log_addition(self, request, obj, message):
        return

    def log_change(self, request, obj, message):
        return

    def log_deletion(self, request, obj, object_repr):
        return

    def log_deletions(self, request, queryset):
        return


def _override_django_ses_admin():
    """Register django-ses models with admin logging disabled.

    django-ses registers SESStat itself, but this project cannot write Django
    admin LogEntry rows because users are not DB-backed.
    """

    try:
        from django.contrib.admin.sites import NotRegistered
        from django_ses.models import BlacklistedEmail, SESStat
    except Exception:
        return

    class SESStatAdmin(_NoAdminLogMixin, admin.ModelAdmin):
        list_display = ("date", "delivery_attempts", "bounces", "complaints", "rejects")
        ordering = ("-date",)

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    class BlacklistedEmailAdmin(_NoAdminLogMixin, admin.ModelAdmin):
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

    class Meta:
        model = IPAGroup
        fields = ("cn", "description")

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

    def validate_unique(self):
        # No DB; uniqueness is enforced by FreeIPA.
        return


@admin.register(IPAUser)
class IPAUserAdmin(_NoAdminLogMixin, admin.ModelAdmin):
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
class IPAGroupAdmin(_NoAdminLogMixin, admin.ModelAdmin):
    form = IPAGroupForm
    list_display = ("cn", "description")
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

        if not change:
            freeipa = FreeIPAGroup.create(cn, description=description or None)
        else:
            freeipa = FreeIPAGroup.get(cn)
            if not freeipa:
                return
            freeipa.description = description
            freeipa.save()

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
