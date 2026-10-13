"""The closed sets a Funestra and Fun Time agree on, each as the words on the wire."""
from __future__ import annotations

import json

import pytest
from app_support.osr2_device import Osr2Mode

from funestra.modes import (
    LengthMode,
    LoopState,
    MainMode,
    NoticeLevel,
    Osr2State,
    SatellitesMode,
    read_mode,
)

_WIRE_WORDS = {
    MainMode: {"kino", "genau"},
    SatellitesMode: {"kino", "origenerator"},
    LoopState: {"normal", "recording", "looping"},
    Osr2State: {"off", "auto", "funscript", "robot_hand"},
    LengthMode: {"mixed", "clips", "full", "none"},
    NoticeLevel: {"warning", "notice", "favorite"},
}


@pytest.mark.parametrize("enum", list(_WIRE_WORDS))
def test_each_entry_is_spelled_as_its_word_on_the_wire(enum):
    assert {entry.value for entry in enum} == _WIRE_WORDS[enum]


@pytest.mark.parametrize("enum", [MainMode, SatellitesMode])
def test_a_branch_from_before_the_rename_still_finds_kino_under_its_old_name(enum):
    assert enum.VIDEO is enum.KINO


def test_a_branch_from_before_the_rename_still_finds_clips_under_its_old_name():
    assert LengthMode.SHORTS is LengthMode.CLIPS


def test_a_length_mode_written_before_the_rename_reads_as_clips():
    assert read_mode(LengthMode, "shorts", None) is LengthMode.CLIPS


@pytest.mark.parametrize("enum", list(_WIRE_WORDS))
def test_an_entry_is_its_wire_word_wherever_a_string_is_wanted(enum):
    """A comparison against the bare word still holds, and a JSON writer that
    is handed the entry writes the word and nothing else."""
    for entry in enum:
        assert entry == entry.value
        assert json.dumps(entry) == json.dumps(entry.value)


def test_read_mode_gives_the_entry_a_known_word_names():
    assert read_mode(MainMode, "genau", MainMode.KINO) is MainMode.GENAU
    assert read_mode(LoopState, "recording", LoopState.NORMAL) is LoopState.RECORDING


@pytest.mark.parametrize("raw", ["", "hybrid", None, 3, "KINO", "video"])
def test_read_mode_answers_the_default_for_a_word_it_does_not_know(raw):
    """A Funestra that raised on a mode it did not know would be worse than one
    that ignored it: a file from a newer or an older session must leave the
    Funestra drawing, in the state the default names."""
    assert read_mode(MainMode, raw, MainMode.KINO) is MainMode.KINO


def test_read_mode_answers_none_for_a_reader_whose_default_is_no_mode_at_all():
    """The length buttons are drawn only for a Funestra that names a length mode,
    so its readers fall back on None rather than on an entry."""
    assert read_mode(LengthMode, "", None) is None
    assert read_mode(LengthMode, "every", None) is None
    assert read_mode(LengthMode, "clips", None) is LengthMode.CLIPS


def test_read_mode_hands_an_entry_straight_back():
    assert read_mode(SatellitesMode, SatellitesMode.ORIGENERATOR, SatellitesMode.KINO) is (
        SatellitesMode.ORIGENERATOR)


class TestWhatHasTheOsr2:
    """The OSR2 line's word, from what the device reads as and whether the
    funscript in front is driving: every app badges it the same way."""

    @pytest.mark.parametrize("funscript_driving", [False, True])
    def test_a_switched_off_device_is_off_whatever_would_drive_it(self, funscript_driving):
        assert Osr2State.of(Osr2Mode.OFF, funscript_driving=funscript_driving) is Osr2State.OFF

    @pytest.mark.parametrize("funscript_driving", [False, True])
    def test_one_running_its_own_auto_mode_is_auto_whatever_would_drive_it(self, funscript_driving):
        assert Osr2State.of(Osr2Mode.AUTO, funscript_driving=funscript_driving) is Osr2State.AUTO

    def test_one_taking_commands_is_the_funscripts_while_one_drives(self):
        assert Osr2State.of(Osr2Mode.CONTROLLED, funscript_driving=True) is Osr2State.FUNSCRIPT

    def test_and_the_robot_hands_otherwise(self):
        assert Osr2State.of(Osr2Mode.CONTROLLED, funscript_driving=False) is Osr2State.ROBOT_HAND
