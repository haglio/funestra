from __future__ import annotations

import socket
from typing import Protocol

from app_support import ports
from app_support.osr2_hold import PARK, hold_tcode

POSITION_MAX = 9999

PARK_COMMAND = hold_tcode(PARK)


def to_tcode_position(percent: float) -> int:
    return round(percent * POSITION_MAX / 100)


HANDOFF_MS = 300


class HandoffGlide:
    def __init__(self) -> None:
        self._armed = False
        self._until: float | None = None

    def begin(self) -> None:
        self._armed, self._until = True, None

    def interval_ms(self, interval_ms: int, now: float) -> int:
        if self._armed:
            self._armed, self._until = False, now + HANDOFF_MS / 1000
        if self._until is None:
            return interval_ms
        if now >= self._until:
            self._until = None
            return interval_ms
        return max(interval_ms, HANDOFF_MS)


def format_tcode_command(axis: str, position: int, interval_ms: int) -> str:
    position = max(0, min(POSITION_MAX, position))
    interval_ms = max(0, interval_ms)
    return f"{axis}{position:04d}I{interval_ms}"


class TCodeSink(Protocol):
    def want(self, wanted: bool) -> None: ...
    def send(self, command: str) -> None: ...
    def close(self) -> None: ...


class UdpTCodeSink:
    def __init__(
        self, host: str = "127.0.0.1", port: int = ports.TCODE_UDP, *, sock=None,
    ) -> None:
        self._host = host
        self._port = port
        self._closed = False
        self._sock = sock if sock is not None else socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def want(self, wanted: bool) -> None:
        pass

    def send(self, command: str) -> None:
        if self._closed:
            return
        try:
            self._sock.sendto((command + "\n").encode("ascii"), (self._host, self._port))
        except OSError:
            if not self._closed:
                raise

    def close(self) -> None:
        self._closed = True
        self._sock.close()
