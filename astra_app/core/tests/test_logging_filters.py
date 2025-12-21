import logging

from core.logging_filters import SkipHealthzFilter


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


class _Req:
    def __init__(self, path: str):
        self.path = path


def test_skip_healthz_filter_drops_by_message():
    f = SkipHealthzFilter()
    assert f.filter(_record('GET /healthz/ 200')) is False
    assert f.filter(_record('Service Unavailable: /healthz/')) is False
    assert f.filter(_record('GET /readyz/ 200')) is False
    assert f.filter(_record('Service Unavailable: /readyz/')) is False


def test_skip_healthz_filter_drops_by_request_attr():
    f = SkipHealthzFilter()
    r = _record("ignored")
    r.request = _Req("/healthz/")
    assert f.filter(r) is False

    r = _record("ignored")
    r.request = _Req("/readyz/")
    assert f.filter(r) is False


def test_skip_healthz_filter_keeps_other_paths():
    f = SkipHealthzFilter()
    assert f.filter(_record('GET / 200')) is True
    r = _record("ignored")
    r.request = _Req("/groups/")
    assert f.filter(r) is True
