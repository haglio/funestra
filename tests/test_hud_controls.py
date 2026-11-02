"""The controls every HUD carries, declared once: the same face, place and
graying on every Funestra, with the words a source has of its own."""
from __future__ import annotations

import pytest

from funestra.funestra_verbs import SEEK_BACK, SEEK_FWD
from funestra.hud_controls import (
    AN_IMAGE,
    FUNSCRIPT_JUMP_ICON,
    LATEST_ICON,
    NONE_FOR_THIS_ONE,
    RESET_ICON,
    RESET_TOOLTIP,
    SHUFFLE_ICON,
    TRASH_ICON,
    VERSIONS_ICON,
    browse_order_buttons,
    favorites_only_tooltip,
    fmode_button,
    funscript_jump_button,
    lit_or_remembered,
    lock_button,
    lock_tooltip,
    longer_than_a_step,
    reset_button,
    too_near_the_end_to_step_forward,
    too_near_the_start_to_step_back,
    too_short_to_step,
    transport,
    trash_button,
    versions_button,
    why_it_cannot_step,
)
from funestra.hud_marks import (
    BACK_ICON,
    FMODE_ICON,
    FORWARD_ICON,
    LOCK_ICON,
    NEXT_ICON,
    PREVIOUS_ICON,
    shared_mark_name,
)
from funestra.hud_title import F_MODE_LABEL, LATEST_LABEL, SHUFFLE_LABEL
from funestra.status import FunestraStatus


def _by_name(buttons) -> dict:
    return {button.command.removeprefix("portrait_"): button for button in buttons}


class TestTheTransport:
    def test_steps_either_way_around_the_two_ten_second_nudges(self):
        row = transport("portrait", noun="clip", longer_than_a_step=True)

        assert [button.command for button in row] == [
            "portrait_prev", "portrait_nudge_prev", "portrait_nudge_next", "portrait_next"]
        assert [button.glyph for button in row] == [
            PREVIOUS_ICON, BACK_ICON, FORWARD_ICON, NEXT_ICON]
        assert [button.tooltip for button in row] == [
            "Previous clip", "Back 10s", "Forward 10s", "Next clip"]
        assert not any(button.dim for button in row)

    def test_the_ten_second_steps_are_dim_on_a_clip_of_ten_seconds_or_shorter(self):
        row = _by_name(transport("portrait", noun="clip", longer_than_a_step=False))

        for step in ("nudge_prev", "nudge_next"):
            assert row[step].dim
            assert row[step].tooltip.endswith(" (this clip is 10s or shorter)")
        assert not row["prev"].dim
        assert not row["next"].dim

    def test_the_ten_second_steps_are_dim_on_an_image_and_say_so(self):
        row = _by_name(transport("portrait", noun="slide", longer_than_a_step=True, image=True))

        assert [row[step].tooltip for step in ("nudge_prev", "nudge_next")] == [
            f"Back 10s ({AN_IMAGE})", f"Forward 10s ({AN_IMAGE})"]
        assert [row[step].dim for step in ("nudge_prev", "nudge_next")] == [True, True]

    def test_the_noun_is_the_sources_word_for_what_it_plays(self):
        row = _by_name(transport("main", noun="video", longer_than_a_step=False))

        assert row["main_prev"].tooltip == "Previous video"
        assert too_short_to_step("video") in row["main_nudge_prev"].tooltip


class TestWhyAStepIsRefused:
    def test_a_clip_longer_than_a_step_can_be_stepped(self):
        assert longer_than_a_step(10_001) is True
        assert longer_than_a_step(10_000) is False

    @pytest.mark.parametrize(("verb", "status", "why"), [
        (SEEK_FWD, FunestraStatus(duration_ms=8_000), too_short_to_step("video")),
        (SEEK_BACK, FunestraStatus(duration_ms=30_000, position_ms=5_000),
         too_near_the_start_to_step_back("video")),
        (SEEK_FWD, FunestraStatus(duration_ms=30_000, position_ms=25_000),
         too_near_the_end_to_step_forward("video")),
        (SEEK_FWD, FunestraStatus(duration_ms=30_000, position_ms=5_000, image=True), AN_IMAGE),
        (SEEK_FWD, FunestraStatus(duration_ms=30_000, position_ms=5_000), None),
        (SEEK_BACK, FunestraStatus(duration_ms=30_000, position_ms=25_000), None),
    ])
    def test_says_why_or_nothing(self, verb, status, why):
        assert why_it_cannot_step(verb, status, "video") == why


class TestSkipAhead:
    def test_rides_the_transport_lit_only_by_the_scripting(self):
        jump = funscript_jump_button("portrait_funscript_jump", noun="clip", has_osr2=True,
                                     has_funscript=True)

        assert shared_mark_name(jump.glyph) == "funscript_jump"
        assert jump.glyph == FUNSCRIPT_JUMP_ICON
        assert jump.tooltip == "Skip ahead to where this clip's scripting starts up again"
        assert not jump.dim

    @pytest.mark.parametrize(("has_osr2", "has_funscript", "why"), [
        (False, True, "this Funestra doesn't have the OSR2"),
        (True, False, "this clip has no funscript"),
        (False, False, "this Funestra doesn't have the OSR2 and this clip has no funscript"),
    ])
    def test_grays_out_without_the_osr2_or_a_funscript_and_says_which(
            self, has_osr2, has_funscript, why):
        jump = funscript_jump_button("portrait_funscript_jump", noun="clip", has_osr2=has_osr2,
                                     has_funscript=has_funscript)

        assert jump.dim
        assert jump.tooltip.endswith(f" ({why})")


class TestTheSwitchesAndTheThingsDone:
    def test_the_lock_is_a_green_switch_that_opens_the_wider_gap(self):
        held = lock_button("portrait", locked=True, tooltip=lock_tooltip(True, "clip"))
        free = lock_button("portrait", locked=False, tooltip=lock_tooltip(False, "clip"))

        assert (held.command, held.glyph) == ("portrait_lock", LOCK_ICON)
        assert (held.lit, held.favorite, held.group_break) == (True, True, True)
        assert not free.lit
        assert held.tooltip == "Locked — this clip repeats; press to play on through the playlist"
        assert free.tooltip == "Unlocked — plays on through the playlist; press to hold this clip"

    def test_the_trash_unfavorites_a_favorite_and_sends_anything_else_to_trash(self):
        trash = trash_button("portrait")

        assert (trash.command, trash.glyph, trash.tooltip) == (
            "portrait_trash", TRASH_ICON,
            "Unfavorite it — or send it to Trash when it is not a favorite")
        assert trash.danger

    def test_f_mode_is_the_favorites_green_switch(self):
        fmode = fmode_button("portrait", favorites_only_tooltip(), lit=True)

        assert (fmode.command, fmode.glyph) == ("portrait_fmode", FMODE_ICON)
        assert fmode.tooltip == f"{F_MODE_LABEL} — browse only the favorites on this Funestra"
        assert (fmode.lit, fmode.favorite) == (True, True)
        assert not fmode_button("portrait", "F-Mode — only the scripted ones", lit=False).lit

    def test_reset_is_a_thing_done_faded_with_nothing_to_put_back(self):
        reset = reset_button("portrait", nothing_to_reset=True, tooltip=RESET_TOOLTIP)

        assert (reset.command, reset.glyph) == ("portrait_reset", RESET_ICON)
        assert (reset.dim, reset.group_break, reset.lit) == (True, True, False)
        assert reset.tooltip.startswith("Reset — ")
        assert not reset_button("portrait", nothing_to_reset=False, tooltip="Reset — this set").dim
        assert not reset_button("portrait", nothing_to_reset=False, tooltip="Reset — this set",
                                group_break=False).group_break

    def test_the_order_pair_lights_the_order_in_play(self):
        shuffle, latest = browse_order_buttons("portrait", latest=True)

        assert (shuffle.command, shuffle.glyph) == ("portrait_shuffle", SHUFFLE_ICON)
        assert (latest.command, latest.glyph) == ("portrait_latest", LATEST_ICON)
        assert [button.tooltip.split(" ")[0] for button in (shuffle, latest)] == [
            SHUFFLE_LABEL, LATEST_LABEL]
        assert (shuffle.lit, latest.lit) == (False, True)
        assert (shuffle.group_break, latest.group_break) == (True, False)
        assert browse_order_buttons("portrait", latest=None) == ()

    def test_an_order_chosen_but_not_yet_applied_is_remembered_rather_than_lit(self):
        assert lit_or_remembered(True, True) == {"lit": False, "remembered": True}
        assert lit_or_remembered(True, False) == {"lit": True, "remembered": False}
        assert lit_or_remembered(False, True) == {"lit": False, "remembered": False}
        shuffle, _latest = browse_order_buttons("main", latest=False, remembered=True)
        assert (shuffle.remembered, shuffle.lit) == (True, False)

    def test_the_versions_button_is_dim_where_the_clip_has_only_itself(self):
        alone = versions_button("portrait_cycle_version", noun="clip", has_other_versions=False)
        among = versions_button("portrait_cycle_version", noun="clip", has_other_versions=True)

        assert (alone.glyph, alone.group_break) == (VERSIONS_ICON, True)
        assert (alone.dim, alone.tooltip) == (True, "Another version of this clip" + NONE_FOR_THIS_ONE)
        assert (among.dim, among.tooltip) == (False, "Another version of this clip")
