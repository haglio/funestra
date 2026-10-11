"""What Genau tells its audio companion: which flick is up, and whether it is on.

Two datagrams over UDP.  ``FLICK <stem>`` goes out when a flick takes the screen,
so the companion can play the music cut beside it, followed by ``CLIP <stem>``,
the same news in the words a companion from before the rename listens for;
``VISIBLE 0|1`` goes out on the edge only, because the tick says it every frame
and the companion wants to hear it once.
"""
from __future__ import annotations

import socket
from pathlib import Path

from .renamed import answers_to_old_names

__all__ = [
    "GenauNotifier",
]

@answers_to_old_names({"notify_clip": "notify_flick"})
class GenauNotifier:
    def __init__(self, host: str, port: int, *, sock=None):
        self.host = host
        self.port = port
        self.sock = sock if sock is not None else socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last_visible_sent: int | None = None

    def _send(self, message: str) -> None:
        self.sock.sendto(message.encode("utf-8"), (self.host, self.port))

    def notify_flick(self, path: Path) -> None:
        self._send(f"FLICK {path.stem}")
        self._send(f"CLIP {path.stem}")

    def notify_visible(self, is_visible: bool) -> None:
        value = 1 if is_visible else 0
        if self.last_visible_sent == value:
            return
        self._send(f"VISIBLE {value}")
        self.last_visible_sent = value

    def close(self) -> None:
        self.sock.close()
