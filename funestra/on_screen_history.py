from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShownEntry:
    path: str
    started_at: float
    asked_for: bool = False


class OnScreenHistory:
    def __init__(self, *, history_s: float = 30.0) -> None:
        self.history_s = history_s
        self._entries: list[ShownEntry] = []
        self._last_seen_at = 0.0
        self._a_change_is_asked_for = False

    def a_change_was_asked_for(self) -> None:
        self._a_change_is_asked_for = True

    def observe(self, path: str, *, now: float, playing_for: float | None = None) -> None:
        if not path:
            return
        if self._entries and self._entries[-1].path == path:
            self._last_seen_at = now
            return
        self._entries.append(ShownEntry(path, self._started_at(now, playing_for),
                                        self._a_change_is_asked_for))
        self._a_change_is_asked_for = False
        self._last_seen_at = now
        self._prune(now - self.history_s)

    def _started_at(self, now: float, playing_for: float | None) -> float:
        if not self._entries:
            return now
        if playing_for is None:
            return (self._last_seen_at + now) / 2
        return max(self._last_seen_at, now - playing_for)

    def _prune(self, cutoff: float) -> None:
        keep_from = 0
        for index, entry in enumerate(self._entries):
            if entry.started_at <= cutoff:
                keep_from = index
        del self._entries[:keep_from]

    def path_at(self, when: float) -> str:
        for entry in reversed(self._entries):
            if entry.started_at <= when or entry.asked_for:
                return entry.path
        return ""
