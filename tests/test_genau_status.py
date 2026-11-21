from __future__ import annotations

from pathlib import Path

from funestra import genau_status
from funestra.flick_advance import FlickAdvanceState
from funestra.genau_status import FlickOnScreen, StatusFile, build_status_text
from funestra.learned_motion import LearnedMotionState
from funestra.robot_hand import RobotHandState, WaveformShape


def test_build_status_text_defaults():
    ds = RobotHandState()

    text = build_status_text(ds)

    assert "shape=sine" in text
    assert "amp_at_max=" in text
    assert "spd_at_min=" in text


def test_build_status_text_shape():
    ds = RobotHandState(shape=WaveformShape.TRIANGLE)

    text = build_status_text(ds)

    assert "shape=triangle" in text


def test_build_status_text_amp_at_max():
    ds = RobotHandState(amplitude=100)

    text = build_status_text(ds)

    assert "amp_at_max=1" in text
    assert "amp_at_min=0" in text


def test_build_status_text_amp_at_min():
    ds = RobotHandState(amplitude=0)

    text = build_status_text(ds)

    assert "amp_at_max=0" in text
    assert "amp_at_min=1" in text


def test_build_status_text_spd_at_max():
    ds = RobotHandState(speed=100)

    text = build_status_text(ds)

    assert "spd_at_max=1" in text
    assert "spd_at_min=0" in text


def test_build_status_text_spd_at_min():
    ds = RobotHandState(speed=5)

    text = build_status_text(ds)

    assert "spd_at_max=0" in text
    assert "spd_at_min=1" in text


def test_build_status_text_ctr_at_limits_given_amplitude():
    ds = RobotHandState(amplitude=100, center=50, intended_center=50)

    text = build_status_text(ds)

    assert "ctr_at_max=1" in text
    assert "ctr_at_min=1" in text


def test_build_status_text_ctr_not_at_limits():
    ds = RobotHandState(amplitude=20, center=50, intended_center=50)

    text = build_status_text(ds)

    assert "ctr_at_max=0" in text
    assert "ctr_at_min=0" in text


def test_the_status_file_creates_file(tmp_path: Path):
    path = tmp_path / "genau_status.txt"

    StatusFile(path).write(build_status_text(RobotHandState()))

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "shape=sine" in text


def test_the_status_file_skips_when_unchanged(tmp_path: Path):
    text = build_status_text(RobotHandState())
    path = tmp_path / "genau_status.txt"
    status = StatusFile(path)

    assert status.write(text) is True
    written_at = path.stat().st_mtime_ns

    assert status.write(text) is False
    assert path.stat().st_mtime_ns == written_at, "the file was rewritten anyway"


def test_build_status_text_reports_the_flick_held_by_default():
    text = build_status_text(RobotHandState())

    assert "locked=1" in text


def test_build_status_text_reports_a_released_flick():
    aa = FlickAdvanceState(locked=False)

    text = build_status_text(RobotHandState(), flick_advance=aa)

    assert "locked=0" in text


def test_build_status_text_names_the_flick_on_screen_so_a_reopened_session_can_go_back_to_it():
    text = build_status_text(
        RobotHandState(), on_screen=FlickOnScreen(Path("C:/flicks/alpha.mp4")),
    )

    assert "flick=C:\\flicks\\alpha.mp4" in text or "flick=C:/flicks/alpha.mp4" in text


def test_build_status_text_names_no_flick_before_one_is_up():
    text = build_status_text(RobotHandState())

    assert "flick=\n" in text


def test_build_status_text_says_whether_the_robot_hand_is_off():
    assert "robot_hand_off=0" in build_status_text(RobotHandState())
    assert "robot_hand_off=1" in build_status_text(RobotHandState(off=True))


def test_build_status_text_says_whether_the_learned_motion_has_the_hand():
    assert "learned=0" in build_status_text(RobotHandState())
    assert "learned=0" in build_status_text(
        RobotHandState(), learned=LearnedMotionState(active=False))
    assert "learned=1" in build_status_text(
        RobotHandState(), learned=LearnedMotionState(active=True))


def test_build_status_text_says_whether_the_flick_on_screen_is_flipped():
    assert "flipped=0" in build_status_text(RobotHandState())
    assert "flipped=1" in build_status_text(RobotHandState(), on_screen=FlickOnScreen(flipped=True))


def test_build_status_text_says_whether_the_flick_on_screen_is_portrait():
    assert "portrait=1\n" in build_status_text(RobotHandState(), on_screen=FlickOnScreen(portrait=True))
    assert "portrait=0\n" in build_status_text(RobotHandState(), on_screen=FlickOnScreen(portrait=False))


def test_build_status_text_leaves_the_shape_empty_until_a_flick_is_up():
    assert "portrait=\n" in build_status_text(RobotHandState())


def test_the_status_file_replaces_the_record_whole_so_a_poller_never_reads_half(
        tmp_path: Path, monkeypatch):
    published = []
    monkeypatch.setattr(genau_status, "publish_whole",
                        lambda path, text: published.append((path, text)) or True)
    path = tmp_path / "genau_status.txt"
    text = build_status_text(RobotHandState())

    assert StatusFile(path).write(text) is True
    assert published == [(path, text)]


def test_whether_the_hand_is_moving_is_said_for_a_genau_taking_its_place():
    assert "playing=1" in build_status_text(RobotHandState(playing=True))
    assert "playing=0" in build_status_text(RobotHandState(playing=False))


def test_the_seconds_a_flick_holds_the_screen_are_said_too():
    advance = FlickAdvanceState(interval=25)
    assert "interval=25" in build_status_text(
        RobotHandState(), flick_advance=advance)


def test_the_status_says_the_max_intensity_the_hand_is_held_to():
    text = build_status_text(RobotHandState(max_intensity=35))

    assert "max_intensity=35\n" in text


def test_a_status_written_many_times_over_is_never_read_back_and_written_once_per_change(
        tmp_path: Path, monkeypatch):
    published = []
    monkeypatch.setattr(genau_status, "publish_whole",
                        lambda path, text: published.append(text) or True)
    reads = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, **kw: reads.append(self) or real(self, **kw))
    status = StatusFile(tmp_path / "genau_status.txt")
    still, moving = (build_status_text(RobotHandState(playing=playing)) for playing in (False, True))

    for text in [still] * 60 + [moving] * 60:
        status.write(text)

    assert reads == []
    assert published == [still, moving]


def test_a_status_the_disk_refused_is_written_again_at_the_next_tick(tmp_path: Path, monkeypatch):
    answers = [False, True]
    published = []
    monkeypatch.setattr(genau_status, "publish_whole",
                        lambda path, text: published.append(text) or answers.pop(0))
    status = StatusFile(tmp_path / "genau_status.txt")
    text = build_status_text(RobotHandState())

    assert [status.write(text), status.write(text), status.write(text)] == [False, True, False]
    assert published == [text, text]


def _read_back(text: str) -> genau_status.GenauStatus:
    return genau_status.genau_status_from(
        dict(line.split("=", 1) for line in text.splitlines() if "=" in line))


def test_what_genau_writes_reads_back_as_the_flick_on_screen_its_lock_flip_and_seconds():
    advance = FlickAdvanceState(locked=False, interval=12)
    on_screen = FlickOnScreen(path=Path("C:/made/up/one.mp4"), flipped=True, portrait=True,
                              up_at=3.5)

    heard = _read_back(build_status_text(RobotHandState(off=True), flick_advance=advance,
                                         learned=LearnedMotionState(active=True),
                                         on_screen=on_screen))

    assert (heard.learned_active, heard.robot_hand_off) == (True, True)
    assert (heard.flick, heard.locked, heard.flipped, heard.interval, heard.portrait,
            heard.up_at) == (str(Path("C:/made/up/one.mp4")), False, True, 12, True, 3.5)


def test_nothing_written_yet_reads_as_genau_as_it_opens():
    heard = genau_status.genau_status_from({})

    assert heard == genau_status.GenauStatus()
    assert (heard.locked, heard.flick, heard.interval) == (
        True, "", FlickAdvanceState().interval)
