from __future__ import annotations

from funestra.funscript import Funscript
from funestra.playback import Playback
from funestra.robot_hand import FULL_INTENSITY
from funestra.testing import FakeEngine


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
