"""What of Genau's publish this video's picture believes, and for how long.

Two things the gate holds across frames: the descent forecasts, chosen once and
held, and whether Genau has been seen live in *this* video yet.

The forecasts are watched through the touch-down the status file publishes —
``handoff_touch`` answers out of the same latch — and the question every case
below asks is the same one: a newer publish has arrived, so is the choice made
for this boundary still the one that was made first, or has it been made again?
Held, the wave underneath can move as much as it likes and the answer does not;
voided, the fresh wave gets to answer.

The motion used throughout rests its floor ON the park (full amplitude,
centered), because only such a motion has a touch-down at all; a raised floor
ramps down instead and has none to publish.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from funestra.descent_latch import DescentChoice, DescentLatch, DriveKey
from funestra.drive_gate import DriveGate, next_handoff_touch
from funestra.drive_readout import DRIVEN_BY_FUNSCRIPT, TRACE_SAMPLES, DriveHud
from funestra.funscript import Funscript

SPAN_S = 7.9
STEP_MS = 100
FIRST_VIDEO = Path("videos/Jane Doe - scene one.mp4")
SECOND_VIDEO = Path("videos/Jane Doe - scene two.mp4")
# The touch the trace chooses for the boundary ahead, on the first read.
CHOSEN_TOUCH_MS = 3_600
# How much newer the second publish is.  Deliberately not equal to any playhead
# a case moves to: a wave advanced by exactly as much as the playhead reads the
# same in absolute time, and a re-choice off one would land back on the first
# answer and look like a carry.
NEWER_MS = 200


def _motion(ms: int = 0, **over) -> DriveHud:
    """Genau's publish, *ms* into the video: the same wave, phase advanced."""
    steps = ms / STEP_MS
    base = dict(
        speed=50, amplitude=100, center=50, trace_seconds=SPAN_S,
        waveform=tuple(0.5 - 0.5 * np.cos((i + steps) / 6) for i in range(TRACE_SAMPLES)))
    base.update(over)
    return DriveHud(**base)


def _script() -> Funscript:
    """A script whose one cluster is still ahead of the playhead, so the handoff
    into it is inside the drawn window."""
    return Funscript(actions=[(t, 0 if (t // 200) % 2 else 100)
                              for t in range(8_000, 9_001, 200)])


class FakeSession:
    """What the gate reads off the Funestra: where it is, in what, how fast."""

    def __init__(self) -> None:
        self.funscript_as_played = _script()
        self.current_video = FIRST_VIDEO
        self.position_ms = 0.0
        self.speed = 1.0


def _gate_holding_a_forecast() -> tuple[DriveGate, FakeSession]:
    """A gate that has read once and chosen a touch for the boundary ahead."""
    session = FakeSession()
    gate = DriveGate(session)
    gate.readout(_motion())
    assert gate.handoff_touch() == CHOSEN_TOUCH_MS
    return gate, session


def _a_newer_publish_arrives(gate: DriveGate) -> None:
    gate.readout(_motion(NEWER_MS))


class TestChoosingAForecast:
    def test_the_trace_chooses_a_touch_down_for_the_boundary_ahead(self):
        gate = DriveGate(FakeSession())

        gate.readout(_motion())

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_with_no_motion_published_there_is_nothing_to_choose_from(self):
        gate = DriveGate(FakeSession())

        gate.readout(None)

        assert gate.handoff_touch() is None


class TestTheDeviceRunningItself:
    """In auto mode the OSR2 drives on its own firmware: the funscript's T-Code is
    dropped at the broker and Genau is not sending either, so the handoff this
    gate exists to draw is not happening.  What the picture must show is the one
    motion there is -- the device's own, as Genau publishes it -- and folding a
    script into that draws a plan for a device nothing here has.
    """

    def test_the_publish_is_drawn_whole_rather_than_composed_with_the_script(self):
        session = FakeSession()
        gate = DriveGate(session)
        published = _motion()

        hud = gate.readout(published, device_drives_itself=True)

        assert hud.waveform == published.waveform
        assert hud.segments == ()

    def test_with_nothing_published_there_is_still_a_readout_to_draw(self):
        gate = DriveGate(FakeSession())

        assert gate.readout(None, device_drives_itself=True) is not None

    def test_no_forecast_survives_the_device_taking_itself(self):
        """A touch chosen for a boundary the device will sail through is a moment
        the arbiter must not act on."""
        gate, _session = _gate_holding_a_forecast()

        gate.readout(_motion(NEWER_MS), device_drives_itself=True)

        assert gate.handoff_touch() is None


class TestAChoiceThatIsHeld:
    """Re-read live every frame, the top breathed with the beat between Genau's
    publish cadence and the frame clock, and the seam flickered between "blue
    ends on the park" and a slightly diagonal ramp."""

    def test_a_newer_publish_does_not_move_it(self):
        gate, _session = _gate_holding_a_forecast()

        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_frames_worth_of_playing_does_not_move_it(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_second_frame_of_playing_does_not_move_it_either(self):
        """It is the step BETWEEN frames that is measured, not the distance from
        where the video started, so ordinary playback never accumulates into a
        jump.  The gate has to remember where the playhead was on the last
        frame for that to be true."""
        gate, session = _gate_holding_a_forecast()

        for ms in (300, 600):
            session.position_ms = ms
            _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_stall_too_short_to_be_a_pause_does_not_move_it(self):
        """The trace's 40ms quantum makes some real frames read as zero."""
        gate, session = _gate_holding_a_forecast()
        for _ in range(5):
            gate.readout(_motion())

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_pause_still_running_does_not_move_it(self):
        """The choice goes when the playhead moves again, not while it waits:
        the picture on a paused Funestra is the one it was already showing."""
        gate, _session = _gate_holding_a_forecast()

        for _ in range(40):
            _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS


class TestWhatVoidsAChoice:
    """Every one of these means the wave the choice was cut from has stopped
    describing this approach, so the fresh wave gets to answer instead."""

    def test_a_stint_with_nothing_published(self):
        """The wave keeps moving while nothing here watches it, so every held
        forecast is void by the time it could be read again."""
        gate, _session = _gate_holding_a_forecast()

        gate.readout(None)
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_different_video(self):
        gate, session = _gate_holding_a_forecast()

        session.current_video = SECOND_VIDEO
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_rewind(self):
        """The carry rules are written for one continuous approach, and a
        rewind approaches the SAME boundary again with a realigned wave -- the
        old choice's touch then cuts the new wave anywhere, which is how the
        blue once overran its own drawn ending by a whole cycle.

        Nothing answers in its place here, unlike the other four: a playhead
        this far back is outside the freeze horizon, so the choice goes back to
        being a live forecast and the field publishes empty until the approach
        re-enters it."""
        gate, session = _gate_holding_a_forecast()

        session.position_ms = -300
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() is None

    def test_a_jump_forward(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 900
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_the_end_of_a_pause_long_enough_to_slide_the_wave(self):
        """A real pause stands the media clock still while Genau's wave keeps
        moving in wall time, so every media-anchored forecast has slid off the
        wave it was cut from by the time the playhead moves again."""
        gate, session = _gate_holding_a_forecast()
        for _ in range(26):
            gate.readout(_motion())  # the playhead stands still

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS


class TestExactlyWhereTheseRulesBegin:
    """The three numbers were tuned against a real device, and every one of
    them was only bracketed: the rewind case moved 300ms and nothing said that
    250 must not void, so the window could have been any width down to zero --
    including "any backward motion at all", which is the asymmetry the constant
    exists to avoid.  The numbers are asserted here, from both sides.
    """

    def test_a_step_back_the_width_of_the_window_is_still_playing(self):
        """-250ms: the trace's own quantum makes some real frames read oddly,
        and a picture that voided its forecasts on one would flicker."""
        gate, session = _gate_holding_a_forecast()

        session.position_ms = -250
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_one_millisecond_further_back_is_a_rewind(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = -251
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_slow_frame_may_carry_the_playhead_this_far_forward(self):
        """+400ms: forward motion has to allow for a frame the machine was too
        busy to draw, which a rewind does not."""
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 400
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_one_millisecond_further_on_is_a_jump(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 401
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_twenty_five_standing_frames_are_not_yet_a_pause(self):
        """The setup's own read is the first of them, so twenty-four more."""
        gate, session = _gate_holding_a_forecast()
        for _ in range(24):
            gate.readout(_motion())

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_twenty_six_of_them_are(self):
        gate, session = _gate_holding_a_forecast()
        for _ in range(25):
            gate.readout(_motion())

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_pause_a_seek_ended_is_voided_once_and_not_again(self):
        """The seek takes the standing count with it.  Left standing, the first
        ordinary frame after the seek would void a second time and throw away
        the choice made from the wave the seek actually landed on."""
        gate, session = _gate_holding_a_forecast()
        for _ in range(30):
            gate.readout(_motion())      # a real pause
        session.position_ms = 900                           # ended by a jump
        _a_newer_publish_arrives(gate)
        chosen_where_it_landed = gate.handoff_touch()

        session.position_ms = 940                           # an ordinary frame
        gate.readout(_motion(NEWER_MS * 2))

        assert gate.handoff_touch() == chosen_where_it_landed


class TestHowFastTheVideoIsRunning:
    def test_the_touch_is_chosen_at_the_rate_the_video_is_playing_at(self):
        """The trace covers wall-clock time, so at double speed twice as much
        of the script goes past inside it and the touch the device will be set
        down on is a different one.  The Funestra knows the rate; nothing else does."""
        session = FakeSession()
        session.speed = 2.0
        gate = DriveGate(session)

        gate.readout(_motion())

        assert gate.handoff_touch() not in (None, CHOSEN_TOUCH_MS)


class TestWhetherGenauHasBeenSeenLiveHere:
    """``let_go`` is Genau's own latch of the height it handed over at, and it
    survives a video change while Genau sits paused."""

    def test_a_handoff_from_before_this_video_is_read_as_still_live(self):
        """A descent drawn from that height tops a ramp the device never made
        here, so the publish is taken as though Genau still had the device."""
        gate = DriveGate(FakeSession())

        hud = gate.readout(_motion(let_go=0.44))

        assert hud.let_go is None

    def test_once_genau_has_been_seen_live_a_handoff_is_honored(self):
        gate = DriveGate(FakeSession())
        gate.readout(_motion())  # let_go unset: Genau has it

        hud = gate.readout(_motion(let_go=0.44))

        assert hud.let_go == 0.44

    def test_a_new_video_makes_genau_prove_itself_live_again(self):
        session = FakeSession()
        gate = DriveGate(session)
        gate.readout(_motion())

        session.current_video = SECOND_VIDEO
        hud = gate.readout(_motion(let_go=0.44))

        assert hud.let_go is None

    def test_a_stint_with_nothing_published_does_not_re_arm_it(self):
        """A publish that failed to arrive is not a new video: the device is
        where Genau left it, and the handoff it published still describes it."""
        gate = DriveGate(FakeSession())
        gate.readout(_motion())

        gate.readout(None)
        hud = gate.readout(_motion(let_go=0.44))

        assert hud.let_go == 0.44

    @pytest.mark.parametrize("what_moved", ["a rewind", "a jump forward", "a pause"])
    def test_nothing_that_only_voids_a_forecast_re_arms_it(self, what_moved):
        """The two things this gate holds go stale on different events, and only
        a new video moves both.  Every rule that voids the held forecasts leaves
        the playhead somewhere else in the SAME video, where Genau has not gone
        anywhere and the handoff it published still describes the device — so
        stripping ``let_go`` there would top the next descent off the parked
        publish and draw a ramp from a height nothing is at.
        """
        session = FakeSession()
        gate = DriveGate(session)
        gate.readout(_motion())   # let_go unset: seen live
        if what_moved == "a pause":
            for _ in range(30):
                gate.readout(_motion())
        session.position_ms = {"a rewind": -300, "a jump forward": 900,
                               "a pause": 40}[what_moved]

        hud = gate.readout(_motion(NEWER_MS, let_go=0.44))

        assert hud.let_go == 0.44


class TestALoopingFunestra:
    def test_the_trace_is_drawn_from_the_script_as_the_funestra_will_play_it(self):
        swings = Funscript(actions=[(0, 0), (1_250, 100), (2_500, 0), (3_760, 100), (5_010, 0)])
        session = FakeSession()
        session.current_funscript = swings
        session.funscript_as_played = swings.looped(0, 5_000)
        session.position_ms = 4_000.0

        hud = DriveGate(session).readout(_motion(4_000))

        assert hud.segments == ((0, DRIVEN_BY_FUNSCRIPT),)


class TestAFunestraHeldDownByTheMaxIntensity:
    def test_its_script_is_drawn_as_shallow_as_it_is_sent(self):
        swings = Funscript(actions=[(t, 0 if (t // 200) % 2 else 100)
                                    for t in range(0, 20_001, 200)])
        session = FakeSession()
        session.funscript_as_played = swings
        session.max_intensity = 30

        hud = DriveGate(session).readout(_motion())

        assert hud.waveform == swings.planned_trace_window(
            0, round(SPAN_S * 1000), TRACE_SAMPLES, max_intensity=30)[0][:TRACE_SAMPLES]


class TestAFunestraThatDoesNotSayHowItPlaysItsScript:
    def test_is_drawn_from_the_script_it_has(self):
        session = FakeSession()
        session.current_funscript = session.funscript_as_played
        del session.funscript_as_played
        gate = DriveGate(session)

        gate.readout(_motion())

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS


class TestTheTouchTheTraceChose:
    """``next_handoff_touch`` reads the choice out of the trace's own latch.

    One chooser, the picture, and the arbiter follows it: when each side chose
    its own touch from its own read of the wave they could pick different
    troughs, the arbiter stopped the device one touch early, and the leftover
    drawn blue vanished the moment the dot reached it.
    """

    # The boundary the script below opens its cluster at, and a touch latched
    # for it.
    BOUNDARY_MS = 3_000
    TOUCHING = DriveKey(center=50, amplitude=100, speed=50, let_go=None)

    @classmethod
    def _latched(cls, top: float = 0.35, touch: int | None = 3_600,
                 key: DriveKey | None = None) -> DescentLatch:
        latch = DescentLatch()
        latch.remember(cls.BOUNDARY_MS,
                       DescentChoice(key=key or cls.TOUCHING, top=top, touch=touch),
                       stale_before=0)
        return latch

    def test_an_unscripted_video_has_no_handoff_to_chose_one_for(self):
        assert next_handoff_touch(None, 0, self._latched()) is None

    def test_resting_before_a_turn_takes_the_turn_it_is_approaching(self):
        """The boundary in play is the one ahead: the device is about to change
        hands there."""
        assert next_handoff_touch(_script(), 0, self._latched()) == 3_600

    def test_inside_a_turn_it_takes_the_boundary_just_crossed(self):
        """The arbiter is still ending that turn, so the touch it needs is the
        one the picture drew the ending on."""
        assert next_handoff_touch(_script(), 5_000, self._latched()) == 3_600

    def test_a_rest_with_no_turn_after_it_has_no_boundary_at_all(self):
        """Past the last cluster nothing hands over again, and a lookup there
        would otherwise land on whatever the latch still held."""
        assert next_handoff_touch(_script(), 20_000, self._latched()) is None

    def test_a_boundary_with_nothing_latched_yet_says_so(self):
        """The choice stays live while the boundary is far, so early in an
        approach there is nothing to publish."""
        assert next_handoff_touch(_script(), 0, DescentLatch()) is None

    def test_a_ramped_handoff_has_no_touch_down_to_name(self):
        """A motion whose floor sits above the park never comes down onto it:
        the gray ramps instead, and there is no touch."""
        ramped = self._latched(
            top=0.12, touch=None,
            key=DriveKey(center=50, amplitude=80, speed=50, let_go=None))

        assert next_handoff_touch(_script(), 0, ramped) is None
