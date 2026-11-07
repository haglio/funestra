from __future__ import annotations

from import_checks import packages_named_in_imports

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
    controls = _Controls()

    assert look_up("play_file C:/Videos/My Clip.mp4", VERBS, controls) is True

    assert controls.opened == ["C:/Videos/My Clip.mp4"]


def test_surrounding_space_and_a_bare_line_are_no_command():
    controls = _Controls()

    assert look_up("  next  ", VERBS, controls) is True
    assert look_up("", VERBS, controls) is False
    assert look_up("   ", VERBS, controls) is False

    assert controls.steps == 1


def test_a_control_this_build_did_not_wire_runs_nothing():
    controls = _Controls()
    unwired = bind((
        Control("playlist_position", verbs=(Verb("NEXT", _step),), needs=("deck",)),
    ))
    controls.deck = None

    assert look_up("NEXT", unwired, controls) is False
    assert controls.steps == 0


def test_a_value_on_a_verb_that_takes_none_runs_nothing():
    controls = _Controls()

    assert look_up("NEXT now", VERBS, controls) is False
    assert controls.steps == 0


def test_no_value_on_a_verb_that_wants_one_runs_nothing():
    controls = _Controls()

    assert look_up("PLAY_FILE", VERBS, controls) is False
    assert controls.opened == []


def test_it_says_only_what_a_control_s_record_looks_like_and_holds_no_app_s_controls_so_it_imports_nothing_of_funestra():
    assert packages_named_in_imports("funestra.control_registry") <= {"__future__", "collections", "dataclasses", "typing"}
