"""The readout's cadence, and what goes out at it.

Nothing had ever pinned it.  The readout goes out 25 times a second because its
trace scrolls; drop the throttle and the app still works, faster and noisier --
a file written at the refresh rate -- which is why it shows up as a failure
nowhere else.
"""
from __future__ import annotations

import random

import pytest

from funestra import wave_stack
from funestra.cruise_control import (
    CruiseControlState,
    enable_cruise_control,
    tick_cruise_control,
)
from funestra.drive_readout import TRACE_SAMPLES
from funestra.flag import Flag
from funestra.flick_advance import FlickAdvanceState
from funestra.genau_controls import GenauControls
from funestra.genau_readout import AutoMotion, GenauReadout
from funestra.learned_model import LearnedModel, Phrase, classify
from funestra.learned_motion import (
    LearnedMotionState,
    enable_learned_motion,
    tick_learned_motion,
)
from funestra.robot_hand import MIN_BPM, RobotHandState, bpm_for_speed
from funestra.robot_hand_beat import BeatEngine


class FakeSender:
    let_go_position = None
    motion_phase = 0.0

    def current_position(self) -> int:
        return 5000


def _controls(**over) -> GenauControls:
    return GenauControls(
        engine=BeatEngine(phase=0.0, last_tick=0.0),
        paused=Flag(),
        step_flick=lambda _step: None,
        robot_hand=over.get("direct") or RobotHandState(speed=50, amplitude=60),
        cruise_control_state=over.get("cruise") or CruiseControlState(),
        flick_advance_state=FlickAdvanceState(interval=20),
    )


def _readout(**over) -> GenauReadout:
    return GenauReadout(
        controls=over.pop("controls", None) or _controls(),
        beats_per_loop=over.pop("beats_per_loop", 4.0),
        tcode_sender=over.pop("tcode_sender", FakeSender()),
        **over,
    )


# Deltas either side of a threshold, chosen as exact binary fractions so the
# comparison is decided by the rule and not by float error -- and chosen close,
# so the threshold cannot be moved a step either way without reddening one of
# them.
JUST_UNDER_DRIVE = 0.0390625     # 5/128, under 0.04
JUST_OVER_DRIVE = 0.04296875     # 11/256, over 0.04


class TestHowOftenTheReadoutGoesOut:
    def _published(self, tmp_path):
        drive = tmp_path / "genau_drive.txt"
        return drive, _readout(drive_file=drive)

    def test_the_first_tick_publishes(self, tmp_path):
        drive, readout = self._published(tmp_path)

        readout.update(1.0)

        assert drive.exists()

    def test_a_tick_too_soon_after_it_does_not(self, tmp_path):
        drive, readout = self._published(tmp_path)
        readout.update(1.0)
        drive.write_text("stale", encoding="utf-8")

        readout.update(1.0 + JUST_UNDER_DRIVE)

        assert drive.read_text(encoding="utf-8") == "stale"

    def test_a_tick_far_enough_after_it_does(self, tmp_path):
        drive, readout = self._published(tmp_path)
        readout.update(1.0)
        drive.write_text("stale", encoding="utf-8")

        readout.update(1.0 + JUST_OVER_DRIVE)

        assert drive.read_text(encoding="utf-8") != "stale"

    def test_a_build_with_nowhere_to_publish_says_nothing(self):
        _readout().update(1.0)   # must not raise



class TestWhatTheLineIsEachTime:
    def test_under_the_broker_the_line_still_goes_out(self):
        """The whole readout used to come down here, leaving the device running
        itself with no line at all."""
        readout = _readout()

        readout.update(1.0, AutoMotion(phase=0.0, bpm=90.0))

        assert readout.drive is not None

    def test_its_line_does_not_jump_where_the_beat_starts_round_again(self):
        """The broker's beat counts 0 to 1 and starts again, while the trace's
        knots stay put only on a phase counted up without wrapping: taken as it
        comes, the line jumped sideways at every wrap."""
        wrapping = _readout()
        counting = _readout()

        wrapping.update(1.0, AutoMotion(phase=0.99, bpm=87.0))
        wrapping.update(1.1, AutoMotion(phase=0.01, bpm=87.0))
        counting.update(1.0, AutoMotion(phase=0.99, bpm=87.0))
        counting.update(1.1, AutoMotion(phase=1.01, bpm=87.0))

        assert wrapping.drive == counting.drive


class TestTheSpanTheTraceIsDrawnOver:
    """Published with the readout, because a funscript the Main Funestra draws on this same
    trace has to be sampled over the same stretch and the Main Funestra has nowhere else to
    learn it -- two spans would make a handoff look like a jump."""

    @pytest.mark.parametrize("beats_per_loop", [2.0, 4.0, 8.0])
    def test_it_is_one_whole_cycle_at_the_slowest_speed(self, beats_per_loop):
        readout = _readout(beats_per_loop=beats_per_loop)

        readout.update(1.0)

        assert readout.drive.trace_seconds == pytest.approx(
            60.0 * beats_per_loop / MIN_BPM)


class TestTheTraceHoldsStillAndSlides:
    """He watched the blue line writhe in every mode: it was re-read from the
    clock at every publish, and with a few samples to a swing the heights at
    fixed columns changed every frame.  Every mode is read on knots now."""

    def test_the_wave_holds_its_picture_between_knots(self):
        sender = FakeSender()
        readout = _readout(tcode_sender=sender)
        readout.update(1.0)
        first = readout.drive
        # A twelfth of a knot on: the readout spans 12 s over 80 samples, and
        # at speed 50 the phase moves 0.0126 cycles in 0.05 s.
        sender.motion_phase = 0.0126

        readout.update(1.05)

        assert readout.drive.waveform == first.waveform
        assert readout.drive.slide > first.slide
        assert readout.drive.edge is not None

    def test_cruise_controls_sum_holds_its_picture_between_knots(self):

        hand = RobotHandState(playing=True, speed=50, amplitude=60)
        cruise = CruiseControlState(rng=random.Random(2))
        enable_cruise_control(cruise)
        tick_cruise_control(hand, cruise, now=1.0)
        tick_cruise_control(hand, cruise, now=1.05)
        controls = _controls(direct=hand, cruise=cruise)
        readout = _readout(controls=controls)
        readout.update(1.05)
        first = readout.drive
        tick_cruise_control(hand, cruise, now=1.1)

        readout.update(1.1)

        assert readout.drive.waveform == pytest.approx(first.waveform, abs=1e-4)
        assert readout.drive.slide > first.slide


class TestTheTraceUnderTheMaxIntensity:
    def test_the_readout_says_the_max_intensity_the_wave_is_held_to(self):
        hand = RobotHandState(playing=True, speed=90, amplitude=100, max_intensity=40)
        readout = _readout(controls=_controls(direct=hand))

        readout.update(1.0)

        assert readout.drive.max_intensity == 40

    def test_a_stack_held_down_by_its_max_intensity_is_drawn_as_the_stack_it_leaves(self):
        hand = RobotHandState(playing=True, speed=90, amplitude=100, max_intensity=40)
        cruise = CruiseControlState(rng=random.Random(2))
        enable_cruise_control(cruise)
        tick_cruise_control(hand, cruise, now=1.0)
        tick_cruise_control(hand, cruise, now=1.05)
        readout = _readout(controls=_controls(direct=hand, cruise=cruise))

        readout.update(1.05)

        drive = readout.drive
        heights, _slide = wave_stack.trace_window(
            cruise.stack, cruise.clock, TRACE_SAMPLES, drive.trace_seconds, max_intensity=40)
        assert drive.waveform == pytest.approx(tuple(heights[:TRACE_SAMPLES]))


class TestTheTraceUnderTheLearnedMotion:
    def test_it_is_the_phrases_coming_up_rather_than_the_waveform(self):
        phrase = Phrase(tuple((500, 80 if i % 2 == 0 else 20) for i in range(16)))
        model = LearnedModel(phrases={classify(phrase): [phrase]}, seen={classify(phrase): 1})
        hand = RobotHandState(playing=True, speed=50, amplitude=100)
        learned = LearnedMotionState(model=model, rng=random.Random(1))
        enable_learned_motion(learned)
        tick_learned_motion(hand, learned, now=1.0)
        controls = _controls(direct=hand)
        controls.learned_motion_state = learned
        readout = _readout(controls=controls)

        readout.update(1.0)

        heights = readout.drive.waveform
        assert heights[0] == pytest.approx(0.0)
        assert max(heights) == pytest.approx(0.8, abs=0.02)
        assert min(heights[1:]) == pytest.approx(0.2, abs=0.05)
        assert readout.drive.slide == 0.0
        assert readout.drive.edge is not None

    def test_it_holds_still_between_knots_and_slides(self):
        phrase = Phrase(tuple((500, 80 if i % 2 == 0 else 20) for i in range(16)))
        model = LearnedModel(phrases={classify(phrase): [phrase]}, seen={classify(phrase): 1},
                             native_cycle_ms=60_000 / bpm_for_speed(50))
        hand = RobotHandState(playing=True, speed=50, amplitude=100)
        learned = LearnedMotionState(model=model, rng=random.Random(1))
        enable_learned_motion(learned)
        tick_learned_motion(hand, learned, now=1.0)
        controls = _controls(direct=hand)
        controls.learned_motion_state = learned
        readout = _readout(controls=controls)
        readout.update(1.0)
        first = readout.drive
        tick_learned_motion(hand, learned, now=1.05)

        readout.update(1.05)

        assert readout.drive.waveform == first.waveform
        assert readout.drive.slide > first.slide

