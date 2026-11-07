from __future__ import annotations

from typing import TYPE_CHECKING

from . import learned_motion
from .flick_flip import HALF_A_LOOP
from .funscript import HANDOFF_RAMP_MS
from .robot_hand import (
    ON_THE_PARK_WITHIN,
    POSITION_MAX,
    phase_to_position,
)
from .tcode import HandoffGlide, TCodeSink, format_tcode_command

if TYPE_CHECKING:
    from .robot_hand import RobotHandState

_RISE_SKIP_BELOW = round(ON_THE_PARK_WITHIN * POSITION_MAX)


class RobotHandTCodeDriver:
    def __init__(
        self,
        sink: TCodeSink,
        *,
        robot_hand: RobotHandState | None = None,
        learned=None,
        min_interval: float = 1.0 / 30.0,
    ) -> None:
        self._sink = sink
        self._robot_hand = robot_hand
        self._learned = learned
        self._min_interval = min_interval
        self._last_send_time: float = 0.0
        self._last_phase: float = 0.0
        self._motion_phase: float = 0.0
        self._glide = HandoffGlide()
        self._glide.begin()
        self._rise = 1.0
        self._rise_started: float | None = None
        self._let_go_position: int | None = None
        self._output_was_off = False

    def take_over(self) -> None:
        self.rest_at_floor()
        if self._compute_position() > _RISE_SKIP_BELOW:
            self._rise = 0.0
            self._rise_started = None
        else:
            self._rise = 1.0
            self._let_go_position = None
        self._glide.begin()

    def hand_over(self) -> None:
        self._let_go_position = self.current_position()
        self.rest_at_floor()

    def rest_at_floor(self) -> None:
        self._motion_phase = 0.0
        if self._learned is not None:
            learned_motion.rest_at_floor(self._learned)

    def set_motion_phase(self, phase: float) -> None:
        self._motion_phase = phase

    def _compute_position(self) -> int:
        if self._learned is not None and self._learned.active:
            return round(POSITION_MAX * learned_motion.position(
                self._learned, self._robot_hand) / 100)
        if self._robot_hand is not None:
            return phase_to_position(
                self._motion_phase,
                shape=self._robot_hand.shape,
                amplitude=self._robot_hand.amplitude,
                center=self._robot_hand.center,
            )
        return phase_to_position(self._motion_phase)

    def current_position(self) -> int:
        return round(self._compute_position() * self._rise)

    @property
    def motion_phase(self) -> float:
        return self._motion_phase

    @property
    def let_go_position(self) -> int | None:
        return self._let_go_position

    def maybe_send(self, phase: float, now: float, *, output: bool = True) -> None:
        if self._rise < 1.0:
            if self._rise_started is None:
                self._rise_started = now
            self._rise = min(1.0, (now - self._rise_started) / (HANDOFF_RAMP_MS / 1000))
            if self._rise >= 1.0:
                self._let_go_position = None
            self._last_phase = phase
        else:
            delta = phase - self._last_phase
            if delta < -HALF_A_LOOP:
                delta += 1.0
            self._motion_phase += max(0.0, delta)
            self._last_phase = phase

        if not output:
            self._output_was_off = True
            return
        if self._output_was_off:
            self._output_was_off = False
            self._glide.begin()
        elapsed = now - self._last_send_time
        if elapsed < self._min_interval:
            return
        interval_ms = max(1, min(9999, round(elapsed * 1000)))
        position = round(self._compute_position() * self._rise)
        self._sink.send(format_tcode_command(
            "L0", position, self._glide.interval_ms(interval_ms, now)))
        self._last_send_time = now

    def want(self, wanted: bool) -> None:
        self._sink.want(wanted)

    def close(self) -> None:
        self._sink.close()


class DeviceHandoff:
    def __init__(self, *, playing: bool, tcode_sender=None):
        self.tcode_sender = tcode_sender
        self._playing = playing

    def watch(self, playing: bool) -> None:
        was, self._playing = self._playing, playing
        if playing == was:
            return
        if self.tcode_sender is not None:
            if playing:
                self.tcode_sender.take_over()
            else:
                self.tcode_sender.hand_over()
