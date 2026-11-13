from __future__ import annotations

from .device_walk import Walk, the_broker_holding, the_hand_taking_back
from .flick_flip import HALF_A_LOOP
from .flick_scrub import FlickScrub, scrub_flick
from .genau_controls import GenauControls
from .hands_device import HandsDevice
from .main_hud import HELD_HEIGHT, HOLD_VERB
from .robot_hand import Waveform, phase_for_position_fraction


class FlickUnderTheDevice:
    def __init__(self, controls: GenauControls, device: HandsDevice) -> None:
        self._hand = controls.robot_hand
        self._heard = controls.tcode_enabled
        self._room = controls.app_hold
        self._device = device
        self._scrub = FlickScrub()
        self._walk: Walk | None = None
        self._held: str | None = None
        self._following = self._hand.playing

    def follow_the_room_hold(self, now: float) -> None:
        if self._hand.playing and self._heard.on:
            self._room.held = None
        held = self._room.held
        if held is not None and held != self._held:
            self._walk = the_broker_holding(self._scrub.height, now, HOLD_VERB[held])
        following = held is None and self._hand.playing
        if following and not self._following:
            self._walk = the_hand_taking_back(self._scrub.height, now)
        self._held, self._following = held, following

    @property
    def stands_still(self) -> bool:
        return not self._hand.playing and self._held is None

    @property
    def on_the_way_down(self) -> bool:
        return self._scrub.back_half

    def phase(self, frame_count: int, now: float, *, with_no_device: float) -> float:
        live = self._device.height
        if live is None:
            return with_no_device
        return scrub_flick(self._scrub, self._height(live, now), frame_count)

    def _height(self, live: float, now: float) -> float:
        if self._walk is None:
            return live
        return self._walk.height_at(now, live if self._held is None else HELD_HEIGHT[self._held])

    def stand_at(self, phase: float) -> None:
        back_half = phase > HALF_A_LOOP
        height = 2 * (1 - phase) if back_half else 2 * phase
        self._scrub.back_half = back_half
        self._scrub.started = False
        swing = Waveform.of(self._hand)
        self._device.stand_at(phase_for_position_fraction(
            height, shape=swing.shape, amplitude=swing.amplitude, center=swing.center,
            rising=not back_half))
