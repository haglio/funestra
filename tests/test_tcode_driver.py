from __future__ import annotations

from funestra.funscript import Funscript
from funestra.tcode import to_tcode_position
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
        assert sink.sent[0] == "L09999I1000"

    def test_remaining_time_shrinks_mid_segment(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(500, self._make_fs(), now=0.0)

        assert sink.sent[0] == "L09999I500"

    def test_speed_up_shortens_move_duration(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(0, self._make_fs(), now=0.0, speed=2.0)

        assert sink.sent[0] == "L09999I500"

    def test_slow_down_lengthens_move_duration(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

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
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (1000, 50)])

        driver.update(0, fs, now=0.0)
        driver.update(1500, fs, now=1.5)

        assert sink.sent[-1] == "L00000I500"

    def test_periodic_resend_protects_against_packet_loss(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (10000, 100)])

        driver.update(0, fs, now=0.0)
        driver.update(500, fs, now=0.5)

        assert len(sink.sent) == 2


class TestTakingOver:
    def test_the_first_waypoint_of_a_session_or_after_taking_over_is_given_time_to_glide_since_the_osr2_moves_from_wherever_it_is_in_the_time_it_is_told(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (40, 100), (2000, 0)])

        driver.update(0, fs, now=0.0)

        assert sink.sent[0] == "L09999I300"

    def test_a_waypoint_already_longer_than_the_glide_is_left_alone(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(0, Funscript(actions=[(0, 0), (1000, 100)]), now=0.0)

        assert sink.sent[0] == "L09999I1000"

    def test_the_script_is_back_on_its_own_clock_once_the_glide_runs_out_within_a_beat(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (40, 100), (80, 0), (2000, 50)])

        driver.update(0, fs, now=0.0)
        driver.update(41, fs, now=0.31)

        assert sink.sent[1] == "L00000I39"

    def test_a_waypoint_inside_the_glide_is_stretched_too_arriving_late_rather_than_snapping_there_on_time(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (40, 100), (80, 0), (2000, 50)])

        driver.update(0, fs, now=0.0)
        driver.update(41, fs, now=0.05)

        assert sink.sent[1] == "L00000I300"

    def test_taking_the_device_back_glides_again(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 0), (40, 100), (80, 0), (2000, 50)])
        driver.update(0, fs, now=0.0)
        driver.update(41, fs, now=0.31)

        driver.reset()
        driver.update(41, fs, now=0.32)

        assert sink.sent[-1] == "L00000I300"


class TestLeadInPark:
    def _lead_in_fs(self):
        return Funscript(actions=[(0, 50), (60000, 0), (60300, 100), (60600, 0)])

    def test_the_handed_over_buffer_rests_at_park_then_rises_to_the_opening(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 50), (60000, 100), (60300, 0), (60600, 100)])

        driver.update(56_000, fs, now=0.0)
        driver.update(59_500, fs, now=1.0)

        assert sink.sent == ["L00000I2000", "L09999I500"]

    def test_before_a_prompt_script_the_target_is_the_opening_action_itself(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(3000, 100), (3300, 0)])

        driver.update(0, fs, now=0.0)
        driver.update(2_500, fs, now=1.0)

        assert sink.sent == ["L00000I2000", "L09999I500"]

    def test_parks_at_closest_position_during_lead_in(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.update(10000, self._lead_in_fs(), now=0.0)

        assert sink.sent == ["L00000I2000"]

    def test_resumes_normal_driving_at_first_real_event(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = self._lead_in_fs()

        driver.update(10000, fs, now=0.0)
        driver.update(60000, fs, now=1.0)

        assert sink.sent == ["L00000I2000", "L09999I300"]

    def test_park_is_rate_limited_but_resends(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = self._lead_in_fs()

        driver.update(10000, fs, now=0.0)
        driver.update(11000, fs, now=0.05)
        driver.update(12000, fs, now=0.15)

        assert sink.sent == ["L00000I2000", "L00000I1850"]


class TestPark:
    def test_a_park_after_scripting_is_the_plan_s_own_settle_which_is_the_brokers_own_park_time(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)
        fs = Funscript(actions=[(0, 100), (200, 0), (400, 100), (600, 0)])

        driver.update(100, fs, now=0.0)
        driver.update(10_000, fs, now=1.0)

        assert sink.sent[-1] == "L00000I500"

    def test_sends_closest_position(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.park(now=0.0)

        assert sink.sent == ["L00000I2000"]

    def test_edge_gated_then_resends_only_the_time_left_since_a_full_interval_resent_restarts_the_osr2_s_glide_and_lands_it_early(self):
        sink = FakeSink()
        driver = FunscriptTCodeDriver(sink)

        driver.park(now=0.0)
        driver.park(now=0.05)
        driver.park(now=0.15)

        assert sink.sent == ["L00000I2000", "L00000I1850"]


class TestDepthAtSpeed:
    def _fast_fs(self):
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
