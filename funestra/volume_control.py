"""A Funestra's volume chip: its own level and mute, or the room's.

A Funestra whose sound is its own sets mpv's level and mute from the chip it
draws.  One whose sound is the room's -- the Main Funestra, whose mpv is one of
two sinks the room drives -- shows the level the room publishes and asks the
room for a new one; the ask shows at once so the slider does not trail the
pointer, and the room's answer overwrites it either way.

The chip is a part of the row the panel draws, so the panel is what places a
press on it (:class:`funestra.hud_row.RowPress`): both controls answer the
same two verbs, and neither hit-tests a window of its own any more.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .dashboard import ask
from .volume import MAX_VOLUME, MIN_VOLUME, VolumeHud

__all__: list[str] = []


class VolumeControl:
    def __init__(self, engine, *, live: bool = True, muted: bool = True) -> None:
        self._engine = engine
        self._live = live
        self._hud = VolumeHud(volume=MAX_VOLUME if live else MIN_VOLUME, muted=muted)

    @property
    def hud(self) -> VolumeHud:
        return self._hud

    def toggle_mute(self) -> None:
        self.set_muted(not self._hud.muted)

    def set_muted(self, muted: bool) -> None:
        if self._live:
            self._set(replace(self._hud, muted=muted))

    def set_level(self, volume: int) -> None:
        if self._live:
            self._set(VolumeHud(volume=volume, muted=False))

    def _set(self, hud: VolumeHud) -> None:
        self._hud = hud
        self._engine.set_volume(hud.volume)
        self._engine.set_muted(hud.muted)


class RoomVolume:
    def __init__(self, engine, *, dashboard_cmd_file: Path | None, live: bool) -> None:
        self._engine = engine
        self._dashboard_cmd_file = dashboard_cmd_file
        self._hud = VolumeHud()
        if live:
            engine.set_muted(False)

    @property
    def hud(self) -> VolumeHud:
        return self._hud

    def set(self, level: int, muted: bool) -> None:
        level = max(MIN_VOLUME, min(MAX_VOLUME, level))
        self._hud = VolumeHud(volume=level, muted=muted)
        self._engine.set_volume(0 if muted else level)

    def toggle_mute(self) -> None:
        self._hud = replace(self._hud, muted=not self._hud.muted)
        ask(self._dashboard_cmd_file, "audio_mute" if self._hud.muted else "audio_unmute")

    def set_level(self, level: int) -> None:
        self._hud = VolumeHud(volume=level, muted=False)
        ask(self._dashboard_cmd_file, f"audio_set_volume|{level}")
