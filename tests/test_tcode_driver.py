from __future__ import annotations

from funestra.funscript import Funscript
from funestra.tcode import HANDOFF_MS, to_tcode_position
from funestra.tcode_driver import FunscriptTCodeDriver


class FakeSink:
    def __init__(self):
        self.sent: list[str] = []
        self.wanted: list[bool] = []

    def send(self, command: str) -> None:
        self.sent.append(command)

    def want(self, wanted: bool) -> None:
        self.wanted.append(wanted)

    def close(self) -> None:
        pass


class TestFunscriptTCodeDriver:
    def _make_fs(self):
        return Funscript(actions=[(0, 0), (1000, 100), (2000, 0)])

    def test_sends_next_waypoint_on_first_update(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(0, self._make_fs(), now=0.0)

        assert len(sink.sent) == 1
        # At t=0, next waypoint is (1000, 100). Remaining = 1000ms.
        assert sink.sent[0] == "L09999I1000"

    def test_remaining_time_shrinks_mid_segment(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(500, self._make_fs(), now=0.0)

        # At t=500, next waypoint is (1000, 100). Remaining = 500ms.
        assert sink.sent[0] == "L09999I500"

    def test_speed_up_shortens_move_duration(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        # At t=0 the next waypoint (1000, 100) is 1000ms away in *media* time,
        # but at 2x playback the video reaches it in 500ms of wall-clock, so the
        # OSR2 must complete its move in 500ms to stay in sync.
        driver.update(0, self._make_fs(), now=0.0, speed=2.0)

        assert sink.sent[0] == "L09999I500"

    def test_slow_down_lengthens_move_duration(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        # At 0.5x the waypoint is 2000ms of wall-clock away, so the move stretches.
        driver.update(0, self._make_fs(), now=0.0, speed=0.5)

        assert sink.sent[0] == "L09999I2000"

    def test_no_duplicate_in_same_segment(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = self._make_fs()

        driver.update(0, fs, now=0.0)
        driver.update(500, fs, now=0.05)

        assert len(sink.sent) == 1

    def test_new_segment_triggers_send(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = self._make_fs()

        driver.update(0, fs, now=0.0)
        driver.update(1001, fs, now=1.0)

        assert len(sink.sent) == 2
        # At t=1001, next waypoint is (2000, 0). Remaining = 999ms.
        assert sink.sent[1] == "L00000I999"

    def test_reset_allows_resend_in_same_segment(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = self._make_fs()

        driver.update(0, fs, now=0.0)
        driver.reset()
        driver.update(100, fs, now=0.1)

        assert len(sink.sent) == 2

    def test_past_the_last_action_the_device_drops_to_its_park(self):
        """The tail after a script's final action is a quiet stretch like any
        other, and its neutral is the parked position — not the last position
        held for as long as the video keeps running."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (1000, 50)])

        driver.update(0, fs, now=0.0)
        driver.update(1500, fs, now=1.5)

        assert sink.sent[-1] == "L00000I500"

    def test_periodic_resend_protects_against_packet_loss(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        # One long segment: 0 to 10000ms
        fs = Funscript(actions=[(0, 0), (10000, 100)])

        driver.update(0, fs, now=0.0)
        driver.update(500, fs, now=0.5)  # same segment, 500ms later

        assert len(sink.sent) == 2


class TestTakingOver:
    """The device is wherever the other driver left it when this one takes it.

    Both drivers send "be at *pos* in *ms*" and the OSR2 interpolates from where
    it is, so the seam is a matter of time alone: the ordinary interval — the gap
    to the next waypoint — can be tens of milliseconds, and crossing most of the
    travel in that is the jolt.
    """

    def test_the_first_waypoint_after_taking_over_is_given_time_to_glide(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        # The next action is 40ms out: on time, and a snap from wherever Genau's
        # motion had the device.
        fs = Funscript(actions=[(0, 0), (40, 100), (2000, 0)])

        driver.update(0, fs, now=0.0)

        assert sink.sent[0] == f"L09999I{HANDOFF_MS}"

    def test_a_waypoint_already_longer_than_the_glide_is_left_alone(self):
        """The glide is a floor, not a rewrite: a script that was always going to
        take a second to get there keeps its own timing."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(0, Funscript(actions=[(0, 0), (1000, 100)]), now=0.0)

        assert sink.sent[0] == "L09999I1000"

    def test_the_script_is_back_on_its_own_clock_once_the_glide_runs_out(self):
        """A glide, not a slowed-down motion: the floor lifts after
        ``HANDOFF_MS`` and every waypoint after that is the script's own."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (40, 100), (80, 0), (2000, 50)])

        driver.update(0, fs, now=0.0)
        driver.update(41, fs, now=HANDOFF_MS / 1000 + 0.01)

        assert sink.sent[1] == "L00000I39"

    def test_a_waypoint_inside_the_glide_is_stretched_too(self):
        """Not the first command alone.  The device is still on its way when the
        next waypoint lands, and an ordinary interval there would make it cover
        whatever was left of the gap in a frame — the jolt, moved."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (40, 100), (80, 0), (2000, 50)])

        driver.update(0, fs, now=0.0)
        driver.update(41, fs, now=0.05)

        assert sink.sent[1] == f"L00000I{HANDOFF_MS}"

    def test_taking_the_device_back_glides_again(self):
        """Genau holds it through a quiet stretch and the script takes over
        again; that seam is the same seam."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (40, 100), (80, 0), (2000, 50)])
        driver.update(0, fs, now=0.0)
        driver.update(41, fs, now=HANDOFF_MS / 1000 + 0.01)

        driver.reset()
        driver.update(41, fs, now=HANDOFF_MS / 1000 + 0.02)

        assert sink.sent[-1] == f"L00000I{HANDOFF_MS}"


class TestLeadInPark:
    def _lead_in_fs(self):
        # Isolated blip at t=0, then dense action from 60s: onset = 60000.
        return Funscript(actions=[(0, 50), (60000, 0), (60300, 100), (60600, 0)])

    def test_the_handed_over_buffer_rests_at_park_then_rises_to_the_opening(self):
        """The neutral through the stretch between the drivers is the parked
        position: the device rests there while the handoff buffer runs down, and
        only a beat ahead of the onset does it rise — to the cluster's *opening*
        action, so it is at the script's starting end as the action fires
        rather than sitting at the floor while the opening, at the opposite
        end, scrolls toward the playhead."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 50), (60000, 100), (60300, 0), (60600, 100)])

        driver.update(56_000, fs, now=0.0)   # buffer: still parked
        driver.update(59_500, fs, now=1.0)   # the rise: aim at (60000, 100)

        # The first park after a takeover IS the handoff ramp down.
        assert sink.sent == ["L00000I2000", "L09999I500"]

    def test_before_a_prompt_script_the_target_is_the_opening_action_itself(self):
        """The rise's first target is where the script *begins* — skipping to
        the first motion's far end sent the device the wrong way across the
        range before playback got there."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(3000, 100), (3300, 0)])

        driver.update(0, fs, now=0.0)      # short lead-in, still parked
        driver.update(2_500, fs, now=1.0)  # rising: the opening action, not its far end

        assert sink.sent == ["L00000I2000", "L09999I500"]

    def test_parks_at_closest_position_during_lead_in(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(10000, self._lead_in_fs(), now=0.0)

        # Rest at position 0 (closest), reached over the handoff ramp: the
        # fresh driver's device is wherever the last driver left it.
        assert sink.sent == ["L00000I2000"]

    def test_resumes_normal_driving_at_first_real_event(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = self._lead_in_fs()

        driver.update(10000, fs, now=0.0)   # parked during lead-in
        driver.update(60000, fs, now=1.0)   # onset reached: drive normally

        # Park, then the next waypoint aims at (60300, 100). Remaining = 300ms.
        assert sink.sent == ["L00000I2000", "L09999I300"]

    def test_park_is_rate_limited_but_resends(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = self._lead_in_fs()

        driver.update(10000, fs, now=0.0)    # first park send
        driver.update(11000, fs, now=0.05)   # within resend interval: suppressed
        driver.update(12000, fs, now=0.15)   # past resend interval: resends

        # A resend carries the descent's REMAINING time, not a fresh interval:
        # re-issued whole, each resend retargeted the in-flight glide from
        # wherever the device was, and every drawn straight ramp became a fast
        # exponential the drawing never showed.
        assert sink.sent == ["L00000I2000", "L00000I1850"]


class TestPark:
    """park() rests the OSR2 at its closest position with no funscript in play —
    an unscripted video.  It reuses the lead-in rest's waypoint and edge gating,
    so callers can hold the device parked without a script to drive from."""

    def test_a_park_after_scripting_is_the_plan_s_own_settle(self):
        """Only the FIRST park after a takeover is the long handoff ramp; once
        this driver has been scripting, dropping out of a cluster is the plan's
        half-second settle, exactly as drawn."""
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 100), (200, 0), (400, 100), (600, 0)])

        driver.update(100, fs, now=0.0)     # mid-cluster: a waypoint
        driver.update(10_000, fs, now=1.0)  # the tail: parked

        assert sink.sent[-1] == "L00000I500"

    def test_sends_closest_position(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.park(now=0.0)

        # Position 0 (closest), over the handoff ramp: a fresh driver's device
        # is wherever whoever had it last left it.
        assert sink.sent == ["L00000I2000"]

    def test_edge_gated_then_resends(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.park(now=0.0)   # first send
        driver.park(now=0.05)  # within the resend interval: suppressed
        driver.park(now=0.15)  # past the resend interval: resends

        assert sink.sent == ["L00000I2000", "L00000I1850"]


class TestDepthAtSpeed:
    def _fast_fs(self):
        # A full cycle every 200ms -- past what the device can travel, so
        # doubling the rate has to buy its timing with depth.
        return Funscript(actions=[(0, 0), (200, 100), (400, 0), (600, 100)])

    def _aimed_at(self, speed):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        driver.update(0, self._fast_fs(), now=0.0, speed=speed)
        return int(sink.sent[0][2:6])

    def test_a_script_past_the_devices_reach_is_aimed_shallower_when_sped_up(self):
        assert self._aimed_at(2.0) == 5000

    def test_the_same_script_is_aimed_at_its_full_depth_at_normal_speed(self):
        assert self._aimed_at(1.0) == 9999


def test_a_script_past_the_max_intensity_is_aimed_as_shallow_as_the_max_intensity_leaves_it():
    sink = FakeSink()
    fs = Funscript(actions=[(0, 0), (1000, 100), (2000, 0), (3000, 100)])

    FunscriptTCodeDriver(sink).update(0, fs, now=0.0, max_intensity=30)

    assert sink.sent[0] == f"L0{to_tcode_position(fs.paced_position_at(1000, 1.0, max_intensity=30)):04d}I1000"


def test_a_funscript_driver_wants_the_osr2_through_its_slot():
    sink = FakeSink()
    driver = FunscriptTCodeDriver(sink)

    driver.want(True)
    driver.want(False)

    assert sink.wanted == [True, False]
