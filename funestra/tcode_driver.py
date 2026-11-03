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

_RESEND_INTERVAL = 0.1
_PARK_INTERVAL_MS = PARK_SETTLE_MS
_PARK_SEGMENT = -2


class FunscriptTCodeDriver:
    def __init__(self, sink: TCodeSink) -> None:
        self._sink = sink
        self._last_send_time: float = -1.0
        self._last_segment: int = -1
        self._glide = HandoffGlide()
        self._glide.begin()
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
            self.park(now=now)
            return

        next_index = bisect.bisect_right(fs._times, position_ms)
        if self._should_send(next_index, now):
            self._send_waypoint(fs, next_index, position_ms, speed, max_intensity, now)
            self._mark_sent(next_index, now)
            self._took_over = False

    def park(self, *, now: float | None = None) -> None:
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
        if next_index < len(fs.actions):
            next_t = fs.actions[next_index][0]
            remaining = max(1, round((next_t - position_ms) / speed))
        else:
            next_t, remaining = fs.actions[-1][0], 100
        self._send(
            to_tcode_position(fs.paced_position_at(next_t, speed, max_intensity=max_intensity)),
            remaining, now)

    def _send(self, position: int, interval_ms: int, now: float) -> None:
        self._sink.send(format_tcode_command(
            "L0", position, self._glide.interval_ms(interval_ms, now)))

    def reset(self) -> None:
        self._last_segment = -1
        self._last_send_time = -1.0
        self._took_over = True
        self._glide.begin()

    def want(self, wanted: bool) -> None:
        self._sink.want(wanted)

    def close(self) -> None:
        self._sink.close()
