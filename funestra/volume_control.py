from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .dashboard import ask
from .volume import MAX_VOLUME, MIN_VOLUME, VolumeHud


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

    def set(self, level: int, muted: bool) -> None:
        if self._live:
            self._set(VolumeHud(volume=max(MIN_VOLUME, min(MAX_VOLUME, level)), muted=muted))

    def _set(self, hud: VolumeHud) -> None:
        self._hud = hud
        self._engine.set_volume(hud.volume)
        self._engine.set_muted(hud.muted)


class AppVolume:
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


def told_to_the_host(move: Callable[..., None], volume, on_moved) -> Callable[..., None]:
    def moved(*args) -> None:
        move(*args)
        if on_moved is not None:
            on_moved(volume.hud)
    return moved
