from __future__ import annotations

import threading

__all__: list[str] = []


class DrawnFile:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._showing: str | None = None
        self._awaited: str | None = None
        self._opened: str | None = None
        self._awaited_frame_drawn = False
        self._owed = False

    def asked_for(self, path: str) -> None:
        with self._lock:
            self._awaited = path
            self._awaited_frame_drawn = False

    def opened(self, path: str | None) -> None:
        with self._lock:
            self._opened = path

    def started(self, path: str | None) -> None:
        with self._lock:
            if self._awaited is not None:
                if path != self._awaited:
                    return
                self._owed = self._owed or self._awaited_frame_drawn
                self._awaited = None
            self._showing = path

    def announced(self) -> None:
        with self._lock:
            self._owed = True

    @property
    def owed(self) -> bool:
        with self._lock:
            return self._owed

    def drawn(self, *, new_frame: bool) -> str | None:
        with self._lock:
            self._owed = False
            if self._awaited is None:
                return self._showing
            if new_frame and self._opened == self._awaited:
                self._awaited_frame_drawn = True
            return None
