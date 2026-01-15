import os
import socket


def send_systemd_notification(message: str) -> None:
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return

    address = notify_socket
    if notify_socket.startswith("@"):
        # Systemd encodes abstract sockets with a leading null byte.
        address = f"\0{notify_socket[1:]}"

    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.sendto(message.encode("utf-8"), address)
