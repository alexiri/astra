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
    except Exception:
        return

    # Idempotent.
    if getattr(jazzmin_tags, "_core_format_html_patched", False):
        return

    try:
        from django.utils.html import format_html as django_format_html
        from django.utils.safestring import mark_safe
    except Exception:
        return

    def compat_format_html(format_string, *args, **kwargs):
        if not args and not kwargs:
            return mark_safe(format_string)
        return django_format_html(format_string, *args, **kwargs)

    jazzmin_tags.format_html = compat_format_html
    jazzmin_tags._core_format_html_patched = True


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        _patch_jazzmin_format_html()
