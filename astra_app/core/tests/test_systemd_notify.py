import os
import socket
import sys
import unittest
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from unittest import mock


@lru_cache(maxsize=1)
def _send_systemd_notification() -> Callable[[str], None]:
    project_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_dir))
    from core.systemd_notify import send_systemd_notification

    return send_systemd_notification


class TestSystemdNotify(unittest.TestCase):
    def test_no_notify_socket_skips_send(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            send_systemd_notification = _send_systemd_notification()

            with mock.patch("core.systemd_notify.socket.socket") as socket_factory:
                send_systemd_notification("READY=1")

        socket_factory.assert_not_called()

    def test_abstract_socket_is_used(self) -> None:
        with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": "@notify"}, clear=True):
            socket_instance = mock.Mock()
            socket_factory = mock.MagicMock()
            socket_factory.return_value.__enter__.return_value = socket_instance

            send_systemd_notification = _send_systemd_notification()

            with mock.patch("core.systemd_notify.socket.socket", socket_factory):
                send_systemd_notification("READY=1")

        socket_factory.assert_called_once_with(socket.AF_UNIX, socket.SOCK_DGRAM)
        socket_instance.sendto.assert_called_once_with(b"READY=1", "\0notify")
