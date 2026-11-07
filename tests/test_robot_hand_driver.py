from __future__ import annotations

import random

from import_checks import assert_imports_without

from funestra.funscript import HANDOFF_RAMP_MS
from funestra.learned_model import LearnedModel, Phrase, classify
from funestra.learned_motion import (
    LearnedMotionState,
    enable_learned_motion,
    tick_learned_motion,
)
from funestra.robot_hand import (
    RobotHandState,
    WaveformShape,
    bpm_for_speed,
)
from funestra.robot_hand_driver import DeviceHandoff, RobotHandTCodeDriver
from funestra.tcode import HANDOFF_MS


class FakeTCodeSink:
    def __init__(self):
        self.sent: list[str] = []
        self.wanted: list[bool] = []
        self.closed = False

    def send(self, command: str) -> None:
        self.sent.append(command)

    def want(self, wanted: bool) -> None:
        self.wanted.append(wanted)

    def close(self) -> None:
        self.closed = True


class TestRobotHandTCodeDriver:
    def test_first_call_always_sends(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.maybe_send(phase=0.0, now=1.0)
        assert len(sink.sent) == 1

    def test_second_call_within_interval_does_not_send(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.01, now=1.01)
        assert len(sink.sent) == 1

    def test_second_call_after_interval_sends(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.1, now=1.05)
        assert len(sink.sent) == 2

    def test_interval_reflects_elapsed_time(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.25, now=1.5)
        sender.maybe_send(phase=0.5, now=1.55)
        assert "I50" in sink.sent[2]


class TestTakingOver:
    def test_a_fresh_sender_eases_onto_the_device(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)

        sender.maybe_send(phase=0.0, now=0.05)

        assert f"I{HANDOFF_MS}" in sink.sent[0]

    def test_taking_the_device_back_eases_onto_it_again(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.maybe_send(phase=0.0, now=0.05)
        sender.maybe_send(phase=0.25, now=1.0)

        sender.take_over()
        sender.maybe_send(phase=0.5, now=1.05)

        assert f"I{HANDOFF_MS}" in sink.sent[2]

    def test_with_its_output_off_the_motion_runs_on_and_nothing_is_sent(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)

        sender.maybe_send(phase=0.0, now=1.0, output=False)
        sender.maybe_send(phase=0.25, now=1.05, output=False)

        assert (sender.motion_phase, sink.sent) == (0.25, [])

    def test_output_coming_back_eases_onto_the_motion(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.maybe_send(phase=0.0, now=0.05)
        sender.maybe_send(phase=0.25, now=1.0)
        sender.maybe_send(phase=0.4, now=1.02, output=False)

        sender.maybe_send(phase=0.5, now=1.05)

        assert f"I{HANDOFF_MS}" in sink.sent[2]

    def test_every_tick_of_the_glide_is_stretched_not_just_the_first(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)

        sender.take_over()
        sender.maybe_send(phase=0.0, now=0.05)
        sender.maybe_send(phase=0.1, now=0.10)
        sender.maybe_send(phase=0.2, now=0.15)

        assert all(f"I{HANDOFF_MS}" in command for command in sink.sent)

    def test_the_motion_is_its_own_again_once_the_glide_runs_out(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        glide = HANDOFF_MS / 1000

        sender.take_over()
        sender.maybe_send(phase=0.0, now=0.05)
        sender.maybe_send(phase=0.5, now=0.05 + glide + 0.01)
        sender.maybe_send(phase=0.6, now=0.05 + glide + 0.06)

        assert "I50" in sink.sent[2]

    def test_phase_wrap_accumulates_motion_phase(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)
        sender.maybe_send(phase=0.9, now=1.0)
        sender.maybe_send(phase=0.1, now=1.05)
        pos_str = sink.sent[1]
        assert pos_str.startswith("L0")
        pos_value = int(pos_str[2:6])
        assert 500 < pos_value < 2000

    def test_no_wrap_advances_motion_phase_normally(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.5, now=1.05)
        assert "L09999" in sink.sent[1]

    def test_close_delegates_to_sink(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.close()
        assert sink.closed is True


class TestRestingAtTheFloor:
    def test_taking_over_resumes_at_the_foot_of_the_swing(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)

        sender.take_over()
        sender.maybe_send(phase=0.5, now=1.05)

        assert sink.sent[1].startswith("L00000")

    def test_losing_the_device_rests_the_published_motion_too(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)
        assert sender.current_position() == 9999

        sender.rest_at_floor()

        assert sender.motion_phase == 0.0
        assert sender.current_position() == 0


class TestTheRiseOutOfThePark:
    def _sender(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=30, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)
        sink.sent.clear()
        return sink, sender

    def test_the_takeover_starts_at_the_park_not_the_floor(self):
        sink, sender = self._sender()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)

        assert sink.sent[0].startswith("L00000")

    def test_the_climb_is_gradual(self):
        sink, sender = self._sender()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.8, now=1.0 + HANDOFF_RAMP_MS / 2000)

        halfway = int(sink.sent[1][2:6])
        assert 1600 < halfway < 1900

    def test_the_swing_holds_until_the_climb_ends(self):
        sink, sender = self._sender()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.9, now=1.0 + HANDOFF_RAMP_MS / 1000)

        assert sender.motion_phase == 0.0
        arrived = int(sink.sent[1][2:6])
        assert 3400 < arrived < 3600

    def test_the_motion_is_its_own_again_after_the_climb(self):
        sink, sender = self._sender()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.9, now=1.0 + HANDOFF_RAMP_MS / 1000 + 0.1)
        sender.maybe_send(phase=0.15, now=1.0 + HANDOFF_RAMP_MS / 1000 + 0.2)

        assert sender.motion_phase > 0.0
        assert int(sink.sent[2][2:6]) > 3600

    def test_the_published_position_follows_the_climb(self):
        _sink, sender = self._sender()

        sender.take_over()
        assert sender.current_position() == 0

        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.8, now=1.0 + HANDOFF_RAMP_MS / 2000)

        assert 1600 < sender.current_position() < 1900

    def test_at_full_amplitude_there_is_no_hold_by_the_owners_confirmed_rule(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=100, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.0, now=0.5)
        sink.sent.clear()

        sender.take_over()
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.25, now=1.1)

        assert int(sink.sent[1][2:6]) > 3000


class TestLetGoThroughTheRoundTrip:
    def _sender(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=30, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)
        return sender

    def test_handing_over_latches_where_the_device_was(self):
        sender = self._sender()

        sender.hand_over()

        assert sender.let_go_position == 6499

    def test_handing_over_sends_nothing_since_the_driver_taking_the_device_walks_it_down(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(
            sink, robot_hand=RobotHandState(amplitude=30, center=50), min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)
        sent_while_driving = list(sink.sent)

        sender.hand_over()

        assert sink.sent == sent_while_driving

    def test_the_latch_survives_the_climb(self):
        sender = self._sender()
        sender.hand_over()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.8, now=1.0 + HANDOFF_RAMP_MS / 2000)

        assert sender.let_go_position is not None

    def test_the_latch_clears_when_the_wave_comes_live_which_is_the_edge_the_trace_re_anchors_its_descent_top_on(self):
        sender = self._sender()
        sender.hand_over()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.9, now=1.0 + HANDOFF_RAMP_MS / 1000)

        assert sender.let_go_position is None

    def test_a_skipped_climb_clears_it_at_once(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=100, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)
        sender.hand_over()

        sender.take_over()

        assert sender.let_go_position is None


    def test_a_takeover_with_nothing_to_climb_ends_a_climb_it_interrupted_or_every_position_after_would_be_shrunk(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=30, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)
        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.8, now=1.0 + HANDOFF_RAMP_MS / 4000)
        state.amplitude = 100

        sender.take_over()
        sender.maybe_send(phase=0.2, now=2.0)

        assert int(sink.sent[-1][2:6]) > 9000


class TestWhatTheHandoffMoves:
    def test_it_moves_the_senders_alone_since_the_broker_is_the_orchestrator_s_to_park_and_resume(self):
        assert_imports_without("funestra.robot_hand_driver", "funestra.broker")


class TestSenderWithDirectState:
    def test_reads_amplitude_from_state(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=50, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)
        pos_value = int(sink.sent[0][2:6])
        assert 7000 < pos_value < 8000

    def test_reads_shape_from_state(self):
        sink = FakeTCodeSink()
        state = RobotHandState(shape=WaveformShape.TRIANGLE)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.25, now=1.0)
        pos_value = int(sink.sent[0][2:6])
        assert 4900 < pos_value < 5100

    def test_current_position(self):
        sink = FakeTCodeSink()
        state = RobotHandState()
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)
        assert sender.current_position() == 9999




class FakeSender:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def take_over(self) -> None:
        self.calls.append("take_over")

    def hand_over(self) -> None:
        self.calls.append("hand_over")


class TestTheSender:
    def test_a_hand_that_starts_moving_arms_the_climb_out_of_the_park(self):
        sender = FakeSender()
        handoff = DeviceHandoff(playing=False, tcode_sender=sender)

        handoff.watch(True)

        assert sender.calls == ["take_over"]

    def test_a_hand_that_stops_walks_the_motion_down_and_rests_it(self):
        sender = FakeSender()
        handoff = DeviceHandoff(playing=True, tcode_sender=sender)

        handoff.watch(False)

        assert sender.calls == ["hand_over"]

    def test_it_is_the_edge_and_not_the_state_that_is_acted_on(self):
        sender = FakeSender()
        handoff = DeviceHandoff(playing=True, tcode_sender=sender)

        handoff.watch(False)
        handoff.watch(False)
        handoff.watch(False)

        assert sender.calls == ["hand_over"]

    def test_the_first_tick_reads_against_the_state_it_was_built_in(self):
        sender = FakeSender()

        DeviceHandoff(playing=True, tcode_sender=sender).watch(True)

        assert sender.calls == []

    def test_a_build_with_no_sender_still_follows_the_edge(self):
        handoff = DeviceHandoff(playing=False)

        handoff.watch(True)
        handoff.watch(False)


class TestLearnedMotionOnTheWire:
    def _learned(self, *, playing: bool = True):
        phrase = Phrase(tuple((500, 80 if i % 2 == 0 else 20) for i in range(16)))
        model = LearnedModel(phrases={classify(phrase): [phrase]}, seen={classify(phrase): 1},
                             native_cycle_ms=60_000 / bpm_for_speed(50))
        hand = RobotHandState(playing=playing, amplitude=100, intended_center=50)
        learned = LearnedMotionState(model=model, rng=random.Random(1))
        enable_learned_motion(learned)
        tick_learned_motion(hand, learned, now=10.0)
        for i in range(1, 6):
            tick_learned_motion(hand, learned, now=10.0 + i * 0.05)
        return hand, learned

    def test_the_device_is_sent_where_the_phrases_have_the_motion(self):
        hand, learned = self._learned()
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, robot_hand=hand, learned=learned, min_interval=0.033)

        sender.maybe_send(phase=0.6, now=11.0)

        assert sink.sent[-1].startswith("L04000")

    def test_losing_the_device_rests_the_phrases_at_the_floor(self):
        hand, learned = self._learned()
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, robot_hand=hand, learned=learned, min_interval=0.033)

        sender.hand_over()

        assert sender.let_go_position == 4000
        assert sender.current_position() == 0


def test_the_robot_hand_wants_the_osr2_through_its_slot():
    sink = FakeTCodeSink()
    sender = RobotHandTCodeDriver(sink)

    sender.want(True)
    sender.want(False)

    assert sink.wanted == [True, False]
