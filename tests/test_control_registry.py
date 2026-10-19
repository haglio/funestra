"""Looking one command line up in a registry, whatever the line carries."""
from __future__ import annotations

from funestra.control_registry import Control, Verb, bind, look_up


class _Controls:
    def __init__(self) -> None:
        self.opened: list[str] = []
        self.steps = 0


def _open(controls: _Controls, value: str) -> bool:
    controls.opened.append(value)
    return True


def _step(controls: _Controls, _value: str) -> bool:
    controls.steps += 1
    return True


VERBS = bind((
    Control("playing_file", verbs=(Verb("PLAY_FILE", _open, takes_a_value=True),)),
    Control("playlist_position", verbs=(Verb("NEXT", _step),)),
))


def test_the_keyword_is_folded_and_the_value_is_left_as_it_came():
    """A path is the one value in this family whose case is load-bearing, and
    every Funestra's ``PLAY_FILE`` carries one: the Main Funestra kept a lookup of
    its own for exactly this, because the shared one folded the whole line."""
    controls = _Controls()

    assert look_up("play_file C:/Videos/My Clip.mp4", VERBS, controls) is True

    assert controls.opened == ["C:/Videos/My Clip.mp4"]


def test_surrounding_space_and_a_bare_line_are_no_command():
    controls = _Controls()

    assert look_up("  next  ", VERBS, controls) is True
    assert look_up("", VERBS, controls) is False
    assert look_up("   ", VERBS, controls) is False

    assert controls.steps == 1


def test_a_value_said_to_a_verb_that_takes_none_is_refused_and_a_missing_one_too():
    controls = _Controls()

    assert look_up("NEXT 5", VERBS, controls) is False
    assert look_up("PLAY_FILE", VERBS, controls) is False

    assert (controls.steps, controls.opened) == (0, [])


def test_a_verb_whose_value_may_be_left_off_answers_with_one_and_without():
    controls = _Controls()
    verbs = bind((Control("lock", verbs=(Verb("LOCK_ON", _open, value_is_optional=True),)),))

    assert look_up("LOCK_ON", verbs, controls) is True
    assert look_up("LOCK_ON C:/Videos/My Clip.mp4", verbs, controls) is True

    assert controls.opened == ["", "C:/Videos/My Clip.mp4"]
