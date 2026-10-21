"""The one title every Funestra's HUD leads with."""
from __future__ import annotations

from funestra.hud_title import (
    ENHANCED_LABEL,
    F_MODE_LABEL,
    LATEST_LABEL,
    LOCKED_LABEL,
    SHUFFLE_LABEL,
    UNLOCKED_LABEL,
    hud_title,
)


def test_an_idle_funestra_says_only_whether_it_is_holding_what_is_on_screen():
    """The lock is the one state every Funestra in this family has, so it is the one
    thing the title always carries."""
    assert hud_title(locked=True) == LOCKED_LABEL
    assert hud_title(locked=False) == UNLOCKED_LABEL


def test_the_slots_run_from_the_set_being_played_down_to_the_finest_filter():
    """Set, hold, order, then the two filters coarse before fine — the order a
    reader's eye takes: what is playing, whether it is stuck, how it advances, and
    what was cut out of it."""
    assert hud_title(
        playing_set="Looping seeds", locked=True, order="Latest",
        f_mode=True, filters=("alpha",),
    ) == f"Looping seeds · {LOCKED_LABEL} · Latest · {F_MODE_LABEL} · alpha"


def test_a_set_playing_through_drops_unlocked_but_keeps_locked():
    """A set on repeat holds nothing, so saying "Unlocked" beside one is noise —
    it names the absence of a hold that was never on offer.  A hold taken inside
    the set is real, though: it is a stop at one clip of it, and it stays."""
    assert hud_title(playing_set="Looping seeds", locked=False) == "Looping seeds"
    assert hud_title(playing_set="Looping seeds", locked=True) == (
        f"Looping seeds · {LOCKED_LABEL}")


def test_an_empty_slot_takes_no_room_and_leaves_no_separator():
    """Every slot but the lock is optional, and a Funestra without one prints nothing
    there rather than an empty phrase or a doubled separator."""
    assert hud_title(locked=False, order=SHUFFLE_LABEL) == f"{UNLOCKED_LABEL} · Shuffle"
    assert hud_title(locked=False, filters=("beta",)) == f"{UNLOCKED_LABEL} · beta"


def test_a_checkout_from_before_the_rename_still_gets_its_status_line():
    from funestra.hud_status import status_line  # noqa: PLC0415

    assert status_line(locked=True, filter_label="alpha") == f"{LOCKED_LABEL} · alpha"
    assert status_line(locked=True) == LOCKED_LABEL


def test_the_two_browse_orders_are_named_once_for_every_funestra():
    """Each Funestra browses newest-first or shuffled, and says so in this slot — so
    the words belong here rather than in each app, where they drifted before."""
    assert (LATEST_LABEL, SHUFFLE_LABEL) == ("Latest", "Shuffle")


def test_the_enhanced_narrowing_has_a_slot_of_its_own_after_f_mode():
    """Origenerator's shows keep only the pictures they have enhanced the way a
    Funestra keeps only its favorites — the same kind of cut, said in the same
    sentence — so the slot is a flag here, and the HUD carrying the switch never
    has to own the word for it.  Coarse before fine: F-mode, then this, then
    whatever act filter is left."""

    assert hud_title(locked=False, order=SHUFFLE_LABEL, enhanced=True) == (
        f"{UNLOCKED_LABEL} · Shuffle · {ENHANCED_LABEL}")
    assert hud_title(locked=True, f_mode=True, enhanced=True, filters=("alpha",)) == (
        f"{LOCKED_LABEL} · {F_MODE_LABEL} · {ENHANCED_LABEL} · alpha")
    assert hud_title(locked=True, enhanced=False) == LOCKED_LABEL
