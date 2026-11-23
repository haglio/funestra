from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from .paused_flag import PausedFlag
from .playlist_follower import HeardList, PlaylistFollower


class Told(NamedTuple):
    paused: bool | None
    playlist: HeardList | None
    commands: list[str]


NOTHING_NEW = Told(None, None, [])


class FilesItIsToldThrough:
    def __init__(self, *, commands: Callable[[], list[str]], paused: PausedFlag | None,
                 playlist: PlaylistFollower | None, paused_at_the_start: bool | None) -> None:
        self._commands = commands
        self._paused = paused
        self._playlist = playlist
        self._paused_said = paused_at_the_start

    def read(self) -> Told | None:
        commands = self._commands()
        paused = None if self._paused is None else self._paused.read()
        playlist = None if self._playlist is None else self._playlist.look()
        newly_paused = None if paused == self._paused_said else paused
        self._paused_said = paused
        if not commands and newly_paused is None and playlist is None:
            return None
        return Told(newly_paused, playlist, commands)
