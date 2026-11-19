from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .playlist import PlaylistItem, parse_playlist, playlist_text


class PlaylistFollower:
    def __init__(self, playlist_file: Path, *,
                 take: Callable[[list[PlaylistItem]], None]) -> None:
        self._playlist_file = playlist_file
        self._take = take
        self._last_text = playlist_text(playlist_file)
        self._last_taken = parse_playlist(self._last_text)

    def read_now(self) -> None:
        self._follow(again=True)

    def tick(self) -> None:
        self._follow(again=False)

    def _follow(self, *, again: bool) -> None:
        # Windows can stamp two writes with one time, and a read that lands inside a write comes
        # back empty there, so a change is told by what the list says and an empty read waits.
        text = playlist_text(self._playlist_file)
        if text == self._last_text and not again:
            return
        items = self._last_taken if text == self._last_text else parse_playlist(text)
        if not items:
            return
        self._last_text = text
        if items == self._last_taken and not again:
            return
        self._last_taken = items
        self._take(items)
