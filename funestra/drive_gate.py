from __future__ import annotations

from dataclasses import replace

from .descent_latch import DescentLatch
from .drive_trace import Playhead, osr2_visualizer
from .osr2_visualizer import DriveHud
from .robot_hand import FULL_INTENSITY
from .trace_grid import on_the_grid

_REWIND_MS = -250
_JUMP_AHEAD_MS = 400

_STALLED_FRAMES = 25

_UNSAID = object()


def next_handoff_touch(script, position_ms: int, latch: DescentLatch) -> int | None:
    if script is None:
        return None
    position_ms = on_the_grid(position_ms)
    if script.is_resting_at(position_ms):
        _, boundary = script.turn_bounds_at(position_ms)
    else:
        boundary, _ = script.turn_bounds_at(position_ms)
    if boundary is None:
        return None
    choice = latch.choice_for(boundary)
    if choice is None:
        return None
    return choice.touch


class DriveGate:
    def __init__(self, session) -> None:
        self._session = session
        self._latch = DescentLatch()
        self._video = None
        self._seen_live = False
        self._position = 0
        self._stalled = 0

    def visualizer(self, published: DriveHud | None, *,
                device_drives_itself: bool = False, video_shows: bool = True) -> DriveHud:
        if device_drives_itself:
            self._latch.void_all()
            self._video = self._session.current_video
            self._seen_live = False
            self._position = int(self._session.position_ms)
            self._stalled = 0
            return published or DriveHud()
        drive = published
        position = int(self._session.position_ms)
        if drive is None:
            self._latch.void_all()
        if drive is not None:
            if self._video != self._session.current_video:
                self._video = self._session.current_video
                self._seen_live = False
                self._latch.void_all()
            moved = position - self._position
            if moved < _REWIND_MS or moved > _JUMP_AHEAD_MS:
                self._latch.void_all()
                self._stalled = 0
            elif moved == 0:
                self._stalled += 1
            else:
                if self._stalled > _STALLED_FRAMES:
                    self._latch.void_all()
                self._stalled = 0
            if drive.let_go is None:
                self._seen_live = True
            elif not self._seen_live:
                drive = replace(drive, let_go=None)
        self._position = position
        if not video_shows:
            self._latch.void_all()
            return drive or DriveHud()
        return osr2_visualizer(
            drive,
            Playhead(position, self._session.speed,
                     getattr(self._session, "max_intensity", FULL_INTENSITY)),
            script=self._script_as_played(),
            latch=self._latch,
        )

    def handoff_touch(self) -> int | None:
        return next_handoff_touch(
            self._script_as_played(), int(self._session.position_ms), self._latch)

    def _script_as_played(self):
        script = getattr(self._session, "funscript_as_played", _UNSAID)
        return self._session.current_funscript if script is _UNSAID else script
