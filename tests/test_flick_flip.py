from __future__ import annotations

import json
from pathlib import Path

from funestra import flick_flip
from funestra.flick_flip import FlickFlip


def _metadata_root(tmp_path: Path) -> Path:
    return tmp_path / "videos" / "metadata"


def _flick(tmp_path: Path, name: str = "scene one.mp4") -> Path:
    folder = tmp_path / "videos" / "genau" / "flicks"
    folder.mkdir(parents=True, exist_ok=True)
    flick = folder / name
    flick.touch()
    return flick


def _record(tmp_path: Path, name: str = "scene one") -> Path:
    return _metadata_root(tmp_path) / "genau" / "flicks" / f"{name}.json"


def _flip(tmp_path: Path) -> FlickFlip:
    return FlickFlip(_metadata_root(tmp_path))


def test_a_flick_nobody_flipped_is_shown_as_it_is(tmp_path):
    flip = _flip(tmp_path)

    flip.follow(_flick(tmp_path))

    assert flip.on is False


def test_flipping_the_flick_on_screen_turns_it_over(tmp_path):
    flip = _flip(tmp_path)
    flip.follow(_flick(tmp_path))

    flip.toggle()

    assert flip.on is True


def test_a_flipped_flick_is_still_flipped_in_the_next_session(tmp_path):
    flick = _flick(tmp_path)
    this_session = _flip(tmp_path)
    this_session.follow(flick)
    this_session.toggle()

    next_session = _flip(tmp_path)
    next_session.follow(flick)

    assert next_session.on is True


def test_flipping_it_again_puts_it_back_for_good(tmp_path):
    flick = _flick(tmp_path)
    this_session = _flip(tmp_path)
    this_session.follow(flick)
    this_session.toggle()
    this_session.toggle()

    next_session = _flip(tmp_path)
    next_session.follow(flick)

    assert (this_session.on, next_session.on) == (False, False)


def test_the_flip_is_kept_in_the_flicks_own_record_beside_everything_else_known_about_it(tmp_path):
    record = _record(tmp_path)
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"video": {"type": "genau_flick"}}), encoding="utf-8")
    flip = _flip(tmp_path)
    flip.follow(_flick(tmp_path))

    flip.toggle()

    assert json.loads(record.read_text(encoding="utf-8")) == {
        "video": {"type": "genau_flick"}, "genau": {"flipped": True}}


def test_a_flick_turned_back_leaves_no_trace_of_the_flip_in_its_record(tmp_path):
    record = _record(tmp_path)
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"video": {"type": "genau_flick"}}), encoding="utf-8")
    flip = _flip(tmp_path)
    flip.follow(_flick(tmp_path))

    flip.toggle()
    flip.toggle()

    assert json.loads(record.read_text(encoding="utf-8")) == {"video": {"type": "genau_flick"}}


def test_the_flip_belongs_to_the_one_flick(tmp_path):
    flipped, other = _flick(tmp_path, "scene one.mp4"), _flick(tmp_path, "scene two.mp4")
    flip = _flip(tmp_path)
    flip.follow(flipped)
    flip.toggle()

    flip.follow(other)
    shown_after_moving_on = flip.on
    flip.follow(flipped)

    assert (shown_after_moving_on, flip.on) == (False, True)


def test_a_toggle_turns_over_what_the_record_says_now(tmp_path):
    flick = _flick(tmp_path)
    headset, desktop = _flip(tmp_path), _flip(tmp_path)
    headset.follow(flick)
    desktop.follow(flick)
    headset.toggle()

    desktop.toggle()

    later = _flip(tmp_path)
    later.follow(flick)
    assert (desktop.on, later.on) == (False, False)


def test_the_record_is_read_when_the_flick_changes_not_every_frame(tmp_path, monkeypatch):
    reads: list[Path] = []
    read = flick_flip.read_json
    monkeypatch.setattr(flick_flip, "read_json", lambda record: reads.append(record) or read(record))
    flick = _flick(tmp_path)
    flip = _flip(tmp_path)

    for _frame in range(120):
        flip.follow(flick)

    assert len(reads) == 1


def test_a_flip_that_could_not_be_saved_still_shows_and_says_so(tmp_path, monkeypatch, caplog):
    def refused(_record, _mutate):
        raise TimeoutError("held")

    monkeypatch.setattr(flick_flip, "locked_update", refused)
    flip = _flip(tmp_path)
    flip.follow(_flick(tmp_path))

    flip.toggle()

    assert flip.on is True
    assert "scene one.mp4" in caplog.text


def test_a_record_that_cannot_be_read_is_never_written_over(tmp_path, caplog):
    record = _record(tmp_path)
    record.parent.mkdir(parents=True)
    record.write_text("{not json", encoding="utf-8")
    flip = _flip(tmp_path)
    flip.follow(_flick(tmp_path))

    flip.toggle()

    assert (flip.on, record.read_text(encoding="utf-8")) == (True, "{not json")
    assert "scene one.mp4" in caplog.text


def test_a_genau_told_of_no_metadata_folder_flips_for_the_session_and_says_it_cannot_keep_it(
        tmp_path, caplog):
    flip = FlickFlip()
    flip.follow(_flick(tmp_path))

    flip.toggle()

    assert flip.on is True
    assert not (tmp_path / "videos" / "metadata").exists()
    assert "scene one.mp4" in caplog.text


def test_a_flick_outside_the_library_flips_for_the_session_and_says_it_cannot_keep_it(
        tmp_path, caplog):
    outside = tmp_path / "elsewhere" / "scene one.mp4"
    outside.parent.mkdir()
    outside.touch()
    flip = FlickFlip(tmp_path / "library" / "videos" / "metadata")
    flip.follow(outside)

    flip.toggle()

    assert flip.on is True
    assert "scene one.mp4" in caplog.text


def test_with_no_flick_on_screen_there_is_nothing_to_flip(tmp_path):
    flip = _flip(tmp_path)

    flip.toggle()

    assert flip.on is False
    assert list(tmp_path.iterdir()) == []


def test_a_flipped_flick_is_shown_half_a_loop_over(tmp_path):
    flip = _flip(tmp_path)
    flip.follow(_flick(tmp_path))
    as_it_is = flip.applied_to(0.25)
    flip.toggle()

    assert (as_it_is, flip.applied_to(0.25), flip.applied_to(0.75)) == (0.25, 0.75, 0.25)
