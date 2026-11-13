from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

from shared_ui.orientation import PORTRAIT, orientation_of_size

from .funscript import Funscript
from .lineup import Lineup
from .play_points import PlayPoints
from .playback_rate import NORMAL_RATE, clamp_rate
from .playback_setup import PLAIN_PLAYBACK, PlaybackSetup
from .playlist import PlaylistItem
from .rides_along import RidesAlong, funscripts_of, points_of_interest_of
from .scripted_device import ScriptedDevice
from .seeking import OwedSeek, seek_if_taken

logger = logging.getLogger(__name__)


class Playback:
    def __init__(
        self,
        playlist: list[Path],
        *,
        engine,
        setup: PlaybackSetup = PLAIN_PLAYBACK,
    ) -> None:
        self._lineup = Lineup(playlist)
        self._rides = RidesAlong(setup.funscripts, setup.points_of_interest)
        self._device = ScriptedDevice(setup.tcode, enabled=False)
        self._engine = engine
        self._points_told: tuple = ()
        self._paused, self._locked = setup.start_paused, setup.locked
        self._held_by_the_pace = False
        self._speed = NORMAL_RATE
        self._loads = 0
        self._play_points = setup.play_points or PlayPoints(None)
        self._owed_seek = OwedSeek()
        self._switching_versions = False
        self._mark: int | None = None
        self._ab_loop: tuple[int, int] | None = None
        if setup.locked:
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
        return self._lineup.current

    @property
    def index(self) -> int:
        return self._lineup.index

    @property
    def loads(self) -> int:
        return self._loads

    @property
    def switching_versions(self) -> bool:
        return self._switching_versions

    @property
    def portrait(self) -> bool | None:
        width, height = self._engine.source_dims
        return orientation_of_size(width, height) == PORTRAIT if width and height else None

    def funscript_of(self, video: Path) -> Path | None:
        return self._rides.funscript_path(video)

    @property
    def current_funscript(self) -> Funscript | None:
        return self._rides.funscript(self.showing, self.current_video)

    @property
    def funscript_as_played(self) -> Funscript | None:
        script = self.current_funscript
        if script is None:
            return None
        if self._ab_loop is not None:
            return script.looped(*self._ab_loop)
        if self._holds:
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
        return self._lineup.showing

    @property
    def idle(self) -> bool:
        return self._engine.idle

    def let_go(self) -> None:
        self._engine.stop()

    def step_version(self, versions: Sequence[Path | PlaylistItem], delta: int) -> None:
        if self._lineup.step_version([self._version_file_of(version) for version in versions],
                                     delta):
            self.load(self.index)
            self._switching_versions = True

    def _version_file_of(self, version: Path | PlaylistItem) -> Path:
        if isinstance(version, PlaylistItem):
            self._rides.take(version.path, version.funscript, version.points_of_interest)
            return version.path
        return Path(version)

    def forget_versions(self) -> None:
        self._lineup.forget_versions()

    @property
    def name_on_screen(self) -> str:
        name = self.current_video.stem
        if not self._switching_versions and self.showing == self.current_video:
            return name
        return f"{name} ({self.showing.name})"

    @property
    def playlist(self) -> list[Path]:
        return self._lineup.videos

    @property
    def playlist_length(self) -> int:
        return len(self._lineup)

    @property
    def position_ms(self) -> float:
        return self._engine.position_ms

    @property
    def duration_ms(self) -> float:
        return self._engine.duration_ms

    @property
    def showing_image(self) -> bool:
        return self._lineup.an_image_was_put_up or self._engine.showing_image

    def step(self, delta: int) -> None:
        self.load(self.index + delta)

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
            self._device.resume_at(self._engine.position_ms)

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(self, speed: float) -> None:
        self._speed = clamp_rate(speed)
        self._engine.set_speed(self._speed)
        self._device.take_over()

    def set_pace(self, seconds: float) -> None:
        self._engine.set_pace(seconds)
        if self._held_by_the_pace != (not seconds):
            self._held_by_the_pace = not seconds
            self._hold_or_roll()

    def hold_image_for(self, seconds: float) -> None:
        self._engine.hold_image_for(seconds)

    def show_frame(self, frame: Path) -> None:
        self._lineup.put_up(frame)
        self._engine.swap_image(frame)
        self._stage_next()
        self._tell_the_places()

    def clear_frame(self) -> None:
        if self._lineup.take_down_the_frame():
            self._engine.swap_image(self.showing)
            self._stage_next()
            self._tell_the_places()

    def _tell_the_places(self) -> None:
        points = self._rides.points(self._lineup.on_screen)
        if points != self._points_told:
            self._points_told = points
            self._engine.set_points_of_interest(points)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._hold_or_roll()

    @property
    def _holds(self) -> bool:
        return self._locked or self._held_by_the_pace

    def _hold_or_roll(self) -> None:
        self._engine.set_loop_file(self._holds)
        if self._holds:
            self._engine.clear_next()
        else:
            self._stage_next()

    def advance(self) -> None:
        self._owed_seek.pay(self._engine, self._seek_now)
        position_ms = self._engine.position_ms
        self._play_points.observe(self.current_video, position_ms, self._engine.duration_ms)
        if self._paused:
            return
        rolled = self.follow_a_roll()
        self._device.follow(position_ms, self.funscript_as_played, speed=self._speed,
                            rolled=rolled, over_an_image=self._engine.showing_image)

    def follow_a_roll(self) -> bool:
        if not self._engine.advanced_to_next:
            return False
        self._play_points.ended()
        self._lineup.roll()
        self._mark = None
        self._ab_loop = None
        self._loads += 1
        self._engine.settle_on_the_next()
        self._stage_next()
        self._owed_seek.owe(self._play_points.point_for(self.current_video) or None)
        self._device.take_over()
        self._tell_the_places()
        return True

    def discard(self) -> None:
        if self._lineup.discard():
            self.load(self.index)

    def play_file(self, video: Path, funscript: Path | None = None,
                  points_of_interest: tuple = ()) -> None:
        self._rides.take(video, funscript, points_of_interest)
        listed_at = self._lineup.place_of(video)
        if listed_at is not None:
            self.load(listed_at)
            return
        self._lineup.put_next(video)
        self.load(self.index + 1)

    def play_next(self, video: Path, funscript: Path | None = None,
                  points_of_interest: tuple = ()) -> None:
        self._rides.take(video, funscript, points_of_interest)
        if video == self.current_video:
            return
        self._lineup.put_next(video)
        self._stage_next()

    def load_playlist(
        self, playlist: list[Path], funscripts: Mapping[Path, Path] | None = None,
        points_of_interest: Mapping[Path, tuple] | None = None,
    ) -> None:
        self._lineup.start_over_with(playlist)
        self._rides = RidesAlong(funscripts, points_of_interest)
        self.load(0)

    def replace_playlist(
        self, playlist: list[Path], funscripts: Mapping[Path, Path] | None = None,
        points_of_interest: Mapping[Path, tuple] | None = None,
    ) -> None:
        stands_on_what_is_on_screen = self._lineup.take(playlist)
        self._rides = RidesAlong(funscripts, points_of_interest)
        if stands_on_what_is_on_screen:
            self._stage_next()
        else:
            self.load(0)
        self._tell_the_places()

    def take_the_list(self, items: Sequence[PlaylistItem]) -> None:
        self.replace_playlist([item.path for item in items], funscripts_of(items),
                              points_of_interest_of(items))

    def load(self, index: int) -> None:
        self._play_points.leave()
        self._switching_versions = False
        self._lineup.stand_at(index)
        self._loads += 1
        video = self.showing
        logger.info("Loading: %s", video.name)
        self.clear_ab_loop()
        self._engine.load(video)
        self._engine.set_paused(self._paused)
        self._stage_next()
        self._owed_seek.owe(self._play_points.point_for(self.current_video) or None)
        self._device.start_an_item()
        self._tell_the_places()

    def _stage_next(self) -> None:
        if self._holds:
            return
        self._engine.stage_next(self._lineup.what_the_roll_puts_up)

    def close(self) -> None:
        self._play_points.leave()
        self._device.close()
        self._engine.close()
