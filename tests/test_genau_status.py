from __future__ import annotations

from pathlib import Path

from funestra import genau_status
from funestra.cruise_control import CruiseControlState
from funestra.flick_advance import FlickAdvanceState
from funestra.genau_status import build_status_text, write_status_file
from funestra.learned_motion import LearnedMotionState
from funestra.robot_hand import RobotHandState, WaveformShape


def test_build_status_text_defaults():
    ds = RobotHandState()
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "cruise=0" in text
    assert "shape=sine" in text
    assert "amp_at_max=" in text
    assert "spd_at_min=" in text


def test_build_status_text_cruise_active():
    ds = RobotHandState()
    cs = CruiseControlState(active=True)

    text = build_status_text(ds, cs)

    assert "cruise=1" in text


def test_build_status_text_shape():
    ds = RobotHandState(shape=WaveformShape.TRIANGLE)
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "shape=triangle" in text


def test_build_status_text_amp_at_max():
    ds = RobotHandState(amplitude=100)
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "amp_at_max=1" in text
    assert "amp_at_min=0" in text


def test_build_status_text_amp_at_min():
    ds = RobotHandState(amplitude=0)
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "amp_at_max=0" in text
    assert "amp_at_min=1" in text


def test_build_status_text_spd_at_max():
    ds = RobotHandState(speed=100)
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "spd_at_max=1" in text
    assert "spd_at_min=0" in text


def test_build_status_text_spd_at_min():
    ds = RobotHandState(speed=5)
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "spd_at_max=0" in text
    assert "spd_at_min=1" in text


def test_build_status_text_ctr_at_limits_given_amplitude():
    # amplitude=100 → half=50 → center clamped to [50, 50]
    ds = RobotHandState(amplitude=100, center=50, intended_center=50)
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "ctr_at_max=1" in text
    assert "ctr_at_min=1" in text


def test_build_status_text_ctr_not_at_limits():
    # amplitude=20 → half=10 → center range [10, 90]
    ds = RobotHandState(amplitude=20, center=50, intended_center=50)
    cs = CruiseControlState()

    text = build_status_text(ds, cs)

    assert "ctr_at_max=0" in text
    assert "ctr_at_min=0" in text


def test_write_status_file_creates_file(tmp_path: Path):
    path = tmp_path / "genau_status.txt"

    write_status_file(path, build_status_text(RobotHandState(), CruiseControlState()))

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "cruise=0" in text
    assert "shape=sine" in text


def test_write_status_file_skips_when_unchanged(tmp_path: Path):
    text = build_status_text(RobotHandState(), CruiseControlState())
    path = tmp_path / "genau_status.txt"

    assert write_status_file(path, text) is True  # first write
    written_at = path.stat().st_mtime_ns

    assert write_status_file(path, text) is False  # no change
    assert path.stat().st_mtime_ns == written_at, "the file was rewritten anyway"


def test_build_status_text_reports_the_flick_held_by_default():
    text = build_status_text(RobotHandState(), CruiseControlState())

    assert "locked=1" in text


def test_build_status_text_reports_a_released_flick():
    aa = FlickAdvanceState(locked=False)

    text = build_status_text(RobotHandState(), CruiseControlState(), flick_advance=aa)

    assert "locked=0" in text


def test_build_status_text_names_the_flick_on_screen():
    """Which flick is up, so a reopened session can be pointed back at it."""
    text = build_status_text(
        RobotHandState(), CruiseControlState(), flick=Path("C:/flicks/alpha.mp4"),
    )

    assert "flick=C:\\flicks\\alpha.mp4" in text or "flick=C:/flicks/alpha.mp4" in text


def test_build_status_text_names_no_flick_before_one_is_up():
    """Genau publishes from its refresh loop, which can run a tick before the
    first flick is decoded; an empty value reads as nothing to come back to."""
    text = build_status_text(RobotHandState(), CruiseControlState())

    assert "flick=\n" in text


def test_build_status_text_says_whether_the_learned_motion_has_the_hand():
    assert "learned=0" in build_status_text(RobotHandState(), CruiseControlState())
    assert "learned=0" in build_status_text(
        RobotHandState(), CruiseControlState(), learned=LearnedMotionState(active=False))
    assert "learned=1" in build_status_text(
        RobotHandState(), CruiseControlState(), learned=LearnedMotionState(active=True))


def test_build_status_text_says_whether_the_flick_on_screen_is_flipped():
    assert "flipped=0" in build_status_text(RobotHandState(), CruiseControlState())
    assert "flipped=1" in build_status_text(RobotHandState(), CruiseControlState(), flipped=True)


def test_build_status_text_says_whether_the_flick_on_screen_is_portrait():
    assert "portrait=1\n" in build_status_text(RobotHandState(), CruiseControlState(), portrait=True)
    assert "portrait=0\n" in build_status_text(RobotHandState(), CruiseControlState(), portrait=False)


def test_build_status_text_leaves_the_shape_empty_until_a_flick_is_up():
    assert "portrait=\n" in build_status_text(RobotHandState(), CruiseControlState())


def test_write_status_file_replaces_the_record_whole_so_a_poller_never_reads_half(
        tmp_path: Path, monkeypatch):
    published = []
    monkeypatch.setattr(genau_status, "publish_whole",
                        lambda path, text: published.append((path, text)) or True)
    path = tmp_path / "genau_status.txt"
    text = build_status_text(RobotHandState(), CruiseControlState())

    assert write_status_file(path, text) is True
    assert published == [(path, text)]
def test_whether_the_hand_is_moving_is_said_for_a_genau_taking_its_place():
    """A Genau arriving beside this one has to know whether to be moving when
    it takes the room, and nothing else it can read says so."""
    assert "playing=1" in build_status_text(RobotHandState(playing=True), CruiseControlState())
    assert "playing=0" in build_status_text(RobotHandState(playing=False), CruiseControlState())


def test_the_seconds_a_flick_holds_the_screen_are_said_too():
    advance = FlickAdvanceState(interval=25)
    assert "interval=25" in build_status_text(
        RobotHandState(), CruiseControlState(), flick_advance=advance)


def test_the_status_says_the_max_intensity_the_hand_is_held_to():
    text = build_status_text(RobotHandState(max_intensity=35), CruiseControlState())

    assert "max_intensity=35\n" in text
