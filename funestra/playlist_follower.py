from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from .playlist import PlaylistItem, parse_playlist, playlist_text

_Written = tuple[int, int, int]


def _written(playlist_file: Path) -> _Written | None:
    # A playlist is replaced, never rewritten in place, so each write is a new file with an
    # identity of its own, though Windows can stamp two writes with one time.
    try:
        found = os.stat(playlist_file)
    except OSError:
        return None
    return (found.st_ino, found.st_size, found.st_mtime_ns)


class PlaylistFollower:
    def __init__(self, playlist_file: Path, *,
                 take: Callable[[list[PlaylistItem]], None]) -> None:
        self._playlist_file = playlist_file
        self._take = take
        self._last_written = _written(playlist_file)
        self._last_text = playlist_text(playlist_file)
        self._last_taken = parse_playlist(self._last_text)

    def read_now(self) -> None:
        self._follow(again=True)

    def tick(self) -> None:
        self._follow(again=False)

    def _follow(self, *, again: bool) -> None:
        written = _written(self._playlist_file)
        if written == self._last_written and not again:
            return
        if written is None or not written[1]:
            return
        text = playlist_text(self._playlist_file)
        items = self._last_taken if text == self._last_text else parse_playlist(text)
        if not items:
            return
        self._last_written, self._last_text = written, text
        if items == self._last_taken and not again:
            return
        self._last_taken = items
        self._take(items)
