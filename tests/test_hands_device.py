from __future__ import annotations

import pytest
from genau_fakes import FakeTCodeSender

from funestra.flag import Flag
from funestra.hands_device import HandsDevice
from funestra.robot_hand import RobotHandState


def _device(*, playing: bool = True, heard: bool = True, **bars):
    hand, sender = RobotHandState(playing=playing, **bars), FakeTCodeSender()
    return HandsDevice(hand, Flag(on=heard), sender), hand, sender


class TestDrivingTheOsr2:
    def test_a_hand_that_plays_and_is_heard_wants_the_osr2_and_sends_it_the_phase(self):
        device, _hand, sender = _device()

        device.drive(0.25, 7.0, the_hand_has_it=True)

        assert (sender.wanted, sender.sends) == (True, [(0.25, 7.0)])

    def test_a_hand_switched_off_plays_on_unheard(self):
        device, _hand, sender = _device(heard=False)

        device.drive(0.25, 7.0, the_hand_has_it=True)

        assert (sender.wanted, sender.sends, sender.motion_phase) == (False, [], 0.25)

    def test_a_paused_hand_lets_the_osr2_go_and_sends_nothing(self):
        device, _hand, sender = _device(playing=False)

        device.drive(0.25, 7.0, the_hand_has_it=True)

        assert (sender.wanted, sender.sends) == (False, [])

    def test_while_the_osr2_runs_itself_the_hand_stays_off_it(self):
        device, _hand, sender = _device()

        device.drive(0.25, 7.0, the_hand_has_it=False)

        assert (sender.wanted, sender.sends) == (False, [])

    def test_a_hand_that_stops_hands_the_device_over_once(self):
        device, hand, sender = _device()
        hand.playing = False

        device.drive(0.25, 7.0, the_hand_has_it=True)
        device.drive(0.25, 7.1, the_hand_has_it=True)

        assert sender.hand_overs == 1

    def test_a_hand_that_starts_takes_the_device_over(self):
        device, hand, sender = _device(playing=False)
        hand.playing = True

        device.drive(0.25, 7.0, the_hand_has_it=True)

        assert sender.take_overs == 1

    def test_with_no_osr2_wired_driving_is_nothing(self):
        HandsDevice(RobotHandState(playing=True), Flag(on=True)).drive(
            0.25, 7.0, the_hand_has_it=True)


class TestWhereTheDeviceIs:
    def test_its_height_is_the_share_of_the_whole_stroke_it_stands_at(self):
        device, _hand, sender = _device()
        sender._position = 2500

        assert device.height == pytest.approx(0.25, abs=0.001)

    def test_with_no_osr2_wired_it_has_no_height(self):
        assert HandsDevice(RobotHandState(), Flag(on=True)).height is None

    def test_where_in_its_travel_is_measured_between_the_ends_the_bars_allow(self):
        device, _hand, sender = _device(amplitude=50, intended_center=50)
        sender._position = 5000

        assert device.where_in_its_travel == pytest.approx(0.5, abs=0.001)

    def test_with_no_travel_in_the_bars_it_is_at_the_floor_of_it(self):
        device, _hand, _sender = _device(amplitude=0)

        assert device.where_in_its_travel == 0.0

    def test_with_no_osr2_wired_it_is_at_the_floor_of_its_travel(self):
        assert HandsDevice(RobotHandState(), Flag(on=True)).where_in_its_travel == 0.0

    def test_standing_it_at_a_phase_tells_the_sender_where_the_motion_is(self):
        device, _hand, sender = _device()

        device.stand_at(0.4)

        assert sender.motion_phase == 0.4

    def test_with_no_osr2_wired_standing_it_somewhere_is_nothing(self):
        HandsDevice(RobotHandState(), Flag(on=True)).stand_at(0.4)


class TestSentBetweenPasses:
    @staticmethod
    def _device(*, playing: bool = True, heard: bool = True):
        hand, sender = RobotHandState(playing=playing), FakeTCodeSender()
        return HandsDevice(hand, Flag(on=heard), sender, sent_between_passes=True), hand, sender

    def test_a_pass_of_the_window_follows_the_phase_and_sends_nothing(self):
        device, _hand, sender = self._device()

        for step in range(3):
            device.drive(0.25 + 0.01 * step, 7.0 + 0.016 * step, the_hand_has_it=True)

        assert (sender.wanted, sender.sends, sender.motion_phase) == (True, [], 0.27)

    def test_the_send_between_passes_follows_the_phase_and_sends_it(self):
        device, _hand, sender = self._device()

        device.send(0.3, 7.01)

        assert sender.sends == [(0.3, 7.01)]

    def test_a_hand_switched_off_is_followed_unheard(self):
        device, _hand, sender = self._device(heard=False)

        device.send(0.3, 7.01)

        assert (sender.sends, sender.motion_phase) == ([], 0.3)

    def test_a_hand_paused_since_the_last_pass_is_sent_nothing(self):
        device, hand, sender = self._device()
        hand.playing = False

        device.send(0.3, 7.01)

        assert (sender.sends, sender.motion_phase) == ([], 0.0)

    def test_with_no_osr2_wired_the_send_is_nothing(self):
        HandsDevice(RobotHandState(playing=True), Flag(on=True),
                    sent_between_passes=True).send(0.3, 7.01)
