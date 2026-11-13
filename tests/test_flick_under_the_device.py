from __future__ import annotations

import pytest
from app_support.osr2_hold import HOLD_DELAY_S, HOLD_MOVE_MS, PARK
from genau_fakes import FakeTCodeSender

from funestra.flag import Flag
from funestra.flick_under_the_device import FlickUnderTheDevice
from funestra.genau_controls import GenauControls
from funestra.hands_device import HandsDevice
from funestra.main_hud import OSR2_PARKED
from funestra.robot_hand import RobotHandState, Waveform
from funestra.robot_hand_beat import BeatEngine
from funestra.tcode import HANDOFF_MS

FRAMES = 1000


def _under(*, playing: bool = True, position: int = 5000, wired: bool = True):
    hand = RobotHandState(playing=playing, bpm=120.0)
    controls = GenauControls(engine=BeatEngine(), paused=Flag(), step_flick=lambda _step: None,
                             robot_hand=hand)
    sender = FakeTCodeSender()
    sender._position = position
    device = HandsDevice(hand, controls.tcode_enabled, sender if wired else None)
    return FlickUnderTheDevice(controls, device), controls, sender


def _height_shown(phase: float) -> float:
    return 2 * phase if phase <= 0.5 else 2 * (1 - phase)


class TestThePointOfTheLoopOnScreen:
    def test_it_is_where_the_device_is_on_its_way_up(self):
        under, _controls, _sender = _under(position=5000)

        assert under.phase(FRAMES, 5.0, with_no_device=0.9) == pytest.approx(0.25, abs=0.001)

    def test_a_turn_at_the_top_puts_the_other_half_of_the_loop_on_the_way_down(self):
        under, _controls, sender = _under(position=5000)
        under.phase(FRAMES, 5.0, with_no_device=0.0)
        sender._position = 9999
        under.phase(FRAMES, 5.1, with_no_device=0.0)
        sender._position = 5000

        assert under.phase(FRAMES, 5.2, with_no_device=0.0) == pytest.approx(0.75, abs=0.001)
        assert under.on_the_way_down

    def test_with_no_osr2_wired_it_is_the_point_the_beat_is_at(self):
        under, _controls, _sender = _under(wired=False)

        assert under.phase(FRAMES, 5.0, with_no_device=0.9) == 0.9


class TestTheRoomHoldingTheDevice:
    ASKED = 5.1
    SETTLED = ASKED + HOLD_DELAY_S + HOLD_MOVE_MS[PARK] / 1000

    def _shown(self, under, now: float) -> float:
        under.follow_the_room_hold(now)
        return _height_shown(under.phase(FRAMES, now, with_no_device=0.0))

    def test_a_park_walks_the_frame_home_after_the_broker_s_wait(self):
        under, controls, _sender = _under(position=5000)
        self._shown(under, 5.0)
        controls.robot_hand.playing = False
        controls.app_hold.held = OSR2_PARKED

        shown = [self._shown(under, self.ASKED), self._shown(under, self.SETTLED)]

        assert shown == pytest.approx([0.5, 0.0], abs=0.005)

    def test_a_hand_that_plays_and_is_heard_ends_the_hold(self):
        under, controls, _sender = _under(position=5000)
        controls.app_hold.held = OSR2_PARKED

        under.follow_the_room_hold(5.0)

        assert controls.app_hold.held is None

    def test_the_frame_eases_back_onto_the_hand_when_it_takes_the_device_back(self):
        under, controls, _sender = _under(position=5000)
        self._shown(under, 5.0)
        controls.robot_hand.playing = False
        controls.app_hold.held = OSR2_PARKED
        self._shown(under, self.ASKED)
        self._shown(under, self.SETTLED)
        controls.robot_hand.playing = True
        back = self.SETTLED + 0.1

        shown = [self._shown(under, back), self._shown(under, back + HANDOFF_MS / 2000),
                 self._shown(under, back + HANDOFF_MS / 1000)]

        assert shown == pytest.approx([0.0, 0.25, 0.5], abs=0.005)

    def test_the_frame_stands_still_under_a_paused_hand_nobody_holds(self):
        under, controls, _sender = _under(playing=False)
        under.follow_the_room_hold(5.0)
        assert under.stands_still

        controls.app_hold.held = OSR2_PARKED
        under.follow_the_room_hold(5.1)

        assert not under.stands_still


class TestStandingTheFlickAtAPointOfItsLoop:
    @staticmethod
    def _device_height(controls, sender) -> float:
        return Waveform.of(controls.robot_hand).height_at(sender.motion_phase)

    def test_the_front_half_is_the_device_on_its_way_up(self):
        under, controls, sender = _under()

        under.stand_at(0.25)

        assert not under.on_the_way_down
        assert self._device_height(controls, sender) == pytest.approx(0.5, abs=0.01)

    def test_the_back_half_is_the_same_heights_on_the_way_down(self):
        under, controls, sender = _under()

        under.stand_at(0.75)

        assert under.on_the_way_down
        assert self._device_height(controls, sender) == pytest.approx(0.5, abs=0.01)
