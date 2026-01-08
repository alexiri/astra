from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class TestSendQueuedMailCommand(SimpleTestCase):
    def test_skips_when_lock_not_acquired(self) -> None:
        from core.management.commands import send_queued_mail as command_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (False,)

        mock_connection = MagicMock()
        mock_connection.vendor = "postgresql"
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        with (
            patch.object(command_module, "connection", mock_connection),
            patch.object(command_module.PostOfficeCommand, "handle") as delegate_handle,
        ):
            command_module.Command().handle()

        delegate_handle.assert_not_called()

    def test_runs_when_lock_acquired(self) -> None:
        from core.management.commands import send_queued_mail as command_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (True,)

        mock_connection = MagicMock()
        mock_connection.vendor = "postgresql"
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        with (
            patch.object(command_module, "connection", mock_connection),
            patch.object(command_module.PostOfficeCommand, "handle") as delegate_handle,
        ):
            command_module.Command().handle(verbosity=2)

        delegate_handle.assert_called_once()
        # Ensure we attempted to unlock at the end.
        assert any(
            "pg_advisory_unlock" in str(call.args[0])
            for call in mock_cursor.execute.call_args_list
        )
