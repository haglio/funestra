from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .playlist import PlaylistItem, parse_playlist, playlist_text
from .replaced_file import ReplacedFile


class PlaylistFollower:
    def __init__(self, playlist_file: Path, *,
                 take: Callable[[list[PlaylistItem]], None]) -> None:
        self._file = ReplacedFile(playlist_file)
        self._take = take
        self._file.replaced()
        self._file.was_read()
        self._last_text = playlist_text(playlist_file)
        self._last_taken = parse_playlist(self._last_text)

    def read_now(self) -> None:
        self._follow(again=True)

    def tick(self) -> None:
        self._follow(again=False)

    def _follow(self, *, again: bool) -> None:
        if not self._file.replaced() and not again:
            return
        if not self._file.holds_something:
            return
        text = playlist_text(self._file.path)
        items = self._last_taken if text == self._last_text else parse_playlist(text)
        if not items:
            return
        self._file.was_read()
        self._last_text = text
        if items == self._last_taken and not again:
            return
        self._last_taken = items
        self._take(items)
