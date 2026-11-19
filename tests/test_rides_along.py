from __future__ import annotations

import json
import os
from pathlib import Path

from funestra_fakes import stamped_long_ago

from funestra import rides_along
from funestra.playlist import PlaylistItem
from funestra.rides_along import RidesAlong

ONE, TWO = Path("one.mp4"), Path("two.mp4")
A_BOX = (0.1, 0.2, 0.3, 0.4)


def _script(tmp_path, name: str, top: int) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"actions": [{"at": 0, "pos": 0}, {"at": 1000, "pos": top}]}),
                    encoding="utf-8")
    return path


def test_a_video_with_nothing_riding_along_has_no_funscript_and_no_points():
    rides = RidesAlong()

    assert (rides.funscript_path(ONE), rides.funscript(ONE), rides.points(ONE)) == (None, None, ())


def test_the_funscript_is_the_first_one_any_of_the_videos_asked_about_has(tmp_path):
    script = _script(tmp_path, "two.funscript", 80)
    rides = RidesAlong({TWO: script})

    assert rides.funscript(ONE, TWO).actions == [(0, 0), (1000, 80)]
    assert rides.funscript_path(TWO) == script


def test_a_funscript_is_read_once_and_stays_held_while_a_neighbors_is_asked_for(tmp_path):
    first, second = _script(tmp_path, "one.funscript", 80), _script(tmp_path, "two.funscript", 60)
    rides = RidesAlong({ONE: first, TWO: second})

    read = rides.funscript(ONE)
    assert rides.funscript(TWO).actions == [(0, 0), (1000, 60)]

    assert rides.funscript(ONE) is read


def test_what_a_video_brings_is_taken_and_what_it_does_not_bring_is_left(tmp_path):
    script = _script(tmp_path, "one.funscript", 80)
    rides = RidesAlong({ONE: script}, {ONE: (A_BOX,)})

    rides.take(ONE, None, ())
    rides.take(TWO, script, [list(A_BOX)])

    assert (rides.funscript_path(ONE), rides.points(ONE)) == (script, (A_BOX,))
    assert (rides.funscript_path(TWO), rides.points(TWO)) == (script, (list(A_BOX),))


def test_it_is_gathered_from_the_items_of_a_playlist(tmp_path):
    script = _script(tmp_path, "one.funscript", 80)

    rides = RidesAlong.of([PlaylistItem(ONE, script), PlaylistItem(TWO, None, (A_BOX,))])

    assert (rides.funscript_path(ONE), rides.funscript_path(TWO)) == (script, None)
    assert (rides.points(ONE), rides.points(TWO)) == ((), (A_BOX,))


def _reads(monkeypatch) -> list[Path]:
    read: list[Path] = []
    real = rides_along.load_funscript
    monkeypatch.setattr(rides_along, "load_funscript", lambda path: read.append(path) or real(path))
    return read


def test_a_funscript_read_under_one_list_is_not_read_again_under_the_next(tmp_path, monkeypatch):
    script = _script(tmp_path, "one.funscript", 80)
    stamped_long_ago(script)
    before = RidesAlong({ONE: script})
    read_before = before.funscript(ONE)
    reads = _reads(monkeypatch)

    after = RidesAlong({ONE: script, TWO: script}, read_before=before)

    assert after.funscript(TWO) is read_before
    assert reads == []


def test_a_funscript_written_again_since_it_was_read_is_read_again_under_the_next_list(
        tmp_path, monkeypatch):
    script = _script(tmp_path, "one.funscript", 80)
    stamped_long_ago(script)
    before = RidesAlong({ONE: script})
    before.funscript(ONE)
    _script(tmp_path, "one.funscript", 55)
    reads = _reads(monkeypatch)

    after = RidesAlong({ONE: script}, read_before=before)

    assert after.funscript(ONE).actions == [(0, 0), (1000, 55)]
    assert reads == [script]


def test_a_funscript_coming_up_is_read_by_whoever_it_is_handed_to_and_asked_for_once(tmp_path):
    script = _script(tmp_path, "two.funscript", 60)
    rides = RidesAlong({TWO: script})
    handed: list[tuple] = []

    def later(work, then) -> None:
        handed.append((work, then))

    while_unread = [rides.funscript_once_read(TWO, later) for _ in range(5)]
    for work, then in handed:
        then(work())

    assert (while_unread, len(handed)) == ([None] * 5, 1)
    assert rides.funscript_once_read(TWO, later).actions == [(0, 0), (1000, 60)]


def test_with_nobody_to_hand_it_to_a_funscript_coming_up_is_read_where_it_is_asked_for(tmp_path):
    rides = RidesAlong({TWO: _script(tmp_path, "two.funscript", 60)})

    assert rides.funscript_once_read(TWO).actions == [(0, 0), (1000, 60)]
    assert rides.funscript_once_read(ONE) is None


def test_a_funscript_read_while_its_stamp_was_too_new_to_tell_writes_apart_is_read_again(
        tmp_path, monkeypatch):
    script = _script(tmp_path, "one.funscript", 80)
    one_stamp = script.stat()
    before = RidesAlong({ONE: script})
    before.funscript(ONE)
    _script(tmp_path, "one.funscript", 55)
    os.utime(script, ns=(one_stamp.st_atime_ns, one_stamp.st_mtime_ns))
    reads = _reads(monkeypatch)

    after = RidesAlong({ONE: script}, read_before=before)

    assert after.funscript(ONE).actions == [(0, 0), (1000, 55)]
    assert reads == [script]
