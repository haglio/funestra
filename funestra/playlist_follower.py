from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from app_support.written_file import WrittenFile

from .playlist import PlaylistItem, parse_playlist, playlist_text


class HeardList(NamedTuple):
    read_again_since: int
    items: list[PlaylistItem]


class PlaylistFollower:
    def __init__(self, playlist_file: Path, *,
                 take: Callable[[list[PlaylistItem]], None]) -> None:
        self._file = WrittenFile(playlist_file)
        self._take = take
        self._file.may_have_been_written()
        self._file.was_read()
        self._last_text = playlist_text(playlist_file)
        self._last_taken = parse_playlist(self._last_text)
        self._reading = threading.Lock()
        self._read_again = 0

    def look(self) -> HeardList | None:
        with self._reading:
            items = self._newer(again=False)
            return None if items is None else HeardList(self._read_again, items)

    def take_heard(self, heard: HeardList) -> None:
        if heard.read_again_since == self._read_again:
            self._take(heard.items)

    def read_now(self) -> None:
        with self._reading:
            self._read_again += 1
            items = self._newer(again=True)
        if items is not None:
            self._take(items)

    def _newer(self, *, again: bool) -> list[PlaylistItem] | None:
        if not self._file.may_have_been_written() and not again:
            return None
        if not self._file.holds_something:
            return None
        text = playlist_text(self._file.path)
        items = self._last_taken if text == self._last_text else parse_playlist(text)
        if not items:
            return None
        self._file.was_read()
        self._last_text = text
        if items == self._last_taken and not again:
            return None
        self._last_taken = items
        return items
