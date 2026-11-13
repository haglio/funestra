from __future__ import annotations

from funestra_fakes import FakeTCode

from funestra.funscript import Funscript
from funestra.robot_hand import FULL_INTENSITY
from funestra.scripted_device import REWIND_MS, ScriptedDevice

SCRIPT = Funscript(actions=[(0, 0), (1000, 100)])


def test_a_rewind_is_a_jump_back_further_than_a_frame_could_slip():
    assert REWIND_MS == 50


class TestWhileEnabled:
    def test_drives_the_script_at_the_playhead_with_the_rate_and_the_ceiling(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)
        device.set_max_intensity(60)

        device.drive(1234.6, SCRIPT, speed=1.5)

        assert tcode.updates == [(1234, SCRIPT, 1.5)]
        assert tcode.max_intensities == [60]

    def test_parks_the_device_where_the_item_has_no_script(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)

        device.drive(1234.0, None, speed=1.0)

        assert tcode.updates == []
        assert tcode.parks == 1

    def test_taking_over_resets_the_wire(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)

        device.take_over()

        assert tcode.resets == 1


class TestWhileDisabled:
    def test_neither_drives_nor_parks(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode, enabled=False)

        device.drive(100.0, SCRIPT, speed=1.0)
        device.drive(100.0, None, speed=1.0)

        assert (tcode.updates, tcode.parks) == ([], 0)

    def test_being_enabled_takes_the_device_over_once(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode, enabled=False)

        device.set_enabled(True)
        device.set_enabled(True)

        assert tcode.resets == 1
        device.drive(100.0, SCRIPT, speed=1.0)
        assert len(tcode.updates) == 1


class TestTheCeiling:
    def test_opens_at_full(self):
        assert ScriptedDevice(FakeTCode()).max_intensity == FULL_INTENSITY

    def test_is_held_between_nothing_and_full(self):
        device = ScriptedDevice(FakeTCode())

        device.set_max_intensity(FULL_INTENSITY + 40)
        assert device.max_intensity == FULL_INTENSITY
        device.set_max_intensity(-5)
        assert device.max_intensity == 0


class TestWithNoWire:
    def test_every_move_is_taken_quietly(self):
        device = ScriptedDevice(None)

        device.drive(100.0, SCRIPT, speed=1.0)
        device.drive(100.0, None, speed=1.0)
        device.take_over()
        device.close()

    def test_closing_closes_the_wire_it_has(self):
        tcode = FakeTCode()

        ScriptedDevice(tcode).close()

        assert tcode.closed is True


def test_a_device_switched_on_wants_the_osr2_and_switched_off_lets_it_go():
    tcode = FakeTCode()
    device = ScriptedDevice(tcode, enabled=False)

    device.set_enabled(True)
    device.set_enabled(False)

    assert tcode.wanted == [False, True, False]


class TestFollowingThePlayhead:
    def test_each_step_of_the_playhead_drives_the_script_there(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)

        device.follow(100.0, SCRIPT, speed=1.0)
        device.follow(140.0, SCRIPT, speed=1.0)

        assert [at for at, _script, _speed in tcode.updates] == [100, 140]
        assert tcode.resets == 0

    def test_a_playhead_that_jumps_back_takes_the_device_over_before_driving_it(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)
        device.follow(1000.0, SCRIPT, speed=1.0)

        device.follow(1000.0 - REWIND_MS - 1, SCRIPT, speed=1.0)

        assert tcode.resets == 1

    def test_a_frame_s_slip_backward_is_no_rewind(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)
        device.follow(1000.0, SCRIPT, speed=1.0)

        device.follow(1000.0 - REWIND_MS, SCRIPT, speed=1.0)

        assert tcode.resets == 0

    def test_a_roll_onto_the_next_item_is_not_taken_for_a_rewind(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)
        device.follow(1000.0, SCRIPT, speed=1.0)

        device.follow(0.0, SCRIPT, speed=1.0, rolled=True)

        assert tcode.resets == 0

    def test_starting_an_item_takes_the_device_over_and_forgets_where_the_last_one_was(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)
        device.follow(1000.0, SCRIPT, speed=1.0)

        device.start_an_item()
        device.follow(0.0, SCRIPT, speed=1.0)

        assert tcode.resets == 1

    def test_after_a_resume_nothing_is_sent_until_the_playhead_has_moved(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)

        device.resume_at(500.0)
        device.follow(500.0, SCRIPT, speed=1.0)
        assert tcode.updates == []

        device.follow(520.0, SCRIPT, speed=1.0)
        device.follow(520.0, SCRIPT, speed=1.0)

        assert [at for at, _script, _speed in tcode.updates] == [520, 520]
        assert tcode.resets == 1

    def test_an_image_has_no_playhead_to_wait_for_so_a_resume_over_one_drives_at_once(self):
        tcode = FakeTCode()
        device = ScriptedDevice(tcode)

        device.resume_at(0.0)
        device.follow(0.0, SCRIPT, speed=1.0, over_an_image=True)

        assert len(tcode.updates) == 1
