from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShownEntry:
    path: str
    started_at: float


class OnScreenHistory:
    def __init__(self, *, history_s: float = 30.0) -> None:
        self.history_s = history_s
        self._entries: list[ShownEntry] = []
        self._last_seen_at = 0.0

    def observe(self, path: str, *, now: float) -> None:
        if not path:
            return
        if self._entries and self._entries[-1].path == path:
            self._last_seen_at = now
            return
        started_at = (self._last_seen_at + now) / 2 if self._entries else now
        self._entries.append(ShownEntry(path, started_at))
        self._last_seen_at = now
        self._prune(now - self.history_s)

    def _prune(self, cutoff: float) -> None:
        keep_from = 0
        for index, entry in enumerate(self._entries):
            if entry.started_at <= cutoff:
                keep_from = index
        del self._entries[:keep_from]

    def path_at(self, when: float) -> str:
        for entry in reversed(self._entries):
            if entry.started_at <= when:
                return entry.path
        return ""
