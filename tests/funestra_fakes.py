from __future__ import annotations

import os

from funestra.broker_feed import BrokerFeed
from funestra.funscript import Funscript
from funestra.playback import Playback
from funestra.playback_setup import PlaybackSetup
from funestra.robot_hand import FULL_INTENSITY
from funestra.testing import FakeEngine


def holds_of_the_lock(feed: BrokerFeed) -> list[str]:
    held: list[str] = []
    original = feed.lock

    class _Recording:
        def __enter__(self):
            held.append("taken")
            return original.__enter__()

        def __exit__(self, *exc):
            held.append("given back")
            return original.__exit__(*exc)

    feed.lock = _Recording()
    return held


class FakeTCode:
    def __init__(self) -> None:
        self.updates: list[tuple[int, Funscript, float]] = []
        self.max_intensities: list[int] = []
        self.parks = 0
        self.resets = 0
        self.new_scripts = 0
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

    def new_script(self) -> None:
        self.new_scripts += 1

    def close(self) -> None:
        self.closed = True


def make_playback(tmp_path, *, entries=1, duration_ms=5_000.0, funscripts=None,
                  points_of_interest=None, **playback):
    playlist = []
    for i in range(entries):
        vid = tmp_path / f"v{i}.mp4"
        vid.write_text("fake")
        playlist.append(vid)
    engine = FakeEngine(duration_ms=duration_ms)
    return Playback(
        playlist, engine=engine,
        setup=PlaybackSetup(
            funscripts={playlist[index]: script for index, script in (funscripts or {}).items()},
            points_of_interest={playlist[index]: points
                                for index, points in (points_of_interest or {}).items()},
            **playback),
    ), engine


class WorkerTheTestRuns:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.asked: list[str] = []
        self.jobs: list[tuple] = []
        self.delivered = 0
        self.closed = False
        self.heard: list[str] = []
        self.followed: list[str] = []

    def publish(self, path, text: str) -> bool:
        self.published.append((path.name, text))
        return True

    def ask(self, _command_file, command: str) -> None:
        self.asked.append(command)

    def do(self, work, then=None) -> None:
        self.jobs.append((work, then))

    def deliver(self) -> None:
        self.delivered += 1

    def follow_commands(self, path, *, log=None):
        self.followed.append(path.name)
        return self._take

    def _take(self) -> list[str]:
        taken, self.heard = self.heard, []
        return taken

    def close(self) -> None:
        self.closed = True

    def run_the_jobs(self) -> None:
        jobs, self.jobs = self.jobs, []
        for work, then in jobs:
            done = work()
            if then is not None:
                then(done)


LONG_AGO_NS = 1_000_000_000 * 60 * 60 * 24 * 365 * 40


def stamped_long_ago(*files) -> None:
    for file in files:
        os.utime(file, ns=(LONG_AGO_NS, LONG_AGO_NS))
