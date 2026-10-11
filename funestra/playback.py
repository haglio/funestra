"""What a Funestra is playing: the list it was handed, the item on screen, and how it is being played.

Auto-advance is the one move mpv makes itself: the item after the one on
screen is staged as mpv's prefetch entry, mpv rolls onto it at end-of-file,
and each tick :meth:`Playback.advance` notices the roll, moves the index onto
it and stages the item after that.  A deliberate step still cold-loads.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from .funscript import Funscript
from .funscript import load as load_funscript
from .play_points import PlayPoints
from .playback_rate import clamp_rate
from .playlist import PlaylistItem
from .renamed import answers_to_old_names
from .scripted_device import REWIND_MS, ScriptedDevice
from .seeking import OwedSeek, seek_if_taken

__all__ = [
    "Playback",
    "funscripts_of",
]

logger = logging.getLogger(__name__)


def funscripts_of(items: Iterable[PlaylistItem]) -> dict[Path, Path]:
    return {item.path: item.funscript for item in items if item.funscript is not None}


@answers_to_old_names({"player": "engine"})
class Playback:
    def __init__(
        self,
        playlist: list[Path],
        *,
        engine,
        start_paused: bool = False,
        locked: bool = False,
        play_points: PlayPoints | None = None,
        funscripts: Mapping[Path, Path] | None = None,
        tcode=None,
    ) -> None:
        if not playlist:
            raise ValueError("playlist must not be empty")
        self._device = ScriptedDevice(tcode, enabled=False)
        self._last_pos_ms = 0.0
        self._playlist = list(playlist)
        self._funscripts = dict(funscripts or {})
        self._loaded_funscript: tuple[Path | None, Funscript | None] = (None, None)
        self._engine = engine
        self._paused = start_paused
        self._locked = locked
        self._speed = 1.0
        self._index = 0
        self._loads = 0
        self._play_points = play_points or PlayPoints(None)
        self._owed_seek = OwedSeek()
        self._versions: dict[Path, Path] = {}
        self._switching_versions = False
        self._mark: int | None = None
        self._ab_loop: tuple[int, int] | None = None
        self._held_at: float | None = None
        if locked:
            engine.set_loop_file(True)
        self.load(0)

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def current_video(self) -> Path:
        return self._playlist[self._index]

    @property
    def index(self) -> int:
        return self._index

    @property
    def loads(self) -> int:
        return self._loads

    @property
    def switching_versions(self) -> bool:
        return self._switching_versions

    @property
    def portrait(self) -> bool | None:
        width, height = self._engine.source_dims
        return height > width if width and height else None

    def funscript_of(self, video: Path) -> Path | None:
        return self._funscripts.get(video)

    @property
    def current_funscript(self) -> Funscript | None:
        path = self._funscripts.get(self.current_video)
        if path != self._loaded_funscript[0]:
            self._loaded_funscript = (path, None if path is None else load_funscript(path))
        return self._loaded_funscript[1]

    @property
    def funscript_as_played(self) -> Funscript | None:
        script = self.current_funscript
        if script is None:
            return None
        if self._ab_loop is not None:
            return script.looped(*self._ab_loop)
        if self._locked:
            return script.looped(0, round(self._engine.duration_ms))
        return script

    @property
    def has_funscript(self) -> bool:
        return self.current_funscript is not None

    @property
    def funscript_resting(self) -> bool:
        script = self.funscript_as_played
        return script is not None and script.is_resting_at(int(self.position_ms))

    def set_tcode_enabled(self, enabled: bool) -> None:
        self._device.set_enabled(enabled)

    def take_the_device_over(self) -> None:
        self._device.take_over()

    @property
    def max_intensity(self) -> int:
        return self._device.max_intensity

    def set_max_intensity(self, max_intensity: int) -> None:
        self._device.set_max_intensity(max_intensity)

    @property
    def showing(self) -> Path:
        return self._versions.get(self.current_video, self.current_video)

    @property
    def idle(self) -> bool:
        """Whether the engine has nothing up at all: the item would not open,
        or it was let go of."""
        return self._engine.idle

    def let_go(self) -> None:
        """Play nothing, so the file on screen can be moved or deleted."""
        self._engine.stop()

    def step_version(self, versions: list[Path], delta: int) -> None:
        showing = self.showing
        if len(versions) < 2 or showing not in versions:
            return
        target = versions[(versions.index(showing) + delta) % len(versions)]
        clip = self.current_video
        if target == clip:
            self._versions.pop(clip, None)
        else:
            self._versions[clip] = target
        self.load(self._index)
        self._switching_versions = True

    @property
    def name_on_screen(self) -> str:
        name = self.current_video.stem
        if not self._switching_versions and self.showing == self.current_video:
            return name
        return f"{name} ({self.showing.name})"

    @property
    def playlist(self) -> list[Path]:
        return list(self._playlist)

    @property
    def playlist_length(self) -> int:
        return len(self._playlist)

    @property
    def position_ms(self) -> float:
        return self._engine.position_ms

    @property
    def duration_ms(self) -> float:
        return self._engine.duration_ms

    @property
    def showing_picture(self) -> bool:
        return self._picture_put_up or self._engine.showing_picture

    def step(self, delta: int) -> None:
        self.load(self._index + delta)

    def seek_by(self, delta_ms: float) -> None:
        self.seek_to(self._engine.position_ms + delta_ms)

    def seek_to(self, ms: float) -> None:
        self._owed_seek.owe(ms)
        self._owed_seek.pay(self._engine, self._seek_now)

    def _seek_now(self, ms: float) -> bool:
        floor = 0.0 if self._mark is None else float(self._mark)
        target = max(floor, min(self._engine.duration_ms, ms))
        taken = seek_if_taken(self._engine, target)
        if taken:
            self._device.take_over()
        return taken

    @property
    def mark(self) -> int | None:
        return self._mark

    def set_mark(self, in_ms: int | None) -> None:
        self._mark = in_ms

    @property
    def ab_loop(self) -> tuple[int, int] | None:
        return self._ab_loop

    def set_ab_loop(self, in_ms: int, out_ms: int) -> None:
        self._mark = None
        self._ab_loop = (in_ms, out_ms)
        self._engine.set_ab_loop(in_ms, out_ms)

    def clear_ab_loop(self) -> None:
        self._mark = None
        self._ab_loop = None
        self._engine.clear_ab_loop()

    def set_paused(self, paused: bool) -> None:
        if paused == self._paused:
            return
        self._paused = paused
        self._engine.set_paused(paused)
        if not paused:
            self._device.take_over()
            self._held_at = self._engine.position_ms

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(self, speed: float) -> None:
        self._speed = clamp_rate(speed)
        self._engine.set_speed(self._speed)
        self._device.take_over()

    def set_pace(self, seconds: float) -> None:
        self._engine.set_pace(seconds)

    def show_frame(self, frame: Path) -> None:
        self._frame_on_screen = frame
        self._picture_put_up = True
        self._engine.swap_still(frame)

    def clear_frame(self) -> None:
        if self._frame_on_screen is not None:
            self._frame_on_screen = None
            self._engine.swap_still(self.showing)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._engine.set_loop_file(locked)
        if locked:
            self._engine.clear_next()
        else:
            self._stage_next()

    def advance(self) -> None:
        self._owed_seek.pay(self._engine, self._seek_now)
        position_ms = self._engine.position_ms
        self._play_points.observe(self.current_video, position_ms, self._engine.duration_ms)
        if self._paused:
            return
        if not self._locked and self._engine.advanced_to_next:
            self._play_points.ended()
            self._frame_on_screen = None
            self._picture_put_up = False
            self._mark = None
            self._ab_loop = None
            self._index = (self._index + 1) % len(self._playlist)
            self._loads += 1
            self._engine.drop_consumed()
            self._stage_next()
            self._owed_seek.owe(self._play_points.point_for(self.current_video) or None)
            self._device.take_over()
        elif position_ms + REWIND_MS < self._last_pos_ms:
            self._device.take_over()
        self._last_pos_ms = position_ms
        if self._the_picture_has_resumed(position_ms):
            self._device.drive(position_ms, self.funscript_as_played, speed=self._speed)

    def _the_picture_has_resumed(self, position_ms: float) -> bool:
        """Un-pausing is a request, not a picture: the device waits for the
        first frame after it, a still counting as there at once."""
        if self._held_at is None:
            return True
        if position_ms == self._held_at and not self._engine.showing_picture:
            return False
        self._held_at = None
        return True

    def discard(self) -> None:
        if len(self._playlist) <= 1:
            return
        self._versions.pop(self._playlist.pop(self._index), None)
        self.load(self._index)

    def play_file(self, video: Path, funscript: Path | None = None) -> None:
        if funscript is not None:
            self._funscripts[video] = funscript
        for i, path in enumerate(self._playlist):
            if path == video:
                self.load(i)
                return
        self._playlist.insert(self._index + 1, video)
        self.load(self._index + 1)

    def load_playlist(
        self, playlist: list[Path], funscripts: Mapping[Path, Path] | None = None,
    ) -> None:
        if not playlist:
            raise ValueError("playlist must not be empty")
        self._playlist = list(playlist)
        self._funscripts = dict(funscripts or {})
        self._versions = {}
        self.load(0)

    def replace_playlist(
        self, playlist: list[Path], funscripts: Mapping[Path, Path] | None = None,
    ) -> None:
        if not playlist:
            raise ValueError("playlist must not be empty")
        current = self.current_video
        chosen = self._versions.get(current)
        self._playlist = list(playlist)
        self._funscripts = dict(funscripts or {})
        self._versions = {} if chosen is None else {current: chosen}
        for i, path in enumerate(self._playlist):
            if path == current:
                self._index = i
                self._stage_next()
                return
        if self._frame_on_screen in self._playlist:
            self._index = self._playlist.index(self._frame_on_screen)
            self._frame_on_screen = None
            self._versions = {}
            self._stage_next()
            return
        self._versions = {}
        self.load(0)

    def load(self, index: int) -> None:
        self._play_points.leave()
        self._switching_versions = False
        self._frame_on_screen = None
        self._picture_put_up = False
        self._index = index % len(self._playlist)
        self._loads += 1
        clip = self._playlist[self._index]
        video = self._versions.get(clip, clip)
        logger.info("Loading: %s", video.name)
        self.clear_ab_loop()
        self._engine.load(video)
        self._engine.set_paused(self._paused)
        self._stage_next()
        self._owed_seek.owe(self._play_points.point_for(clip) or None)
        self._device.take_over()
        self._last_pos_ms = 0.0

    def _stage_next(self) -> None:
        if self._locked:
            return
        nxt = self._playlist[(self._index + 1) % len(self._playlist)]
        self._engine.stage_next(self._versions.get(nxt, nxt))

    def close(self) -> None:
        self._play_points.leave()
        self._device.close()
        self._engine.close()
