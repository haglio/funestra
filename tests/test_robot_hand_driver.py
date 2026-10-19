from __future__ import annotations

import random

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
        self.closed = False

    def send(self, command: str) -> None:
        self.sent.append(command)

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
        # Past the glide a fresh sender opens with, so this is an ordinary tick
        # rather than the ease onto a device somebody else was holding.
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.25, now=1.5)
        sender.maybe_send(phase=0.5, now=1.55)
        # Third command should have I50 (50ms elapsed)
        assert "I50" in sink.sent[2]


class TestTakingOver:
    """Genau does not hold the device the whole time — in kino mode a funscript has
    it for every scripted stretch — so it comes back to a device parked wherever
    that script left it, with its own phase run on without it."""

    def test_a_fresh_sender_eases_onto_the_device(self):
        """Whatever had it last — the broker's park, a funscript — it is not
        where this motion's phase says to be."""
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
        """A motion sends thirty times a second: one stretched command would be
        superseded a frame later by an ordinary one, and the device would cover
        whatever was left of the gap in that frame — the jolt, moved."""
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)

        sender.take_over()
        sender.maybe_send(phase=0.0, now=0.05)
        sender.maybe_send(phase=0.1, now=0.10)
        sender.maybe_send(phase=0.2, now=0.15)

        assert all(f"I{HANDOFF_MS}" in command for command in sink.sent)

    def test_the_motion_is_its_own_again_once_the_glide_runs_out(self):
        """A glide, not a slowed-down motion."""
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
        # Phase goes 0.9 → 0.1 (wrap). Motion phase should go 0.9 → 1.1
        sender.maybe_send(phase=0.9, now=1.0)
        sender.maybe_send(phase=0.1, now=1.05)
        # motion_phase ~1.1: past the base-at-1.0 point, heading back up.
        # Should NOT snap to the position for raw phase 0.1 (near base).
        # Position at 1.1 should be small but nonzero (~951).
        pos_str = sink.sent[1]
        assert pos_str.startswith("L0")
        pos_value = int(pos_str[2:6])
        assert 500 < pos_value < 2000

    def test_no_wrap_advances_motion_phase_normally(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.5, now=1.05)
        # motion_phase=0.5 → tip (9999) with 2π cosine
        assert "L09999" in sink.sent[1]

    def test_close_delegates_to_sink(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.033)
        sender.close()
        assert sink.closed is True


class TestRestingAtTheFloor:
    """The funscript's turn leaves the device at its park, so the motion resumes
    from the foot of its swing — phase 0, where every shape's raw value is 0 —
    instead of lunging to wherever the swing happened to freeze."""

    def test_taking_over_resumes_at_the_foot_of_the_swing(self):
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)   # swing at the tip when it froze

        sender.take_over()
        sender.maybe_send(phase=0.5, now=1.05)  # engine phase held through the pause

        assert sink.sent[1].startswith("L00000")

    def test_losing_the_device_rests_the_published_motion_too(self):
        """The readout the Main Funestra draws through a funscript's turn samples forward from
        ``motion_phase`` — rested at the floor the moment Genau loses the
        device, so the waiting motion on screen is the one that will resume."""
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)
        assert sender.current_position() == 9999   # frozen at the tip without this

        sender.rest_at_floor()

        assert sender.motion_phase == 0.0
        assert sender.current_position() == 0


class TestTheRiseOutOfThePark:
    """At full amplitude the motion's floor is the park and the swing starts at
    once — but with the floor raised (amplitude under 100, a shifted center),
    starting there jumped the device across the gap the moment Genau took the
    device back.  The swing holds while the device climbs park-to-floor, then
    begins."""

    def _sender(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=30, center=50)  # floor at 35%
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)   # mid-swing when the script takes it
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
        assert 1600 < halfway < 1900             # about half of the 35% floor

    def test_the_swing_holds_until_the_climb_ends(self):
        """No motion phase accumulates during the rise, so the wave begins at
        the floor rather than part-way up its cycle."""
        sink, sender = self._sender()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.9, now=1.0 + HANDOFF_RAMP_MS / 1000)

        assert sender.motion_phase == 0.0
        arrived = int(sink.sent[1][2:6])
        assert 3400 < arrived < 3600             # the floor, arrived at exactly

    def test_the_motion_is_its_own_again_after_the_climb(self):
        sink, sender = self._sender()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.9, now=1.0 + HANDOFF_RAMP_MS / 1000 + 0.1)
        sender.maybe_send(phase=0.15, now=1.0 + HANDOFF_RAMP_MS / 1000 + 0.2)

        assert sender.motion_phase > 0.0
        assert int(sink.sent[2][2:6]) > 3600     # off the floor, swinging

    def test_the_published_position_follows_the_climb(self):
        """The readout's dot rides ``current_position`` — sitting on the floor
        while the device was still down at the park would detach it from the
        line for the whole climb."""
        sink, sender = self._sender()

        sender.take_over()
        assert sender.current_position() == 0

        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.8, now=1.0 + HANDOFF_RAMP_MS / 2000)

        assert 1600 < sender.current_position() < 1900

    def test_at_full_amplitude_there_is_no_hold(self):
        """His confirmed case stays exactly as it was: the wave starts the
        moment Genau has the device again."""
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=100, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.0, now=0.5)
        sink.sent.clear()

        sender.take_over()
        sender.maybe_send(phase=0.0, now=1.0)
        sender.maybe_send(phase=0.25, now=1.1)

        assert int(sink.sent[1][2:6]) > 3000     # already swinging up


class TestLetGoThroughTheRoundTrip:
    """let_go means "my published wave is the frozen phase-0 one, not yet
    running" — so it holds from the hand-over through the whole climb back, and
    clears only when the wave actually starts.  Readers re-anchor on that edge
    (the trace re-selects its descent top), so an edge that fired at the climb's
    START re-read a wave still two seconds from being true."""

    def _sender(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=30, center=50)  # floor at 35%
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)
        return sender

    def test_handing_over_latches_where_the_device_was(self):
        sender = self._sender()

        sender.hand_over()

        assert sender.let_go_position == 6499                   # the swing's tip

    def test_the_latch_survives_the_climb(self):
        sender = self._sender()
        sender.hand_over()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)                   # climb starts
        sender.maybe_send(phase=0.8, now=1.0 + HANDOFF_RAMP_MS / 2000)

        assert sender.let_go_position is not None

    def test_the_latch_clears_when_the_wave_comes_live(self):
        sender = self._sender()
        sender.hand_over()

        sender.take_over()
        sender.maybe_send(phase=0.7, now=1.0)
        sender.maybe_send(phase=0.9, now=1.0 + HANDOFF_RAMP_MS / 1000)

        assert sender.let_go_position is None

    def test_a_skipped_climb_clears_it_at_once(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=100, center=50)    # floor on the park
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=0.5)
        sender.hand_over()

        sender.take_over()

        assert sender.let_go_position is None


class TestSenderWithDirectState:
    def test_reads_amplitude_from_state(self):
        sink = FakeTCodeSink()
        state = RobotHandState(amplitude=50, center=50)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)
        # amplitude=50, center=50: tip should be ~7500, not 9999
        pos_value = int(sink.sent[0][2:6])
        assert 7000 < pos_value < 8000

    def test_reads_shape_from_state(self):
        sink = FakeTCodeSink()
        state = RobotHandState(shape=WaveformShape.TRIANGLE)
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.25, now=1.0)
        # Triangle at 0.25 should be 5000 (same as sine at 0.25 for default params)
        pos_value = int(sink.sent[0][2:6])
        assert 4900 < pos_value < 5100

    def test_current_position(self):
        sink = FakeTCodeSink()
        state = RobotHandState()
        sender = RobotHandTCodeDriver(sink, robot_hand=state, min_interval=0.0)
        sender.maybe_send(phase=0.5, now=1.0)
        assert sender.current_position() == 9999




"""The device changing hands, both directions.

The driver is told on the edge to climb out of the park or walk the motion
down and rest it.  The tick used to hold this inline, interleaved with ten
other jobs, with the previous play state as a bare attribute beside them.
"""
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
        """Told the same thing twice, the second says nothing: the walk down
        latches where the device was, and doing it again would move the latch."""
        sender = FakeSender()
        handoff = DeviceHandoff(playing=True, tcode_sender=sender)

        handoff.watch(False)
        handoff.watch(False)
        handoff.watch(False)

        assert sender.calls == ["hand_over"]

    def test_the_first_tick_reads_against_the_state_it_was_built_in(self):
        """A PAUSE queued before the first tick is a real falling edge; seeded
        the other way it would either be missed or fire on nothing."""
        sender = FakeSender()

        DeviceHandoff(playing=True, tcode_sender=sender).watch(True)

        assert sender.calls == []

    def test_a_build_with_no_sender_still_follows_the_edge(self):
        handoff = DeviceHandoff(playing=False)

        handoff.watch(True)   # must not raise
        handoff.watch(False)


class TestLearnedMotionOnTheWire:
    """While the learned motion has the hand, the device follows its phrases
    rather than the waveform, and losing the device rests it at its floor."""

    def _learned(self, *, playing: bool = True):
        phrase = Phrase(tuple((500, 80 if i % 2 == 0 else 20) for i in range(16)))
        # Scripts at the wave's own resting pace, so at the bar's 50 the
        # phrases play as written.
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

        # A quarter second into a half-second climb from the floor to 80.
        assert sink.sent[-1].startswith("L04000")

    def test_losing_the_device_rests_the_phrases_at_the_floor(self):
        hand, learned = self._learned()
        sink = FakeTCodeSink()
        sender = RobotHandTCodeDriver(sink, robot_hand=hand, learned=learned, min_interval=0.033)

        sender.hand_over()

        assert sender.let_go_position == 4000
        assert sender.current_position() == 0
