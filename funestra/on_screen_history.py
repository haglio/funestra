"""What one Funestra had on screen over the last half minute, so a late word can be back-dated.

Speech recognition only finalizes a phrase once the speaker stops, so a spoken
"lock portrait" arrives a second or two after the speaker began saying it, by
which time an advancing Funestra may already be on the next video or picture.
Sampling what each Funestra shows into this history lets the word be resolved
to what was on screen when the utterance *started*, which is the one meant.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShownEntry:
    path: str
    started_at: float


class OnScreenHistory:
    """A short (path, started-at) history built from periodic samples."""

    def __init__(self, *, history_s: float = 30.0) -> None:
        self.history_s = history_s
        self._entries: list[ShownEntry] = []
        self._last_seen_at = 0.0

    def observe(self, path: str, *, now: float) -> None:
        """Record that *path* is what is on screen as of *now*.

        A switch is only ever bounded by the two samples that straddle it, so it
        is dated to their midpoint: the residual error is then half a sample
        interval in either direction rather than a full interval in one.
        """
        if not path:
            # A Funestra's status carries no path before it has loaded
            # anything: a gap in the record, not a switch to something new.
            return
        if self._entries and self._entries[-1].path == path:
            self._last_seen_at = now
            return
        started_at = (self._last_seen_at + now) / 2 if self._entries else now
        self._entries.append(ShownEntry(path, started_at))
        self._last_seen_at = now
        self._prune(now - self.history_s)

    def _prune(self, cutoff: float) -> None:
        """Drop entries the window no longer needs.

        The newest entry that started at or before *cutoff* is what a query at
        the window's edge must still resolve to, so it is kept along with
        everything after it.
        """
        keep_from = 0
        for index, entry in enumerate(self._entries):
            if entry.started_at <= cutoff:
                keep_from = index
        del self._entries[:keep_from]

    def path_at(self, when: float) -> str:
        """What was on screen at *when*, or "" when the history doesn't reach it."""
        for entry in reversed(self._entries):
            if entry.started_at <= when:
                return entry.path
        return ""
