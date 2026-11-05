from __future__ import annotations

import random

import pytest

from funestra.flag import Flag
from funestra.flick_advance import FlickAdvanceState
from funestra.genau_controls import GenauControls
from funestra.genau_visualizer import AutoMotion, GenauVisualizer
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
        flick_advance_state=FlickAdvanceState(interval=20),
    )


def _visualizer(**over) -> GenauVisualizer:
    return GenauVisualizer(
        controls=over.pop("controls", None) or _controls(),
        beats_per_loop=over.pop("beats_per_loop", 4.0),
        tcode_sender=over.pop("tcode_sender", FakeSender()),
        **over,
    )


JUST_UNDER_DRIVE = 0.0390625
JUST_OVER_DRIVE = 0.04296875


class TestTheVisualizerGoesOutOnATimerSinceItsTraceScrollsWhileNothingElseChanges:
    def _published(self, tmp_path):
        drive = tmp_path / "genau_drive.txt"
        return drive, _visualizer(drive_file=drive)

    def test_the_first_tick_publishes(self, tmp_path):
        drive, visualizer = self._published(tmp_path)

        visualizer.update(1.0)

        assert drive.exists()

    def test_a_tick_too_soon_after_it_does_not(self, tmp_path):
        drive, visualizer = self._published(tmp_path)
        visualizer.update(1.0)
        drive.write_text("stale", encoding="utf-8")

        visualizer.update(1.0 + JUST_UNDER_DRIVE)

        assert drive.read_text(encoding="utf-8") == "stale"

    def test_a_tick_far_enough_after_it_does(self, tmp_path):
        drive, visualizer = self._published(tmp_path)
        visualizer.update(1.0)
        drive.write_text("stale", encoding="utf-8")

        visualizer.update(1.0 + JUST_OVER_DRIVE)

        assert drive.read_text(encoding="utf-8") != "stale"

    def test_a_build_with_nowhere_to_publish_says_nothing(self):
        _visualizer().update(1.0)



class TestWhatTheLineIsEachTime:
    def test_under_the_broker_the_line_still_goes_out(self):
        visualizer = _visualizer()

        visualizer.update(1.0, AutoMotion(phase=0.0, bpm=90.0))

        assert visualizer.drive is not None

    def test_its_line_does_not_jump_where_the_beat_starts_round_again(self):
        wrapping = _visualizer()
        counting = _visualizer()

        wrapping.update(1.0, AutoMotion(phase=0.99, bpm=87.0))
        wrapping.update(1.1, AutoMotion(phase=0.01, bpm=87.0))
        counting.update(1.0, AutoMotion(phase=0.99, bpm=87.0))
        counting.update(1.1, AutoMotion(phase=1.01, bpm=87.0))

        assert wrapping.drive == counting.drive


class TestTheSpanTheTraceIsDrawnOver:
    @pytest.mark.parametrize("beats_per_loop", [2.0, 4.0, 8.0])
    def test_it_is_one_whole_cycle_at_the_slowest_speed(self, beats_per_loop):
        visualizer = _visualizer(beats_per_loop=beats_per_loop)

        visualizer.update(1.0)

        assert visualizer.drive.trace_seconds == pytest.approx(
            60.0 * beats_per_loop / MIN_BPM)


class TestTheTraceHoldsStillAndSlides:
    def test_the_wave_holds_its_drawing_between_knots(self):
        sender = FakeSender()
        visualizer = _visualizer(tcode_sender=sender)
        visualizer.update(1.0)
        first = visualizer.drive
        sender.motion_phase = 0.0126

        visualizer.update(1.05)

        assert visualizer.drive.waveform == first.waveform
        assert visualizer.drive.slide > first.slide
        assert visualizer.drive.edge is not None


class TestTheTraceUnderTheMaxIntensity:
    def test_the_visualizer_says_the_max_intensity_the_wave_is_held_to(self):
        hand = RobotHandState(playing=True, speed=90, amplitude=100, max_intensity=40)
        visualizer = _visualizer(controls=_controls(direct=hand))

        visualizer.update(1.0)

        assert visualizer.drive.max_intensity == 40


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
        visualizer = _visualizer(controls=controls)

        visualizer.update(1.0)

        heights = visualizer.drive.waveform
        assert heights[0] == pytest.approx(0.0)
        assert max(heights) == pytest.approx(0.8, abs=0.02)
        assert min(heights[1:]) == pytest.approx(0.2, abs=0.05)
        assert visualizer.drive.slide == 0.0
        assert visualizer.drive.edge is not None

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
        visualizer = _visualizer(controls=controls)
        visualizer.update(1.0)
        first = visualizer.drive
        tick_learned_motion(hand, learned, now=1.05)

        visualizer.update(1.05)

        assert visualizer.drive.waveform == first.waveform
        assert visualizer.drive.slide > first.slide

