import json
from typing import Any

from django.core.cache import cache, caches
from django.core.management.base import BaseCommand


def _try_locmem_keys() -> list[str] | None:
    """Return raw keys if the cache backend exposes them (e.g., LocMemCache)."""
    # Use the actual backend instance (not the ConnectionProxy).
    backend = caches["default"]
    # LocMemCache exposes an internal dict called _cache.
    internal = getattr(backend, "_cache", None)
    if isinstance(internal, dict):
        return sorted(str(k) for k in internal.keys())
    return None


def _safe_serialize(value: Any, *, max_chars: int, pretty: bool) -> str:
    if value is None:
        return "<missing>"

    try:
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, indent=2 if pretty else None, sort_keys=pretty, default=str)
        else:
            text = str(value)
    except Exception:
        text = repr(value)

    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


class Command(BaseCommand):
    help = "Inspect Django cache entries (handy for FreeIPA cache debugging)."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true", help="List known FreeIPA cache keys.")
        parser.add_argument(
            "--keys",
            action="store_true",
            help="List all cache keys if supported by backend (LocMemCache only).",
        )
        parser.add_argument(
            "--get",
            dest="get_keys",
            action="append",
            help="Fetch a cache entry by key (repeatable).",
        )
        parser.add_argument(
            "--delete",
            dest="delete_keys",
            action="append",
            help="Delete a cache entry by key (repeatable).",
        )
        parser.add_argument(
            "--max-chars",
            type=int,
            default=4000,
            help="Truncate printed values to this many characters (0 = no truncation).",
        )
        parser.add_argument("--pretty", action="store_true", help="Pretty-print dict/list values as JSON.")

    def handle(self, *args, **options):
        max_chars: int = options["max_chars"]
        pretty: bool = options["pretty"]

        delete_keys = options.get("delete_keys") or []
        for key in delete_keys:
            cache.delete(key)
            self.stdout.write(f"deleted: {key}")

        get_keys = options.get("get_keys") or []
        for key in get_keys:
            val = cache.get(key)
            self.stdout.write(f"{key} = {_safe_serialize(val, max_chars=max_chars, pretty=pretty)}")

        if options.get("list"):
            # These are the keys used by core/backends.py.
            self.stdout.write("Known FreeIPA keys:")
            self.stdout.write("- freeipa_users_all")
            self.stdout.write("- freeipa_groups_all")
            self.stdout.write("- freeipa_user_<username>")
            self.stdout.write("- freeipa_group_<cn>")

        if options.get("keys"):
            keys = _try_locmem_keys()
            if keys is None:
                self.stdout.write("This cache backend does not expose keys (try LocMemCache or switch to Redis for inspectability).")
            elif not keys:
                backend = caches["default"]
                backend_path = f"{backend.__class__.__module__}.{backend.__class__.__name__}"
                self.stdout.write("<no keys>")
                self.stdout.write(f"cache backend: {backend_path}")
                self.stdout.write(
                    "Note: LocMemCache is per-process. Running `manage.py` in `podman-compose exec` starts a new Python process,"
                    " so it will NOT see the runserver/gunicorn process's in-memory cache."
                )
                self.stdout.write("If you need to inspect live keys, use a shared cache backend (e.g., Redis) or add an in-app debug view.")
            else:
                for k in keys:
                    self.stdout.write(k)

        # Default behavior if no flags: show a tiny hint.
        if not (delete_keys or get_keys or options.get("list") or options.get("keys")):
            self.stdout.write("Use --list, --keys, --get <key>, or --delete <key>.")
