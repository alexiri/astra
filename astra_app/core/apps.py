from django.apps import AppConfig


def _patch_jazzmin_format_html() -> None:
    """Patch Jazzmin's template tag module for Django compatibility.

    Newer Django versions raise `TypeError` if `format_html()` is called without
    args/kwargs. Jazzmin's paginator tag calls `format_html(html_str)`.
    We replace the module-local `format_html` with a wrapper that treats a
    no-arg call as already-formatted HTML.
    """

    try:
        import jazzmin.templatetags.jazzmin as jazzmin_tags
    except ImportError:
        return

    # Idempotent.
    if getattr(jazzmin_tags, "_core_format_html_patched", False):
        return

    try:
        from django.utils.html import format_html as django_format_html
        from django.utils.safestring import mark_safe
    except ImportError:
        return

    def compat_format_html(format_string, *args, **kwargs):
        if not args and not kwargs:
            return mark_safe(format_string)
        return django_format_html(format_string, *args, **kwargs)

    jazzmin_tags.format_html = compat_format_html
    jazzmin_tags._core_format_html_patched = True


def _patch_django_avatar_get_user() -> None:
    """Make django-avatar template tags compatible with FreeIPA-backed users.

    django-avatar's template tags call `avatar.utils.get_user()` which expects
    either a real Django AUTH_USER_MODEL instance or a string/PK descriptor.

    This project uses non-persistent FreeIPA-backed user objects for
    `request.user`, so we treat any object that looks like an authenticated
    user (has `is_authenticated` + `get_username`) as already-resolved.

    This keeps `{% avatar request.user %}` and `{% avatar_url request.user %}`
    working without forcing DB-backed users.
    """

    try:
        import avatar.utils as avatar_utils
        import avatar.templatetags.avatar_tags as avatar_tags
    except ImportError:
        return

    # Idempotent.
    if getattr(avatar_utils, "_core_get_user_patched", False):
        return

    original_get_user = avatar_utils.get_user

    def compat_get_user(userdescriptor):
        # Unwrap SimpleLazyObject when it has already been evaluated.
        # If it is still the `empty` sentinel, leave it alone and let the
        # attribute checks below trigger evaluation safely.
        try:
            from django.utils.functional import empty

            wrapped = getattr(userdescriptor, "_wrapped", None)
            if wrapped is not None and wrapped is not empty and wrapped is not userdescriptor:
                userdescriptor = wrapped
        except Exception:
            pass

        # Our FreeIPA user objects are already resolved and behave like users.
        if getattr(userdescriptor, "is_authenticated", False) and hasattr(userdescriptor, "get_username"):
            return userdescriptor

        return original_get_user(userdescriptor)

    avatar_utils.get_user = compat_get_user
    # avatar_tags imports get_user into module scope; patch that reference too.
    avatar_tags.get_user = compat_get_user
    avatar_utils._core_get_user_patched = True


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        _patch_jazzmin_format_html()
        _patch_django_avatar_get_user()
