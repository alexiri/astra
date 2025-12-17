import logging
from typing import Any, Optional


class SkipHealthzFilter(logging.Filter):
    """Drop log records associated with health endpoints."""

    def __init__(self, prefixes: tuple[str, ...] = ("/healthz", "/readyz")) -> None:
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        path = _extract_request_path(record)
        if path is not None:
            return not any(path.startswith(prefix) for prefix in self.prefixes)

        message = record.getMessage()
        return not any(prefix in message for prefix in self.prefixes)


def _extract_request_path(record: logging.LogRecord) -> Optional[str]:
    request = getattr(record, "request", None)
    path = _path_from_request_obj(request)
    if path:
        return path

    args = getattr(record, "args", None)
    if isinstance(args, tuple):
        for arg in args:
            path = _path_from_request_obj(arg)
            if path:
                return path

    return None


def _path_from_request_obj(obj: Any) -> Optional[str]:
    if obj is None:
        return None

    path = getattr(obj, "path", None) or getattr(obj, "path_info", None)
    if isinstance(path, str) and path:
        return path

    return None
