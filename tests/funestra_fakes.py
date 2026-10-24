from __future__ import annotations

from pathlib import Path

from funestra.funscript import Funscript
from funestra.playback import Playback
from funestra.robot_hand import FULL_INTENSITY


class FakeTCode:
    def __init__(self) -> None:
        self.updates: list[tuple[int, Funscript, float]] = []
        self.max_intensities: list[int] = []
        self.parks = 0
        self.resets = 0
        self.wanted: list[bool] = []
        self.closed = False

    def want(self, wanted: bool) -> None:
        self.wanted.append(wanted)

    def update(self, position_ms: int, fs: Funscript, *, speed: float = 1.0,
               max_intensity: int = FULL_INTENSITY) -> None:
        self.updates.append((position_ms, fs, speed))
        self.max_intensities.append(max_intensity)

    def park(self) -> None:
        self.parks += 1

    def reset(self) -> None:
        self.resets += 1

    def close(self) -> None:
        self.closed = True


class RefusesSeeks:
    _refusals_left = 0
    refused = 0

    def refuse_seeks(self, count: int) -> None:
        self._refusals_left = count

    def refuse_if_asked(self) -> None:
        if self._refusals_left > 0:
            self._refusals_left -= 1
            self.refused += 1
            raise SystemError("Error running mpv command", -12)


class FakeStation:
    def __init__(self, clips) -> None:
        self.clips = list(clips)
        self.heard_at: int | None = None
        self.paused = False
        self.closed = False

    def tune(self, level: int | None) -> None:
        self.heard_at = level

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def close(self) -> None:
        self.closed = True


class FakeEngine(RefusesSeeks):
    def __init__(self, duration_ms: float = 5_000.0) -> None:
        self.opened: list[Path] = []
        self.playlist: list[Path] = []
        self.playlist_pos = 0
        self.duration_ms = duration_ms
        self.position_ms = 0.0
        self.frame_rate = 25.0
        self.paused = False
        self.loop_file = False
        self.closed = False
        self.overlays: dict[int, tuple[int, int, object]] = {}
        self.volume = 100
        self.muted = True
        self.seeks: list[float] = []
        self.speed = 1.0
        self.pace_s: float | None = None
        self.showing_picture = False
        self.showing_video = True
        self.stations: list[FakeStation] = []
        self.picture_time: tuple[float, float] | None = None
        self.picture_seeks: list[float] = []
        self.held_for: float | None = None
        self.source_dims = (0, 0)
        self.ab_loop: tuple[float, float] | None = None
        self.pushes = 0
        self.tiled_to: list[tuple[int, int]] = []
        self.swapped: list[Path] = []
        self.screenshot = None
        self.screenshots = 0
        self.idle = False
        self.stopped = False
        self.settled = 0
        self.points_told: list[tuple] = []

    def tile_to_fill(self, window_width: int, window_height: int) -> None:
        self.tiled_to.append((window_width, window_height))

    def set_points_of_interest(self, points: tuple) -> None:
        self.points_told.append(points)

    def load(self, path: Path) -> None:
        self.opened.append(path)
        self.playlist = [path]
        self.playlist_pos = 0
        self.idle = False
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True
        self.idle = True
        self.position_ms = 0.0

    def swap_still(self, path: Path) -> None:
        self.swapped.append(path)
        self.playlist[self.playlist_pos] = path

    def stage_next(self, path: Path) -> None:
        del self.playlist[self.playlist_pos + 1:]
        self.playlist.append(path)

    def clear_next(self) -> None:
        del self.playlist[self.playlist_pos + 1:]

    @property
    def advanced_to_next(self) -> bool:
        return self.playlist_pos >= 1

    def settle_on_the_next(self) -> None:
        self.settled += 1
        while self.playlist_pos > 0:
            self.playlist.pop(0)
            self.playlist_pos -= 1

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def set_loop_file(self, loop: bool) -> None:
        self.loop_file = loop

    def set_pace(self, seconds: float) -> None:
        self.pace_s = seconds

    def push_still(self) -> None:
        self.pushes += 1

    def seek_picture(self, ms: float) -> None:
        self.picture_seeks.append(ms)

    def hold_picture_for(self, seconds: float | None) -> None:
        self.held_for = seconds

    def radio_station(self, clips) -> FakeStation:
        self.stations.append(FakeStation(clips))
        return self.stations[-1]

    def seek_ms(self, ms: float) -> None:
        self.refuse_if_asked()
        self.seeks.append(ms)
        self.position_ms = max(0.0, min(self.duration_ms, ms))

    def set_ab_loop(self, in_ms: float, out_ms: float) -> None:
        self.ab_loop = (in_ms, out_ms)

    def clear_ab_loop(self) -> None:
        self.ab_loop = None

    def set_volume(self, volume: int) -> None:
        self.volume = volume

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def set_speed(self, speed: float) -> None:
        self.speed = speed

    def close(self) -> None:
        self.closed = True

    def screenshot_bgra(self):
        self.screenshots += 1
        return self.screenshot

    def overlay(self, ident: int, x: int, y: int, bgra) -> None:
        self.overlays[ident] = (x, y, bgra)

    def remove_overlay(self, ident: int) -> None:
        self.overlays.pop(ident, None)

    def simulate_eof_advance(self) -> None:
        if len(self.playlist) > self.playlist_pos + 1:
            self.playlist_pos += 1

    @property
    def staged_next(self) -> Path | None:
        tail = self.playlist[self.playlist_pos + 1:]
        return tail[0] if tail else None


def make_playback(tmp_path, *, entries=1, start_paused=False, duration_ms=5_000.0, locked=False,
                  play_points=None, funscripts=None, points_of_interest=None, tcode=None):
    playlist = []
    for i in range(entries):
        vid = tmp_path / f"v{i}.mp4"
        vid.write_text("fake")
        playlist.append(vid)
    engine = FakeEngine(duration_ms=duration_ms)
    return Playback(
        playlist, engine=engine, start_paused=start_paused, locked=locked, play_points=play_points,
        funscripts={playlist[index]: script for index, script in (funscripts or {}).items()},
        points_of_interest={playlist[index]: points
                            for index, points in (points_of_interest or {}).items()},
        tcode=tcode,
    ), engine
