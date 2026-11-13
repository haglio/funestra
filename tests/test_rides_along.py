from __future__ import annotations

import json
from pathlib import Path

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


def test_a_funscript_is_read_once_and_again_only_when_another_is_asked_for(tmp_path):
    first, second = _script(tmp_path, "one.funscript", 80), _script(tmp_path, "two.funscript", 60)
    rides = RidesAlong({ONE: first, TWO: second})

    read = rides.funscript(ONE)

    assert rides.funscript(ONE) is read
    assert rides.funscript(TWO).actions == [(0, 0), (1000, 60)]


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
