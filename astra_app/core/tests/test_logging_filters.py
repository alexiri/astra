import logging

from core.logging_filters import SkipHealthzFilter
from django.test import SimpleTestCase


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def _record_level(message: str, *, level: int) -> logging.LogRecord:
    r = _record(message)
    r.levelno = level
    return r


class _Req:
    def __init__(self, path: str):
        self.path = path


class SkipHealthzFilterTests(SimpleTestCase):
    def test_skip_healthz_filter_drops_by_message(self) -> None:
        f = SkipHealthzFilter()
        self.assertIs(f.filter(_record('GET /healthz/ 200')), False)
        self.assertIs(f.filter(_record_level('Service Unavailable: /healthz/', level=logging.ERROR)), True)
        self.assertIs(f.filter(_record('GET /readyz/ 200')), False)
        self.assertIs(f.filter(_record_level('Service Unavailable: /readyz/', level=logging.ERROR)), True)

    def test_skip_healthz_filter_drops_by_request_attr(self) -> None:
        f = SkipHealthzFilter()

        r = _record("ignored")
        r.request = _Req("/healthz/")
        self.assertIs(f.filter(r), False)

        r = _record_level("ignored", level=logging.ERROR)
        r.request = _Req("/healthz/")
        self.assertIs(f.filter(r), True)

        r = _record("ignored")
        r.request = _Req("/readyz/")
        self.assertIs(f.filter(r), False)

        r = _record_level("ignored", level=logging.ERROR)
        r.request = _Req("/readyz/")
        self.assertIs(f.filter(r), True)

    def test_skip_healthz_filter_keeps_other_paths(self) -> None:
        f = SkipHealthzFilter()
        self.assertIs(f.filter(_record('GET / 200')), True)
        r = _record("ignored")
        r.request = _Req("/groups/")
        self.assertIs(f.filter(r), True)
