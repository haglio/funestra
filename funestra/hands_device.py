from __future__ import annotations

from .flag import Flag
from .robot_hand import POSITION_MAX, RobotHandState
from .robot_hand_driver import DeviceHandoff


class HandsDevice:
    def __init__(self, hand: RobotHandState, heard: Flag, tcode_sender=None) -> None:
        self._hand = hand
        self._heard = heard
        self._sender = tcode_sender
        self._handoff = DeviceHandoff(playing=hand.playing, tcode_sender=tcode_sender)

    def drive(self, phase: float, now: float, *, the_hand_has_it: bool) -> None:
        self._handoff.watch(self._hand.playing)
        if self._sender is None:
            return
        moving = the_hand_has_it and self._hand.playing
        self._sender.want(moving and self._heard.on)
        if moving:
            self._sender.maybe_send(phase, now, output=self._heard.on)

    @property
    def height(self) -> float | None:
        return None if self._sender is None else self._sender.current_position() / POSITION_MAX

    @property
    def where_in_its_travel(self) -> float:
        hand = self._hand
        if self._sender is None or hand.amplitude <= 0:
            return 0.0
        low = max(0.0, hand.center - hand.amplitude / 2)
        span = min(100.0, hand.center + hand.amplitude / 2) - low
        return (100.0 * self.height - low) / span if span > 0 else 0.0

    def stand_at(self, phase: float) -> None:
        if self._sender is not None:
            self._sender.set_motion_phase(phase)
