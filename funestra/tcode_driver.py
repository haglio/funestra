from __future__ import annotations

import bisect
import time

from .funscript import HANDOFF_RAMP_MS, PARK_SETTLE_MS, Funscript
from .robot_hand import FULL_INTENSITY
from .tcode import (
    HandoffGlide,
    TCodeSink,
    format_tcode_command,
    to_tcode_position,
)

__all__ = [
    "FunscriptTCodeDriver",
]

_RESEND_INTERVAL = 0.1
# Glide to the parked position over this long, matching the broker's own park.
# The funscript's plan draws this same descent, which is why the number is its.
_PARK_INTERVAL_MS = PARK_SETTLE_MS
# Sentinel "segment" for the parked state, distinct from -1 ("nothing sent yet").
_PARK_SEGMENT = -2


class FunscriptTCodeDriver:
    def __init__(self, sink: TCodeSink) -> None:
        self._sink = sink
        self._last_send_time: float = -1.0
        self._last_segment: int = -1
        # The device is wherever the other driver left it when this one takes
        # over, so its first waypoints glide rather than snap.  Armed by
        # :meth:`reset`, which is what a takeover already calls, and armed here
        # too: the first waypoint of a session starts from the broker's park.
        self._glide = HandoffGlide()
        self._glide.begin()
        # The first PARK after a takeover is the handoff itself: the device is
        # wherever the other driver left it — most of the range away, not a
        # settle's width — and this driver owns walking it down.  Tracked here
        # (armed with the glide) and consumed by :meth:`park`.
        self._took_over = True
        self._park_started: float | None = None
        self._park_total_ms: int = _PARK_INTERVAL_MS

    def update(
        self, position_ms: int, fs: Funscript, *, now: float | None = None,
        speed: float = 1.0, max_intensity: int = FULL_INTENSITY,
    ) -> None:
        if now is None:
            now = time.monotonic()

        if fs.is_parked_at(position_ms):
            # The plan through every quiet stretch — the lead-in, interior gaps,
            # the tail past the last action — is the parked position: the
            # device's neutral is its rest, not wherever the last action left it
            # and not a drift toward one still seconds away.  The rise back out
            # is the waypoint below, which the plan arms a beat ahead of each
            # cluster so the device meets its opening action as it fires.
            self.park(now=now)
            return

        next_index = bisect.bisect_right(fs._times, position_ms)
        if self._should_send(next_index, now):
            self._send_waypoint(fs, next_index, position_ms, speed, max_intensity, now)
            self._mark_sent(next_index, now)
            self._took_over = False

    def park(self, *, now: float | None = None) -> None:
        """Walk the OSR2 down to its rest and hold it there.

        Drives the OSR2 when there is nothing to script from — an unscripted
        video, or a funscript's quiet lead-in.  Sent on entry, then refreshed on
        the resend interval against packet loss — but each refresh carries the
        REMAINING time of the descent, not a fresh full interval.  A re-sent
        full interval retargets the in-flight glide from wherever the device is,
        which bends every drawn straight ramp into a fast exponential: the
        device was effectively parked in a third of the time the picture showed.

        The first park after a takeover descends over the handoff ramp — the
        device is wherever the other driver left it, most of the range away, and
        this glide IS the grey ramp the trace draws.  Every later park is the
        plan's own settle.
        """
        if now is None:
            now = time.monotonic()
        if self._last_segment != _PARK_SEGMENT:
            self._park_started = now
            self._park_total_ms = HANDOFF_RAMP_MS if self._took_over else _PARK_INTERVAL_MS
            self._took_over = False
        if self._should_send(_PARK_SEGMENT, now):
            started = now if self._park_started is None else self._park_started
            elapsed_ms = round((now - started) * 1000)
            remaining = max(50, self._park_total_ms - elapsed_ms)
            self._sink.send(format_tcode_command("L0", 0, remaining))
            self._mark_sent(_PARK_SEGMENT, now)

    def _should_send(self, segment: int, now: float) -> bool:
        new_segment = segment != self._last_segment
        stale = (
            self._last_send_time >= 0
            and now - self._last_send_time >= _RESEND_INTERVAL
        )
        return new_segment or stale

    def _mark_sent(self, segment: int, now: float) -> None:
        self._last_segment = segment
        self._last_send_time = now

    def _send_waypoint(
        self, fs: Funscript, next_index: int, position_ms: int, speed: float, max_intensity: int,
        now: float,
    ) -> None:
        """Aim at ``fs.actions[next_index]``, the first action still ahead.

        Ahead of the whole script that is the opening action itself, so a
        playhead approaching the script's start glides to where the script
        begins rather than skipping to where its first motion ends.

        The gap is *media* time and the OSR2 moves in wall-clock, so at
        playback rate ``speed`` the move has that many wall-milliseconds to
        finish in -- and the height is the paced one, which is how that rate
        stays inside what the device can travel.
        """
        if next_index < len(fs.actions):
            next_t = fs.actions[next_index][0]
            remaining = max(1, round((next_t - position_ms) / speed))
        else:
            next_t, remaining = fs.actions[-1][0], 100
        self._send(
            to_tcode_position(fs.paced_position_at(next_t, speed, max_intensity=max_intensity)),
            remaining, now)

    def _send(self, position: int, interval_ms: int, now: float) -> None:
        """One waypoint, given the handoff's glide while one is running.

        The script's own timing runs a beat late for that stretch — the
        alternative is arriving on time by snapping there from wherever the Robot
        Hand's motion had the device, which is the jolt this exists to remove.
        """
        self._sink.send(format_tcode_command(
            "L0", position, self._glide.interval_ms(interval_ms, now)))

    def reset(self) -> None:
        """Forget what was sent, and glide onto whatever comes next.

        A reset is what a takeover, a seek and a new video all do, and each of
        them leaves the device somewhere this script did not put it.
        """
        self._last_segment = -1
        self._last_send_time = -1.0
        self._took_over = True
        self._glide.begin()

    def close(self) -> None:
        self._sink.close()
