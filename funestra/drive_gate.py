"""What of Genau's publish this video's trace is allowed to believe.

:mod:`funestra.drive_trace` draws one line out of two drivers, and two of
the things it needs cannot be read off a single publish:

*The descent forecasts.*  A descent's top is SELECTED once per approaching turn
and then held, because re-read live every frame it breathed with the beat
between Genau's publish cadence and the frame clock, and the seam flickered.
Holding one means knowing when it is void — and it is void whenever the wave it
was cut from stopped describing this approach: a stint with nothing published,
a different video, a seek, or a pause long enough for the media clock
and the wall clock to part company.

*Who has the device.*  ``DriveHud.let_go`` is Genau's own latch of the height it
handed over at, and it describes the last handoff GENAU made — which, across a
video change while it sits paused, is a handoff from some other video's motion.
A descent drawn from that height tops a ramp the device never made here.  So it
is honored only once Genau has been seen live (``let_go`` unset) within the
current video; until then the descent tops off the parked publish instead, which
is where the device really is.

One gate for every Funestra that hangs the console over a video — the Main Funestra's window on
the desktop, FunTimeVR's HUD in the headset — so the two hold their forecasts
by the same rules and publish the same touch for the arbiter.  It lived as a
closure and two dicts inside the Main Funestra's run loop, where none of these rules could be
exercised: widening the seek window a hundredfold, so a rewind no longer voided
the held forecasts, left the whole suite green.
"""
from __future__ import annotations

from dataclasses import replace

from .descent_latch import DescentLatch
from .drive_readout import DriveHud
from .drive_trace import drive_readout
from .robot_hand import FULL_INTENSITY
from .trace_grid import on_the_grid

# What counts as a seek rather than a frame's worth of playing.  Real frames
# advance tens of milliseconds (and the trace's 40ms quantum makes some read as
# zero); anything outside this is a jump.  Asymmetric because a rewind is a
# rewind at once, while forward motion has to allow for a slow frame.
#
# Any seek voids every held choice: the carry rules are written for one
# continuous approach, and a rewind approaches the SAME boundary again with a
# realigned wave — the old choice's touch cuts the new wave anywhere, and the
# blue overruns its own drawn ending by a whole cycle.
_REWIND_MS = -250
_JUMP_AHEAD_MS = 400

# How many frames of a standing playhead make a real pause rather than the
# quantum reading as zero.  When one ends, the media clock has stood still while
# Genau's wave kept moving in wall time, so every media-anchored forecast slid
# off the wave it was cut from.
_STALLED_FRAMES = 25

_UNSAID = object()


def next_handoff_touch(script, position_ms: int, latch: DescentLatch) -> int | None:
    """The touch-down the trace has chosen for the boundary ahead (or the one
    just crossed), in media ms — None when there is none (a raised floor, no
    script, nothing latched yet).

    Published so the arbiter can END Genau's turn exactly where the trace
    drew the blue ending.  Two readers of the same wave can pick different
    troughs, and then the device stops a touch short of the line still drawn on
    screen.  One chooser, the trace; the arbiter follows it.
    """
    if script is None:
        return None
    # On the trace's grid, as the trace read it: the raw playhead crosses a
    # boundary up to a quantum before the snapped one does, and asked there
    # it named a turn the trace had not chosen for yet.
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
    """The forecasts this trace is holding, and the rules that void them.

    *session* is the Funestra drawing the trace, read for where it is
    (``position_ms``), in what (``current_video``), with which script as it
    will play it (``funscript_as_played``), how fast (``speed``) and how hard
    the OSR2 may work (``max_intensity``).
    """

    def __init__(self, session) -> None:
        self._session = session
        # One choice per approaching turn.  Written by drive_readout as it
        # paints, read by the status file, voided here.
        self._latch = DescentLatch()
        self._video = None
        self._seen_live = False
        self._position = 0
        self._stalled = 0

    def readout(self, published: DriveHud | None, *,
                device_drives_itself: bool = False, video_shows: bool = True) -> DriveHud:
        """The readout to draw, with this video's funscript folded into it.

        *published* is Genau's readout as it last said it, or None while it has
        not published one yet.

        *device_drives_itself* is the OSR2 in auto mode, where the script's
        T-Code is dropped at the broker and Genau is not sending either: the
        handoff this gate draws is not happening, so the publish is handed back
        whole and every forecast is void.  A script folded in there would draw a
        plan for a device nothing here has.
        """
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
            # A stint with nothing published: the wave keeps moving while
            # nothing here watches it, so every held forecast is void by the
            # time it could be read again.
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
        return drive_readout(
            drive,
            script=self._script_as_played(),
            position_ms=position,
            speed=self._session.speed,
            latch=self._latch,
            max_intensity=getattr(self._session, "max_intensity", FULL_INTENSITY),
        )

    def handoff_touch(self) -> int | None:
        """The touch-down the trace has chosen for the boundary in play.

        Published with every status so the arbiter ends Genau's turn where the
        trace drew it ending; see :func:`next_handoff_touch` for why there is
        one chooser rather than two.
        """
        return next_handoff_touch(
            self._script_as_played(), int(self._session.position_ms), self._latch)

    def _script_as_played(self):
        # A Funestra on a branch opened before it said this runs on the same install.
        script = getattr(self._session, "funscript_as_played", _UNSAID)
        return self._session.current_funscript if script is _UNSAID else script
