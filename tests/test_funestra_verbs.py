from __future__ import annotations

from pathlib import Path

import pytest

from funestra import funestra_verbs
from funestra.playlist import PlaylistItem, item_from_line


def _spellings() -> dict[str, str]:
    return {name: value for name, value in vars(funestra_verbs).items()
            if name.isupper() and not name.startswith("_") and isinstance(value, str)}


def test_every_verb_is_spelled_as_a_registry_looks_it_up_upper_cased_and_split_at_the_first_space():
    for name, spelling in _spellings().items():
        assert spelling == name, f"{name} is spelled {spelling!r}"
        assert spelling == spelling.upper()
        assert " " not in spelling


def test_no_two_verbs_share_a_spelling():
    spellings = list(_spellings().values())
    assert len(spellings) == len(set(spellings))


@pytest.mark.parametrize(("spell", "verb"), [
    (funestra_verbs.play_file, funestra_verbs.PLAY_FILE),
    (funestra_verbs.play_next, funestra_verbs.PLAY_NEXT),
])
def test_a_verb_naming_an_item_carries_it_as_the_playlist_would(spell, verb):
    item = PlaylistItem(Path("C:/vids/My Clip.mp4"), Path("C:/scripts/My Clip.funscript"))

    line = spell(item)

    keyword, _, value = line.partition(" ")
    assert keyword == verb
    assert item_from_line(value) == item


def test_a_pace_is_read_as_the_seconds_it_names():
    assert funestra_verbs.pace_seconds("2.5") == 2.5
    assert funestra_verbs.pace_seconds("0") == 0.0


@pytest.mark.parametrize("value", ["-1", "soon", "", "inf", "nan"])
def test_a_value_that_names_no_pace_is_refused(value):
    assert funestra_verbs.pace_seconds(value) is None


class TestAStepToAnotherVersionOfTheItemOnScreen:
    def test_a_step_forward_carries_the_family_in_the_sources_order_the_whole_family_so_the_funestra_steps_from_whichever_file_it_has_up(self):
        versions = [Path("C:/vids/clip_topaz.mp4"), Path("C:/vids/clip.mp4")]

        line = funestra_verbs.step_version(1, versions)

        keyword, _, value = line.partition(" ")
        assert keyword == funestra_verbs.NEXT_VERSION
        assert funestra_verbs.version_files(value) == versions

    def test_a_step_back_is_the_other_verb(self):
        line = funestra_verbs.step_version(-1, [Path("C:/vids/clip_topaz.mp4"), Path("C:/vids/clip.mp4")])

        assert line.partition(" ")[0] == funestra_verbs.PREV_VERSION

    def test_a_value_naming_nothing_carries_no_versions(self):
        assert funestra_verbs.version_files("") == []
