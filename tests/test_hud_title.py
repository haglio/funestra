from __future__ import annotations

from funestra.hud_title import (
    ENHANCED_LABEL,
    F_MODE_LABEL,
    LATEST_LABEL,
    LOCKED_LABEL,
    SHUFFLE_LABEL,
    UNLOCKED_LABEL,
    HudTitleFacts,
    hud_title,
    looping_label,
)


def test_an_idle_funestra_says_only_whether_it_is_holding_what_is_on_screen():
    assert hud_title(HudTitleFacts(locked=True)) == LOCKED_LABEL
    assert hud_title(HudTitleFacts(locked=False)) == UNLOCKED_LABEL


def test_the_slots_run_from_the_set_being_played_down_to_the_finest_filter():
    assert hud_title(HudTitleFacts(
        playing_set="Looping seeds", locked=True, order="Latest",
        f_mode=True, filters=("alpha",),
    )) == f"Looping seeds · {LOCKED_LABEL} · Latest · {F_MODE_LABEL} · alpha"


def test_a_set_playing_through_drops_unlocked_but_keeps_locked():
    assert hud_title(HudTitleFacts(playing_set="Looping seeds", locked=False)) == "Looping seeds"
    assert hud_title(HudTitleFacts(playing_set="Looping seeds", locked=True)) == (
        f"Looping seeds · {LOCKED_LABEL}")


def test_an_empty_slot_takes_no_room_and_leaves_no_separator():
    assert hud_title(HudTitleFacts(locked=False, order=SHUFFLE_LABEL)) == (
        f"{UNLOCKED_LABEL} · Shuffle")
    assert hud_title(HudTitleFacts(locked=False, filters=("beta",))) == f"{UNLOCKED_LABEL} · beta"


def test_the_two_browse_orders_are_named_once_for_every_funestra():
    assert (LATEST_LABEL, SHUFFLE_LABEL) == ("Latest", "Shuffle")


def test_the_enhanced_narrowing_has_a_slot_of_its_own_after_f_mode_named_like_every_filter_for_what_it_keeps():
    assert hud_title(HudTitleFacts(locked=False, order=SHUFFLE_LABEL, enhanced=True)) == (
        f"{UNLOCKED_LABEL} · Shuffle · {ENHANCED_LABEL}")
    assert hud_title(HudTitleFacts(
        locked=True, f_mode=True, enhanced=True, filters=("alpha",))) == (
        f"{LOCKED_LABEL} · {F_MODE_LABEL} · {ENHANCED_LABEL} · alpha")
    assert hud_title(HudTitleFacts(locked=True, enhanced=False)) == LOCKED_LABEL


def test_a_loop_on_an_axis_is_named_looping_that_axis_in_the_plural():
    assert looping_label("seed") == "Looping seeds"
    assert looping_label("action") == "Looping actions"
