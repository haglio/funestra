"""A window takes the list its playlist file holds whenever that list changes."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .playlist import PlaylistItem, read_playlist

__all__: list[str] = []


class PlaylistFollower:
    """Hands on the list the playlist file holds, as often as that list changes."""

    def __init__(self, playlist_file: Path, *,
                 take: Callable[[list[PlaylistItem]], None]) -> None:
        self._playlist_file = playlist_file
        self._take = take
        self._last_taken = read_playlist(playlist_file)

    def read_now(self) -> None:
        self._follow(again=True)

    def tick(self) -> None:
        self._follow(again=False)

    def _follow(self, *, again: bool) -> None:
        items = read_playlist(self._playlist_file)
        if not items or (items == self._last_taken and not again):
            return
        self._last_taken = items
        self._take(items)
