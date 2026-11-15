from __future__ import annotations

from dataclasses import replace

import pytest
from shared_ui.icon_geometry import icon_names

from funestra import hud_minimize
from funestra.hud_button import BUTTON, FIT_THE_WORD, Button
from funestra.hud_controls import (
    AN_IMAGE,
    LATEST_ICON,
    RESET_PUTS_BACK_THE_SPEED,
    TRASH_TOOLTIP,
    lock_tooltip,
)
from funestra.hud_icons import (
    MINIMIZE_FUNESTRA_ICON,
    SHARED_ICON,
    UNFAVORITE_ICON,
    shared_icon,
    shared_icon_name,
)
from funestra.hud_kinds import (
    EVERY_SHOW,
    TRANSPORT_CONTROLS,
    HudControl,
    HudFacts,
    HudKind,
    clip_seconds_row,
    hud_rows,
    main_title,
    osr2_button,
    slideshow_title,
    title_choices,
    window_buttons,
)
from funestra.hud_title import (
    F_MODE_LABEL,
    LATEST_LABEL,
    SHUFFLE_LABEL,
    compilation_label,
)
from funestra.inclusion_pair import LENGTH, ORIENTATION, PROJECTION
from funestra.main_hud import GAP, GROUP_GAP, ModeHud, hit_test, place_rows, tooltip_at
from funestra.modes import LengthMode, MainMode
from funestra.satellite_hud import HudModel
from funestra.satellite_hud_paint import HudRenderer

_EVERY_KIND_OF_HUD = (
    (HudKind.MAIN, HudFacts(funestra="main", main_mode=MainMode.KINO)),
    (HudKind.MAIN, HudFacts(funestra="main", main_mode=MainMode.GENAU, flick_one="pip")),
    (HudKind.SATELLITE, HudFacts(funestra="portrait")),
    (HudKind.SATELLITE, HudFacts(funestra="landscape", in_vr=True)),
    (HudKind.SLIDESHOW, HudFacts(funestra="portrait", clip_seconds=5)),
)


def _a_new_button(facts: HudFacts, _shows) -> tuple[Button, ...]:
    return (Button(f"{facts.funestra}_made_up", "M", "A made-up button"),)


def test_a_new_button_for_every_hud_is_one_line_of_one_table():
    controls = (*TRANSPORT_CONTROLS, HudControl("made_up", EVERY_SHOW, _a_new_button))

    for kind, facts in _EVERY_KIND_OF_HUD:
        commands = [button.command for row in hud_rows(kind, facts, controls) for button in row]
        assert f"{facts.funestra}_made_up" in commands, (kind, facts)


FLAT_ICON, VR_ICON = PROJECTION.first.mark, PROJECTION.second.mark
CLIPS_ICON, FULL_ICON = LENGTH.first.mark, LENGTH.second.mark
PORTRAIT_ICON, LANDSCAPE_ICON = ORIENTATION.first.mark, ORIENTATION.second.mark

_MINUS, _PLUS = shared_icon("minus"), shared_icon("plus")


def _main_facts(**over) -> HudFacts:
    return HudFacts(**{"funestra": "main", "flick_one": "pip", "flick_many": "pips",
                       "locked": True, "crowned": True, "has_osr2": True, **over})


def main_hud_rows(facts: HudFacts, *, in_vr: bool = False) -> tuple[tuple[Button, ...], ...]:
    return hud_rows(HudKind.MAIN, replace(facts, in_vr=in_vr))


def _every_row(facts: HudFacts) -> tuple[tuple[Button, ...], ...]:
    return main_hud_rows(facts)


def _actions(facts: HudFacts) -> list[str]:
    return [b.command for row in _every_row(facts) for b in row if b.command]


def _button(facts: HudFacts, action: str) -> Button:
    return next(b for row in _every_row(facts) for b in row if b.command == action)


def _placed(facts: HudFacts) -> dict[str, tuple]:
    return {b.command: rect for rect, b in place_rows(_every_row(facts), x=0, y=0)}


_EVERY_FACE_SLOTS = (
    _main_facts(main_mode=MainMode.KINO, latest=False, length_mode=LengthMode.MIXED, plays_vr=True, plays_flat=True,
                has_compilation=True, has_other_versions=True, jump_to="scene"),
    _main_facts(main_mode=MainMode.KINO, jump_to="clip"),
    _main_facts(main_mode=MainMode.GENAU, latest=False),
)


def _every_button() -> list[Button]:
    declared = [b for facts in _EVERY_FACE_SLOTS for row in _every_row(facts) for b in row]
    return [*declared, osr2_button("main", has_it=True), osr2_button("main", has_it=False)]


class TestTransport:
    def test_kino_mode_steps_the_video_and_acts_on_it(self):
        actions = _actions(_main_facts(main_mode=MainMode.KINO))
        for action in ("main_prev", "main_next", "main_nudge_prev",
                       "main_nudge_next", "main_fmode", "browse_library",
                       "genaumacher_save", "main_funestra_record_tap"):
            assert action in actions, action

    def test_f_mode_is_the_main_funestras_own_and_lights_while_it_is_on(self):
        assert _button(_main_facts(main_mode=MainMode.KINO), "main_fmode").lit is False
        assert _button(_main_facts(main_mode=MainMode.KINO, f_mode=True), "main_fmode").lit is True

    def test_genau_steps_its_own_flicks_and_can_mark_one_trash(self):
        actions = _actions(_main_facts(main_mode=MainMode.GENAU))

        assert "genau_prev_flick" in actions
        assert "genau_next_flick" in actions
        assert "genau_trash_flick" in actions

    def test_genau_can_flip_the_flick_up_half_a_snippet(self):
        flip = _button(_main_facts(main_mode=MainMode.GENAU), "genau_flip_ends")

        assert shared_icon_name(flip.icon) == "flip_ends"
        assert flip.lit is False
        assert _button(_main_facts(main_mode=MainMode.GENAU, flipped=True), "genau_flip_ends").lit is True

    def test_a_video_has_no_flick_to_flip(self):
        assert "genau_flip_ends" not in _actions(_main_facts(main_mode=MainMode.KINO))

    def test_genau_offers_no_video_only_actions(self):
        actions = _actions(_main_facts(main_mode=MainMode.GENAU))

        for action in ("main_nudge_prev", "genaumacher_save", "main_funestra_record_tap"):
            assert action not in actions

    def test_genau_browses_its_flicks_from_the_same_button_kino_browses_its_library(self):
        kino = _button(_main_facts(main_mode=MainMode.KINO), "browse_library")
        genau = _button(_main_facts(main_mode=MainMode.GENAU), "browse_library")

        assert (kino.icon, kino.tooltip) == (genau.icon, "Browse the library")
        assert genau.tooltip == "Browse the pips"

    def test_genaus_transport_names_its_flicks_in_the_overlays_word(self):
        def tips(**facts):
            return {b.command: b.tooltip for row in _every_row(_main_facts(main_mode=MainMode.GENAU, **facts))
                    for b in row}

        held, loose = tips(locked=True, pace_s=7), tips(locked=False, pace_s=7)

        assert (held["genau_prev_flick"], held["genau_next_flick"]) == ("Previous pip", "Next pip")
        assert held["main_lock"] == "Locked — this pip repeats; press to move on every 7s"
        assert loose["main_lock"] == "Unlocked — moving on every 7s; press to hold this pip"
        assert tips(flipped=True)["genau_flip_ends"] == "Flipped — this pip stays that way; press to put it back"
        assert tips()["genau_flip_ends"] == ("Flip this pip, for one running opposite the OSR2 — "
                                             "it stays flipped")


class TestKinosFMode:
    def test_it_plays_only_the_well_funscripted_videos(self):
        button = _button(_main_facts(main_mode=MainMode.KINO), "main_fmode")

        assert button.tooltip == f"{F_MODE_LABEL} — play only the well funscripted videos"


class TestGenausFMode:
    def test_it_keeps_the_favorites_and_says_so(self):
        off = _button(_main_facts(main_mode=MainMode.GENAU), "main_fmode")
        on = _button(_main_facts(main_mode=MainMode.GENAU, f_mode=True), "main_fmode")

        assert (off.lit, on.lit) == (False, True)
        assert off.tooltip == f"{F_MODE_LABEL} — play only the favorites"
        assert on.tooltip == "Showing the favorites only — press for all of them"
        assert on.favorite is True

    def test_it_holds_the_place_it_holds_in_kino_mode_straight_after_the_lock(self):
        for mode in MainMode:
            actions = _actions(_main_facts(main_mode=mode))
            assert actions.index("main_fmode") == actions.index("main_lock") + 1, mode


class TestReset:
    def test_the_main_funestra_can_be_reset_wherever_main_funestra_is_on_screen(self):
        assert "main_reset" in _actions(_main_facts(main_mode=MainMode.KINO))

    def test_it_is_not_offered_where_there_is_no_main_funestra_playlist(self):
        assert "main_reset" not in _actions(_main_facts(main_mode=MainMode.GENAU))

    def test_it_is_a_thing_done_rather_than_a_state_held(self):
        for scripted_filter in (False, True):
            button = _button(_main_facts(main_mode=MainMode.KINO, f_mode=scripted_filter),
                             "main_reset")
            assert button.lit is False
            assert button.favorite is False

    def test_it_stands_clear_of_the_switches_it_turns_off(self):
        by_action = _placed(_main_facts(main_mode=MainMode.KINO))
        fmode, reset = by_action["main_fmode"], by_action["main_reset"]

        assert reset[0] - (fmode[0] + fmode[2]) == GROUP_GAP


class TestBrowseOrder:
    def test_both_funestras_can_be_reordered_from_the_main_hud(self):
        for mode in MainMode:
            actions = _actions(_main_facts(main_mode=mode, latest=False))
            assert "main_shuffle" in actions
            assert "main_latest" in actions

    def test_exactly_one_of_the_pair_is_lit(self):
        shuffled, newest = _main_facts(main_mode=MainMode.KINO, latest=False), _main_facts(main_mode=MainMode.KINO, latest=True)

        assert _button(shuffled, "main_shuffle").lit is True
        assert _button(shuffled, "main_latest").lit is False
        assert _button(newest, "main_shuffle").lit is False
        assert _button(newest, "main_latest").lit is True

    def test_neither_of_the_pair_wears_a_color_of_its_own(self):
        for action in ("main_shuffle", "main_latest"):
            button = _button(_main_facts(main_mode=MainMode.KINO, latest=False), action)
            assert button.favorite is False
            assert button.enhanced is False

    def test_the_pair_is_its_own_group_after_the_reset(self):
        by_action = _placed(_main_facts(main_mode=MainMode.KINO, latest=False))
        reset = by_action["main_reset"]
        shuffle, latest = by_action["main_shuffle"], by_action["main_latest"]

        assert shuffle[0] - (reset[0] + reset[2]) == GROUP_GAP
        assert latest[0] - (shuffle[0] + shuffle[2]) == GAP

    def test_a_host_with_no_browse_order_is_offered_neither(self):
        actions = _actions(_main_facts(main_mode=MainMode.GENAU))

        assert "main_shuffle" not in actions
        assert "main_latest" not in actions


class TestProjectionPair:
    def _flat_and_vr(self, *, flat, vr, **over) -> tuple[Button, ...]:
        rows = main_hud_rows(_main_facts(main_mode=MainMode.KINO, latest=False, length_mode=LengthMode.MIXED,
                                     plays_flat=flat, plays_vr=vr, **over))
        by_face = {b.icon: b for row in rows for b in row if b.command.startswith("main_projection")}
        return tuple(by_face[face] for face in (FLAT_ICON, VR_ICON) if face in by_face)

    def test_both_shapes_is_both_of_them_lit(self):
        assert [b.lit for b in self._flat_and_vr(flat=True, vr=True)] == [True, True]

    def test_dropping_one_from_both_asks_for_the_other_alone(self):
        flat, vr = self._flat_and_vr(flat=True, vr=True)

        assert (flat.command, vr.command) == ("main_projection_vr", "main_projection_flat")

    def test_putting_the_dark_one_back_asks_for_both(self):
        flat, vr = self._flat_and_vr(flat=False, vr=True)

        assert (flat.lit, vr.lit) == (False, True)
        assert flat.command == "main_projection_both"

    def test_the_last_lit_one_can_still_be_turned_off(self):
        flat, vr = self._flat_and_vr(flat=True, vr=False)

        assert (flat.dim, vr.dim) == (False, False)
        assert flat.command == "main_projection_none"

    def test_neither_lit_offers_each_shape_back(self):
        flat, vr = self._flat_and_vr(flat=False, vr=False)

        assert (flat.command, vr.command) == ("main_projection_flat", "main_projection_vr")

    def test_flat_leads_vr_after_portrait_and_landscape_in_a_group_of_their_own(self):
        placed = place_rows(main_hud_rows(_main_facts(main_mode=MainMode.KINO, latest=False,
                                                  plays_flat=True, plays_vr=True)), x=0, y=0)
        rect_of = {b.icon: rect for rect, b in placed}
        landscape, flat, vr = rect_of[LANDSCAPE_ICON], rect_of[FLAT_ICON], rect_of[VR_ICON]

        assert flat[0] - (landscape[0] + landscape[2]) == GROUP_GAP
        assert vr[0] - (flat[0] + flat[2]) == GAP

    def test_inside_a_compilation_the_shapes_read_as_held(self):
        pair = self._flat_and_vr(flat=True, vr=True, compilation="Volume 6")

        assert pair
        assert all(b.remembered and not b.lit for b in pair)


class TestGenausProjectionPair:
    def _pair(self, plays_vr, plays_flat):
        rows = main_hud_rows(_main_facts(main_mode=MainMode.GENAU, latest=False,
                                     plays_vr=plays_vr, plays_flat=plays_flat))
        return [b for row in rows for b in row if b.command.startswith("main_projection")]

    def _faces_after_latest(self, main_mode: MainMode) -> list[str]:
        faces = [b.icon for row in main_hud_rows(_main_facts(main_mode=main_mode, latest=False,
                                                           plays_vr=True, plays_flat=True))
                 for b in row]
        return faces[faces.index(LATEST_ICON) + 1:][:2]

    def test_it_follows_the_browse_order_as_it_does_under_a_video(self):
        assert self._faces_after_latest(MainMode.GENAU) == self._faces_after_latest(MainMode.KINO) != []

    def test_it_names_the_flicks_where_the_video_pair_says_videos(self):
        tips = [{b.tooltip for b in self._pair(*plays)}
                for plays in ((True, True), (True, False), (False, False))]

        assert tips == [
            {"Including VR pips", "Including 2D pips"},
            {"Including VR pips", "Not including 2D pips"},
            {"Not including VR pips", "Not including 2D pips"},
        ]


class TestLengthPair:
    def _clips_and_full(self, length_mode: LengthMode, **over) -> tuple[Button, ...]:
        rows = main_hud_rows(_main_facts(main_mode=MainMode.KINO, latest=False, length_mode=length_mode, **over))
        by_face = {b.icon: b for row in rows for b in row if b.command.startswith("main_funestra_length")}
        return tuple(by_face[face] for face in (CLIPS_ICON, FULL_ICON) if face in by_face)

    def test_mixed_is_both_of_them_lit(self):
        assert [b.lit for b in self._clips_and_full(LengthMode.MIXED)] == [True, True]

    def test_one_length_is_that_one_lit_and_the_other_dark(self):
        assert [b.lit for b in self._clips_and_full(LengthMode.CLIPS)] == [True, False]
        assert [b.lit for b in self._clips_and_full(LengthMode.FULL)] == [False, True]

    def test_dropping_one_from_mixed_asks_for_the_other_alone(self):
        clips, full = self._clips_and_full(LengthMode.MIXED)

        assert (clips.command, full.command) == ("main_funestra_length_full", "main_funestra_length_clips")

    def test_putting_the_dark_one_back_asks_for_mixed(self):
        clips, _full = self._clips_and_full(LengthMode.FULL)

        assert clips.command == "main_funestra_length_mixed"

    def test_the_last_lit_one_can_still_be_turned_off(self):
        clips, full = self._clips_and_full(LengthMode.FULL)

        assert (clips.dim, full.dim) == (False, False)
        assert full.command == "main_funestra_length_none"

    def test_neither_lit_offers_each_length_back(self):
        clips, full = self._clips_and_full(LengthMode.NONE)

        assert (clips.lit, full.lit) == (False, False)
        assert (clips.command, full.command) == ("main_funestra_length_clips", "main_funestra_length_full")

    def test_clips_lead_full_after_2d_and_vr_in_a_group_of_their_own(self):
        placed = place_rows(main_hud_rows(_main_facts(main_mode=MainMode.KINO, latest=False,
                                                  length_mode=LengthMode.MIXED)), x=0, y=0)
        rect_of = {b.icon: rect for rect, b in placed}
        vr, clips, full = rect_of[VR_ICON], rect_of[CLIPS_ICON], rect_of[FULL_ICON]

        assert clips[0] - (vr[0] + vr[2]) == GROUP_GAP
        assert full[0] - (clips[0] + clips[2]) == GAP

    def test_each_says_whether_its_length_is_included(self):
        clips, full = self._clips_and_full(LengthMode.CLIPS)

        assert (clips.tooltip, full.tooltip) == ("Including clips", "Not including full videos")


class TestCompilationAndJumps:
    def _button_for(self, action: str, **over):
        return _button(_main_facts(main_mode=MainMode.KINO, latest=False, length_mode=LengthMode.MIXED, **over), action)

    def test_the_compilation_button_enters_and_the_lit_one_leaves(self):
        outside = self._button_for("main_funestra_compilation", has_compilation=True)
        inside = self._button_for("main_funestra_end_compilation", compilation="Volume 6")

        assert outside.lit is False
        assert outside.dim is False
        assert inside.lit is True

    def test_a_video_in_no_compilation_cannot_be_pressed_into_one(self):
        assert self._button_for("main_funestra_compilation").dim is True

    def test_inside_a_compilation_the_order_and_length_read_as_held(self):
        rows = main_hud_rows(_main_facts(main_mode=MainMode.KINO, latest=False, length_mode=LengthMode.MIXED,
                                     compilation="Volume 6"))
        held = [b for row in rows for b in row
                if b.command in ("main_shuffle", "main_funestra_length_clips")]

        assert held
        assert all(b.remembered and not b.lit for b in held)

    def test_the_clip_jump_says_which_way_it_would_go(self):
        to_scene = self._button_for("main_funestra_full_vid", jump_to="scene")
        to_clip = self._button_for("main_funestra_clip_jump", jump_to="clip")

        assert to_scene.icon != to_clip.icon
        assert to_scene.dim is False
        assert to_clip.dim is False

    def test_a_video_with_nothing_on_the_other_end_is_dim(self):
        assert self._button_for("main_funestra_clip_jump").dim is True

    def test_the_version_step_is_dim_without_another_version(self):
        assert self._button_for("main_funestra_cycle_version").dim is True
        assert self._button_for("main_funestra_cycle_version", has_other_versions=True).dim is False


class TestLock:
    def test_it_is_lit_while_the_video_is_held(self):
        assert _button(_main_facts(main_mode=MainMode.KINO, locked=True), "main_lock").lit is True
        assert _button(_main_facts(main_mode=MainMode.KINO, locked=False), "main_lock").lit is False

    def test_it_says_which_way_a_press_goes(self):
        held = _button(_main_facts(main_mode=MainMode.KINO, locked=True), "main_lock")
        loose = _button(_main_facts(main_mode=MainMode.KINO, locked=False), "main_lock")

        assert held.tooltip.startswith("Locked")
        assert "play on" in held.tooltip
        assert loose.tooltip.startswith("Unlocked")
        assert "hold this video" in loose.tooltip

    def test_it_pairs_with_f_mode_and_stands_apart_from_everything_else(self):
        by_action = _placed(_main_facts(main_mode=MainMode.KINO))
        step, skip = by_action["main_next"], by_action["main_funestra_funscript_jump"]
        lock = by_action["main_lock"]
        fmode, reset = by_action["main_fmode"], by_action["main_reset"]

        assert skip[0] - (step[0] + step[2]) == GAP
        assert lock[1] != skip[1]
        assert fmode[0] - (lock[0] + lock[2]) == GAP
        assert reset[0] - (fmode[0] + fmode[2]) == GROUP_GAP

    def test_every_mode_offers_exactly_one_padlock_lit_while_whatever_shows_is_held(self):
        for mode in MainMode:
            assert _actions(_main_facts(main_mode=mode)).count("main_lock") == 1, mode
            assert _button(_main_facts(main_mode=mode, locked=True), "main_lock").lit is True
            assert _button(_main_facts(main_mode=mode, locked=False), "main_lock").lit is False

    def test_in_genau_it_says_what_the_clip_does_and_how_fast(self):
        held = _button(_main_facts(main_mode=MainMode.GENAU, locked=True, pace_s=7), "main_lock")
        loose = _button(_main_facts(main_mode=MainMode.GENAU, locked=False, pace_s=7), "main_lock")

        assert held.tooltip.startswith("Locked")
        assert "every 7s" in held.tooltip
        assert loose.tooltip.startswith("Unlocked")
        assert "every 7s" in loose.tooltip


class TestPaceRows:
    def test_the_video_rate_has_controls_where_main_funestra_is_on_screen(self):
        actions = _actions(_main_facts(main_mode=MainMode.KINO))
        assert "main_funestra_speed_down" in actions
        assert "main_funestra_speed_up" in actions
        assert "genau_flick_seconds_down" not in actions

    def test_genau_has_the_video_rate_and_the_pace(self):
        actions = _actions(_main_facts(main_mode=MainMode.GENAU))
        assert "genau_flick_seconds_down" in actions
        assert "genau_flick_seconds_up" in actions
        assert "main_funestra_speed_down" in actions

    def test_the_rate_is_a_read_out_between_the_arrows_that_the_funestra_fills(self):
        row = next(row for row in main_hud_rows(_main_facts(main_mode=MainMode.KINO))
                   if any(b.command == "main_funestra_speed_down" for b in row))

        assert [b.icon or b.host_value for b in row] == [
            "Playback speed", _MINUS, "playback_speed", _PLUS]

    def test_the_seconds_are_a_read_out_between_the_arrows_that_genau_fills(self):
        row = next(row for row in main_hud_rows(_main_facts(main_mode=MainMode.GENAU))
                   if any(b.command == "genau_flick_seconds_down" for b in row))

        assert [b.icon or b.host_value for b in row] == [
            "Playback speed", _MINUS, "playback_speed", _PLUS,
            "Pip seconds", _MINUS, "advance_interval", _PLUS]
        assert row[-1].tooltip == "Leave each pip longer"

    def test_a_read_out_is_not_a_hit_target(self):
        placed = place_rows(main_hud_rows(_main_facts(main_mode=MainMode.KINO)), x=0, y=0)
        rect = next(r for r, b in placed if b.host_value == "playback_speed")

        assert hit_test(placed, rect[0] + 1, rect[1] + 1) == ""

    def test_the_rate_pair_says_what_a_satellites_rate_pair_says(self):
        rendered = HudRenderer("landscape").render(
            HudModel(funestra="landscape", playback_speed=1.0))
        satellite = [button.tooltip for _rect, button in rendered.targets.buttons
                     if button.command.startswith("landscape_speed_")]
        console = [button.tooltip
                   for row in main_hud_rows(_main_facts(main_mode=MainMode.KINO))
                   for button in row if button.command.startswith("main_funestra_speed_")]

        assert satellite == console != []


class TestSkipAhead:
    @staticmethod
    def _transport_row(facts: HudFacts) -> list[str]:
        return [button.command for button in next(
            row for row in main_hud_rows(facts) if any(b.command == "main_prev" for b in row))]

    def test_skip_ahead_follows_previous_and_next_as_on_every_satellite(self):
        row = self._transport_row(_main_facts(main_mode=MainMode.KINO))

        start = row.index("main_prev")
        assert row[start:start + 5] == ["main_prev", "main_nudge_prev", "main_nudge_next",
                                        "main_next", "main_funestra_funscript_jump"]

    @pytest.mark.parametrize("has_osr2", [True, False])
    def test_skip_ahead_is_there_whether_or_not_the_main_funestra_has_the_osr2(self, has_osr2):
        facts = _main_facts(main_mode=MainMode.KINO, has_osr2=has_osr2)

        assert "main_funestra_funscript_jump" in self._transport_row(facts)
        osr2 = next(b for b in main_hud_rows(facts)[0] if b.command == "main_take_osr2")
        assert osr2.lit is has_osr2

    @pytest.mark.parametrize(("has_osr2", "has_funscript", "why"), [
        (False, True, " (this Funestra doesn't have the OSR2)"),
        (True, False, " (this video has no funscript)"),
        (True, True, ""),
    ])
    def test_skip_ahead_grays_out_without_the_osr2_or_a_funscript(self, has_osr2, has_funscript,
                                                                  why):
        jump = _button(_main_facts(main_mode=MainMode.KINO, has_osr2=has_osr2,
                                has_funscript=has_funscript), "main_funestra_funscript_jump")

        assert jump.dim is bool(why)
        assert jump.tooltip == f"Skip ahead to where this video's scripting starts up again{why}"

    def test_skip_ahead_rides_a_video_alone(self):
        assert "main_funestra_funscript_jump" not in _actions(_main_facts(main_mode=MainMode.GENAU))


class TestDriveControls:
    def test_the_axis_arrows_are_not_main_hud_buttons(self):
        actions = _actions(_main_facts(main_mode=MainMode.KINO))

        for action in ("robot_hand_amplitude_up", "robot_hand_center_down", "robot_hand_speed_up"):
            assert action not in actions

class TestTheOsr2Button:
    def test_a_main_hud_that_has_the_osr2_wears_its_button_lit_after_kino_and_genau(self):
        top = main_hud_rows(_main_facts(main_mode=MainMode.GENAU))[0]

        assert top[2].command == "main_take_osr2"
        assert (top[2].lit, top[2].group_break) == (True, True)

    def test_a_main_hud_that_gave_the_osr2_away_offers_it_back_there(self):
        top = main_hud_rows(_main_facts(main_mode=MainMode.KINO, has_osr2=False))[0]

        assert top[2].command == "main_take_osr2"
        assert top[2].lit is False


class TestState:
    def test_the_mode_you_are_in_is_lit_and_the_others_are_not(self):
        facts = _main_facts(main_mode=MainMode.KINO)

        assert _button(facts, "main_kino_activate").lit is True
        assert _button(facts, "genau_activate").lit is False

    def test_nothing_but_the_recording_and_its_snippet_takes_a_color_of_its_own(self):
        colored = [b.command for row in _every_row(_main_facts(main_mode=MainMode.GENAU, locked=True))
                   for b in row if b.warn or b.hold]

        assert colored == []

    def test_f_mode_keeps_the_green_the_other_switches_gave_up(self):
        assert _button(_main_facts(main_mode=MainMode.KINO, f_mode=True), "main_fmode").favorite is True

    def test_the_record_button_tells_marking_from_repeating(self):
        idle = _button(_main_facts(main_mode=MainMode.KINO), "main_funestra_record_tap")
        marking = _button(_main_facts(main_mode=MainMode.KINO, snippet="recording"), "main_funestra_record_tap")
        repeating = _button(_main_facts(main_mode=MainMode.KINO, snippet="repeating"), "main_funestra_record_tap")

        assert (idle.warn, idle.hold) == (False, False)
        assert (marking.warn, marking.hold) == (True, False)
        assert (repeating.warn, repeating.hold) == (False, True)

    def test_the_record_button_says_which_press_comes_next(self):
        for snippet_state, wanted in (("", "Record"), ("recording", "out point"),
                                   ("repeating", "drop it")):
            assert wanted in _button(_main_facts(main_mode=MainMode.KINO, snippet=snippet_state),
                                     "main_funestra_record_tap").tooltip


class TestLayout:
    def test_the_mode_pair_names_kino_and_genau(self):
        first = main_hud_rows(_main_facts())[0]

        assert [(b.command, b.icon, b.tooltip) for b in first[:2]] == [
            ("main_kino_activate", "Kino", ""), ("genau_activate", "Genau", "")]

    def test_the_mode_row_leads_so_it_holds_its_place_across_modes(self):
        for mode in MainMode:
            first = main_hud_rows(_main_facts(main_mode=mode))[0]
            assert [b.command for b in first][:3] == [
                "main_kino_activate", "genau_activate", "main_take_osr2"]

    def test_the_browse_rides_the_mode_row_in_both_modes_and_the_rest_only_over_a_video(self):
        video = [b.command for b in main_hud_rows(_main_facts(main_mode=MainMode.KINO))[0]]
        genau = [b.command for b in main_hud_rows(_main_facts(main_mode=MainMode.GENAU))[0]]

        assert video[-3:] == ["browse_library", "main_funestra_record_tap", "genaumacher_save"]
        assert genau[-1:] == ["browse_library"]

    def test_the_save_is_named_for_the_snippet_it_saves(self):
        assert _button(_main_facts(main_mode=MainMode.KINO), "genaumacher_save").tooltip == "Save snippet"

    def test_the_file_actions_stand_apart_from_the_crown_and_from_each_other(self):
        by_action = _placed(_main_facts(main_mode=MainMode.KINO))
        crown, browse = by_action["main_crown"], by_action["browse_library"]
        record, save = by_action["main_funestra_record_tap"], by_action["genaumacher_save"]

        assert browse[0] - (crown[0] + crown[2]) == GROUP_GAP
        assert record[0] - (browse[0] + browse[2]) == GROUP_GAP
        assert save[0] - (record[0] + record[2]) == GAP

    def test_the_crown_is_lit_while_the_main_funestra_holds_it(self):
        held = _button(_main_facts(crowned=True), "main_crown")
        given_away = _button(_main_facts(crowned=False), "main_crown")

        assert (held.lit, given_away.lit) == (True, False)
        assert held.tooltip.startswith("Crowned")

    def test_the_crown_sits_beside_minimize(self):
        by_action = _placed(_main_facts(main_mode=MainMode.KINO))
        minimize, crown = by_action["main_minimize"], by_action["main_crown"]

        assert crown[0] - (minimize[0] + minimize[2]) == GAP

    def test_minimize_rides_the_row_that_never_changes(self):
        video, genau = _placed(_main_facts(main_mode=MainMode.KINO)), _placed(_main_facts(main_mode=MainMode.GENAU))

        assert video["main_minimize"] == genau["main_minimize"]

    def test_minimize_stands_apart_from_skip_ahead_it_sits_beside(self):
        by_action = _placed(_main_facts(main_mode=MainMode.KINO))
        skip, minimize = by_action["main_funestra_funscript_jump"], by_action["main_minimize"]

        assert minimize[0] - (skip[0] + skip[2]) == GROUP_GAP

    def test_a_main_hud_in_the_headset_has_no_window_to_minimize(self):
        video = [b.command for b in main_hud_rows(_main_facts(main_mode=MainMode.KINO), in_vr=True)[0]]
        genau = [b.command for b in main_hud_rows(_main_facts(main_mode=MainMode.GENAU), in_vr=True)[0]
                 if not b.dim]

        assert video == ["main_kino_activate", "genau_activate", "main_take_osr2",
                         "main_prev", "main_nudge_prev", "main_nudge_next", "main_next",
                         "main_funestra_funscript_jump",
                         "browse_library", "main_funestra_record_tap", "genaumacher_save"]
        assert genau == ["main_kino_activate", "genau_activate", "main_take_osr2",
                         "genau_prev_flick", "genau_next_flick", "browse_library"]

    def test_minimize_this_funestra_wears_a_screen_with_an_arrow_not_the_huds_own_minus(self):
        button = _button(_main_facts(main_mode=MainMode.GENAU), "main_minimize")

        assert button.icon == shared_icon("screen_arrow_down")
        assert button.icon != hud_minimize.MINIMIZE_ICON
        assert "taskbar" in button.tooltip

    def test_a_press_finds_the_button_under_it_and_names_it(self):
        placed = place_rows(main_hud_rows(_main_facts(main_mode=MainMode.KINO)), x=0, y=0)
        rect = next(r for r, b in placed if b.command == "main_next")

        assert hit_test(placed, rect[0] + 1, rect[1] + 1) == "main_next"
        assert tooltip_at(placed, rect[0] + 1, rect[1] + 1) == "Next video"

    def test_the_buttons_are_the_familys_size(self):
        placed = place_rows(main_hud_rows(_main_facts(main_mode=MainMode.KINO)), x=0, y=0)

        assert all(rect[3] == BUTTON for rect, _b in placed)


class TestFaces:
    @staticmethod
    def _is_a_symbol_the_font_would_draw(face: str) -> bool:
        return len(face) == 1 and not face.isalnum()

    def test_no_buttons_face_is_a_symbol_the_font_draws(self):
        assert not {b.icon for b in _every_button() if self._is_a_symbol_the_font_would_draw(b.icon)}

    def test_every_mark_a_button_names_is_one_the_family_draws(self):
        named = {shared_icon_name(b.icon) for b in _every_button()
                 if b.icon.startswith(SHARED_ICON)}

        assert {"trash", "reset", "crown", "folder", "chevron_left", "lock"} <= named
        assert not named - set(icon_names())

    def test_the_bin_takes_something_away(self):
        assert _button(_main_facts(main_mode=MainMode.GENAU), "genau_trash_flick").danger is True


class TestOrientationPair:
    def _pair(self, main_mode=MainMode.KINO, *, things=None, **over) -> tuple[Button, ...]:
        rows = main_hud_rows(_main_facts(main_mode=main_mode, latest=False, **over))
        by_face = {b.icon: b for row in rows for b in row
                   if b.command.startswith("main_orientation")}
        return tuple(by_face[face] for face in (PORTRAIT_ICON, LANDSCAPE_ICON) if face in by_face)

    def test_they_wear_the_familys_portrait_and_landscape_marks(self):
        assert (shared_icon_name(PORTRAIT_ICON), shared_icon_name(LANDSCAPE_ICON)) == (
            "portrait", "landscape")
        assert {"portrait", "landscape"} <= set(icon_names())

    def test_both_lit_and_each_press_asks_for_the_other_alone(self):
        portrait, landscape = self._pair()

        assert (portrait.lit, landscape.lit) == (True, True)
        assert (portrait.command, landscape.command) == (
            "main_orientation_landscape", "main_orientation_portrait")

    def test_the_dark_one_asks_for_both_and_the_last_lit_one_for_neither(self):
        portrait, landscape = self._pair(plays_portrait=False)

        assert (portrait.lit, landscape.lit) == (False, True)
        assert (portrait.command, landscape.command) == (
            "main_orientation_both", "main_orientation_none")

    def test_they_lead_the_inclusion_pairs_right_after_the_browse_order_in_a_group_of_their_own(self):
        placed = place_rows(main_hud_rows(_main_facts(main_mode=MainMode.KINO, latest=False)), x=0, y=0)
        rect_of = {b.icon: rect for rect, b in placed}
        latest, portrait, landscape = rect_of[LATEST_ICON], rect_of[PORTRAIT_ICON], rect_of[LANDSCAPE_ICON]

        assert portrait[0] - (latest[0] + latest[2]) == GROUP_GAP
        assert landscape[0] - (portrait[0] + portrait[2]) == GAP

    def test_they_name_the_videos_and_the_flicks_where_the_other_pairs_do(self):
        assert {b.tooltip for b in self._pair()} == {
            "Including portrait videos", "Including landscape videos"}
        assert {b.tooltip for b in self._pair(MainMode.GENAU, plays_landscape=False)} == {
            "Including portrait pips", "Not including landscape pips"}

    def test_inside_a_compilation_they_read_as_held(self):
        pair = self._pair(compilation="Volume 6")

        assert pair
        assert all(b.remembered and not b.lit for b in pair)


def _window_buttons(funestra: str, *, in_vr: bool, crowned: bool) -> tuple[Button, ...]:
    return window_buttons(HudFacts(funestra=funestra, in_vr=in_vr, crowned=crowned))


def test_a_satellites_own_buttons_are_its_minimize_button_and_the_portraits_crown():
    portrait = _window_buttons("portrait", in_vr=False, crowned=False)

    assert [button.command for button in portrait] == ["portrait_minimize", "portrait_crown"]
    assert [button.icon for button in portrait] == [MINIMIZE_FUNESTRA_ICON, shared_icon("crown")]


def test_a_funestra_in_the_headset_has_no_window_to_minimize():
    assert _window_buttons("portrait", in_vr=True, crowned=False) == ()


def test_the_portrait_funestras_crown_is_lit_while_it_holds_the_crown():
    held = _window_buttons("portrait", in_vr=False, crowned=True)[-1]
    given_away = _window_buttons("portrait", in_vr=False, crowned=False)[-1]

    assert (held.command, held.lit, given_away.lit) == ("portrait_crown", True, False)
    assert held.tooltip.startswith("Crowned")


def test_only_the_portrait_funestra_wears_a_crown():
    assert [button.command for button in _window_buttons("landscape", in_vr=False, crowned=False)
            ] == ["landscape_minimize"]


SLIDESHOW_THE_ROW = [
    "prev", "nudge_prev", "nudge_next", "next", "funscript_jump", "trash", "lock", "fmode",
    "reset", "shuffle", "latest", "media_videos", "media_images", "enhancement_originals",
    "enhancement_enhanced", "cycle_version"]


def _slideshow_rows(shape: str = "portrait", *, favorites_filter: bool = False,
                    order: str = "", hosted: bool = True,
                    **fields) -> tuple[tuple[Button, ...], ...]:
    return hud_rows(HudKind.SLIDESHOW, HudFacts(
        funestra=shape, f_mode=favorites_filter, latest=order == LATEST_LABEL, hosted=hosted,
        **fields))


def _button_row(**fields) -> tuple:
    return _slideshow_rows("portrait", **fields)[-1]


def _names(buttons) -> list[str]:
    return [button.command.removeprefix("portrait_") for button in buttons]


def _by_name(**fields) -> dict:
    row = _button_row(**fields)
    return dict(zip(_names(row), row, strict=True))


def test_the_band_is_the_controls_a_slideshow_answers_in_the_funestras_order():
    assert _names(_button_row()) == SLIDESHOW_THE_ROW


def test_every_button_posts_that_sides_own_verb_and_names_itself():
    for shape in ("portrait", "landscape"):
        for button in _slideshow_rows(shape)[-1]:
            assert button.command.startswith(f"{shape}_"), button.command
            assert button.tooltip, button.command


def test_the_band_breaks_into_groups_where_the_controls_stop_being_about_one_thing():
    assert [name for name, button in zip(_names(_button_row()), _button_row(), strict=True) if button.group_break] == [
        "prev", "trash", "reset", "shuffle", "media_videos", "enhancement_originals",
        "cycle_version"]


def test_the_switches_light_and_the_things_done_never_do():
    row = _by_name(locked=True, favorites_filter=True)

    assert row["lock"].lit
    assert row["lock"].favorite
    assert row["fmode"].lit
    assert row["fmode"].favorite
    assert row["trash"].danger
    assert not any(row[name].lit for name in ("prev", "next", "trash", "reset"))
    at_rest = _by_name()
    assert not any(at_rest[name].lit for name in ("lock", "fmode"))


def _pair_buttons(row, word: str) -> tuple:
    return tuple(button for button in row if button.tooltip.endswith(word))


def test_each_pair_lights_the_kinds_it_includes():
    row = _button_row(media=(True, False), enhancement=(False, True))

    (images,) = _pair_buttons(row, " images")
    (videos,) = _pair_buttons(row, " videos")
    (enhanced,) = _pair_buttons(row, "enhanced items")
    (originals,) = _pair_buttons(row, "original items")
    assert [images.lit, videos.lit, enhanced.lit, originals.lit] == [True, False, False, True]
    at_rest = _button_row()
    assert all(button.lit for word in (" images", " videos", "enhanced items", "original items")
               for button in _pair_buttons(at_rest, word))


def test_the_enhanced_button_keeps_the_enhanced_color_and_the_originals_button_wears_none():
    row = _button_row()

    (enhanced,) = _pair_buttons(row, "enhanced items")
    (originals,) = _pair_buttons(row, "original items")
    assert (enhanced.enhanced, originals.enhanced) == (True, False)


def test_the_order_the_set_plays_in_is_the_one_lit_of_the_pair():
    for order, lit in ((SHUFFLE_LABEL, ["shuffle"]), (LATEST_LABEL, ["latest"])):
        row = _button_row(order=order)
        assert [name for name, button in zip(_names(row), row, strict=True)
                if name in ("shuffle", "latest") and button.lit] == lit, order


class TestSlideshowWords:

    def test_the_controls_both_modes_share_read_as_kino_reads_them(self):
        row = _by_name(has_other_versions=True)

        assert row["prev"].tooltip == "Previous slide"
        assert row["next"].tooltip == "Next slide"
        assert row["nudge_prev"].tooltip.startswith("Back 10s")
        assert row["nudge_next"].tooltip.startswith("Forward 10s")
        assert row["funscript_jump"].tooltip.startswith(
            "Skip ahead to where this slide's scripting starts up again")
        assert row["fmode"].tooltip == f"{F_MODE_LABEL} — browse only the favorites on this Funestra"
        assert row["shuffle"].tooltip == f"{SHUFFLE_LABEL} — reshuffle what plays"
        assert row["latest"].tooltip == f"{LATEST_LABEL} — reload it newest-first"
        assert row["cycle_version"].tooltip == "Another version of this slide"

    def test_each_pair_says_what_it_includes_as_two_d_and_vr_do(self):
        row = _by_name(media=(True, False), enhancement=(False, True))

        assert [row[name].tooltip for name in (
            "media_none", "media_both", "enhancement_both", "enhancement_none")] == [
            "Including images", "Not including videos", "Not including enhanced items",
            "Including original items"]

    def test_the_lock_and_the_trash_read_as_kinos_and_reset_says_what_it_does_here(self):
        row = _by_name()

        assert row["lock"].tooltip == lock_tooltip(False, "slide")
        assert row["trash"].tooltip == TRASH_TOOLTIP
        assert row["reset"].tooltip.startswith("Reset — ")


class TestSlideshowTheTenSecondSteps:
    def test_step_a_video_longer_than_ten_seconds(self):
        row = _by_name(longer_than_a_step=True)

        assert [row[step].dim for step in ("nudge_prev", "nudge_next")] == [False, False]

    def test_are_faded_on_a_video_of_ten_seconds_or_shorter_and_say_so(self):
        row = _by_name(longer_than_a_step=False)

        for step in ("nudge_prev", "nudge_next"):
            assert row[step].dim
            assert row[step].tooltip.endswith("(this slide is 10s or shorter)")

    def test_are_faded_on_an_image_and_say_so(self):
        row = _by_name(longer_than_a_step=True, image=True)

        for step in ("nudge_prev", "nudge_next"):
            assert row[step].dim
            assert row[step].tooltip.endswith(f"({AN_IMAGE})")


class TestSlideshowSkipAhead:
    def test_is_live_with_the_osr2_on_this_funestra_and_a_funscript_on_screen(self):
        assert not _by_name(has_osr2=True, has_funscript=True)["funscript_jump"].dim

    @pytest.mark.parametrize(("has_osr2", "has_funscript", "why"), [
        (False, True, "this Funestra doesn't have the OSR2"),
        (True, False, "this slide has no funscript"),
        (False, False, "this Funestra doesn't have the OSR2 and this slide has no funscript"),
    ])
    def test_is_faded_without_the_osr2_or_a_funscript_and_says_which(
            self, has_osr2, has_funscript, why):
        jump = _by_name(has_osr2=has_osr2, has_funscript=has_funscript)["funscript_jump"]

        assert jump.dim
        assert jump.tooltip.endswith(f"({why})")


def test_reset_is_faded_with_nothing_to_put_back():
    assert _by_name(nothing_to_reset=True)["reset"].dim
    assert not _by_name(nothing_to_reset=False)["reset"].dim


def test_a_slideshow_on_its_own_puts_the_transport_and_minimize_on_a_top_row_of_their_own():
    top, second = hud_rows(HudKind.SLIDESHOW, HudFacts(funestra="portrait", crowned=True, latest=False))

    assert _names(top) == ["prev", "nudge_prev", "nudge_next", "next", "funscript_jump", "minimize"]
    assert _names(second) == SLIDESHOW_THE_ROW[5:]


def test_a_slideshow_on_its_own_in_the_headset_has_no_minimize():
    top = hud_rows(HudKind.SLIDESHOW, HudFacts(funestra="portrait", in_vr=True))[0]

    assert "minimize" not in _names(top)


def test_a_hosted_slideshow_declares_its_band_and_nothing_around_it():
    rows = _slideshow_rows("portrait", hosted=True)

    assert len(rows) == 1
    assert _names(rows[0]) == SLIDESHOW_THE_ROW


def test_the_versions_button_is_dim_where_the_item_has_only_itself():
    assert _by_name()["cycle_version"].dim
    assert not _by_name(has_other_versions=True)["cycle_version"].dim


def test_reset_says_what_the_side_goes_back_to_where_it_is_being_shown():
    hosted = next(b for b in _button_row(hosted=True) if b.command == "portrait_reset")
    alone = next(b for b in _button_row(hosted=False) if b.command == "portrait_reset")

    assert "library" in hosted.tooltip
    assert "library" not in alone.tooltip


def test_reset_says_the_speed_goes_back_in_the_words_kinos_reset_uses():
    hosted = next(b for b in _button_row(hosted=True) if b.command == "portrait_reset")
    alone = next(b for b in _button_row(hosted=False) if b.command == "portrait_reset")

    assert RESET_PUTS_BACK_THE_SPEED in hosted.tooltip
    assert RESET_PUTS_BACK_THE_SPEED in alone.tooltip


def test_the_clip_seconds_and_the_playback_speed_share_one_row():
    *_rows, shared = _slideshow_rows("portrait", clip_seconds=4)

    assert [button.command or button.icon for button in shared] == [
        "Clip seconds", "portrait_clip_seconds_down", "4s", "portrait_clip_seconds_up",
        "Playback speed", "portrait_speed_down", "", "portrait_speed_up"]
    assert shared == clip_seconds_row("portrait", 4)


def test_each_name_on_that_row_keeps_its_controls_close_and_the_second_pair_stands_apart_from_the_first():
    *_rows, shared = _slideshow_rows("portrait", clip_seconds=4)
    clip_seconds, *_controls, playback_speed, _slower, _rate, _faster = shared

    assert [button.group_break for button in shared] == [
        False, False, False, False, True, False, False, False]
    assert (clip_seconds.width, playback_speed.width) == (FIT_THE_WORD, FIT_THE_WORD)


def _commands(row) -> list[str]:
    return [button.command for button in row]


def test_the_main_funestras_top_row_holds_the_modes_the_osr2_button_and_the_transport():
    top = hud_rows(HudKind.MAIN, _main_facts(main_mode=MainMode.KINO))[0]

    assert _commands(top) == [
        "main_kino_activate", "genau_activate", "main_take_osr2",
        "main_prev", "main_nudge_prev", "main_nudge_next", "main_next",
        "main_funestra_funscript_jump", "main_minimize", "main_crown",
        "browse_library", "main_funestra_record_tap", "genaumacher_save"]


def test_genau_shows_kinos_skip_buttons_and_funscript_jump_dimmed_in_their_places():
    kino = _placed(_main_facts(main_mode=MainMode.KINO))
    genau_facts = _main_facts(main_mode=MainMode.GENAU)
    genau = _placed(genau_facts)
    shown = {b.command: b for b in hud_rows(HudKind.MAIN, genau_facts)[0]}

    for kinos, genaus in (("main_prev", "genau_prev_flick"), ("main_nudge_prev", "genau_nudge_prev"),
                          ("main_nudge_next", "genau_nudge_next"), ("main_next", "genau_next_flick"),
                          ("main_funestra_funscript_jump", "genau_funscript_jump")):
        assert genau[genaus][0] == kino[kinos][0], genaus
    for dimmed in ("genau_nudge_prev", "genau_nudge_next", "genau_funscript_jump"):
        assert shown[dimmed].dim
        assert "not in Genau" in shown[dimmed].tooltip
    assert not shown["genau_next_flick"].dim


def test_a_satellites_top_row_starts_with_the_osr2_button_then_the_transport():
    top = hud_rows(HudKind.SATELLITE, HudFacts(funestra="portrait", has_osr2=True))[0]

    assert _commands(top) == [
        "portrait_take_osr2", "portrait_prev", "portrait_nudge_prev", "portrait_nudge_next",
        "portrait_next", "portrait_funscript_jump", "portrait_minimize", "portrait_crown"]
    assert top[0].lit


def test_in_the_headset_the_top_row_ends_after_skip_ahead():
    top = hud_rows(HudKind.SATELLITE, HudFacts(funestra="landscape", in_vr=True))[0]

    assert _commands(top)[-1] == "landscape_funscript_jump"



def test_trash_sits_right_before_the_lock_so_the_lock_and_f_mode_stay_neighbors():
    for kind, facts in ((HudKind.SATELLITE, HudFacts(funestra="portrait")),
                        (HudKind.SLIDESHOW, HudFacts(funestra="portrait")),
                        (HudKind.MAIN, _main_facts(main_mode=MainMode.GENAU))):
        commands = [command for row in hud_rows(kind, facts) for command in _commands(row)]
        lock = next(index for index, command in enumerate(commands) if command.endswith("_lock"))
        assert "trash" in commands[lock - 1], (kind, commands)
        assert commands[lock + 1].endswith("_fmode"), (kind, commands)


def test_every_row_label_is_only_as_wide_as_its_words():
    for kind, facts in ((HudKind.MAIN, _main_facts(main_mode=MainMode.KINO)),
                        (HudKind.MAIN, _main_facts(main_mode=MainMode.GENAU)),
                        (HudKind.SATELLITE, HudFacts(funestra="portrait", clip_seconds=4))):
        labels = [button for row in hud_rows(kind, facts) for button in row
                  if button.is_a_name and not button.command and button.icon]
        assert labels, kind
        assert all(label.width == FIT_THE_WORD for label in labels), kind


def _title(*, block: ModeHud | None = None, **facts) -> str:
    return main_title(HudFacts(**{"locked": True, "latest": False, **facts}), block or ModeHud())


class TestTheMainFunestrasTitle:
    def test_says_whether_the_main_funestra_is_holding_the_video_on_screen(self):
        assert _title(locked=True) == "Locked · Shuffle"
        assert _title(locked=False) == "Unlocked · Shuffle"

    def test_says_the_length_mode_last_and_nothing_for_mixed(self):
        assert _title(length_mode=LengthMode.MIXED) == "Locked · Shuffle"
        assert _title(length_mode=LengthMode.FULL) == "Locked · Shuffle · Full"
        assert _title(length_mode=LengthMode.CLIPS) == "Locked · Shuffle · Clips"

    def test_a_genau_main_funestra_says_its_order_and_the_pace_it_moves_at_while_unlocked(self):
        def line(**over) -> str:
            return _title(main_mode=MainMode.GENAU, pace_s=5, **over)

        assert line(locked=False) == "Unlocked · Shuffle · 5s"
        assert line(locked=True) == "Locked · Shuffle"
        assert line(locked=False, latest=True) == "Unlocked · Latest · 5s"

    def test_the_pace_belongs_to_genau_and_is_not_claimed_in_kino(self):
        assert _title(locked=False, pace_s=5) == "Unlocked · Shuffle"

    def test_a_host_with_no_browse_order_names_none(self):
        assert _title(main_mode=MainMode.GENAU, latest=None) == "Locked"

    def test_names_the_compilation_and_where_you_are_in_it(self):
        block = ModeHud(compilation="Example Set - Vol6 (v2)", position=9, total=20)

        assert _title(block=block, locked=False) == "Vol6 · 9/20 · Shuffle"
        assert _title(block=block, locked=True) == "Vol6 · 9/20 · Locked · Shuffle"

    def test_says_when_the_library_is_narrowed_to_f_mode(self):
        assert _title(block=ModeHud(scripted_filter=True)) == "Locked · Shuffle · F-mode"


def test_a_compilations_title_keeps_only_its_volume():
    assert compilation_label("various - Example Studio Alpha Collection - Volume 6 (v1)") == "Volume 6"
    assert compilation_label("Scene Five 3") == "Scene Five 3"


def test_a_slideshows_title_says_its_loop_its_hold_its_order_and_what_it_narrows_to():
    facts = HudFacts(funestra="portrait", locked=False, latest=True, f_mode=True,
                     media=(False, True), enhancement=(True, True))

    assert slideshow_title(facts, loop="seed", action_filter="alpha") == (
        "Looping seeds · Latest · F-mode · Videos · alpha")


def test_every_title_a_kind_of_hud_can_show_is_among_its_choices_but_the_unbounded_parts():
    shown = main_title(HudFacts(main_mode=MainMode.GENAU, locked=False, latest=False, pace_s=99,
                                f_mode=True, plays_vr=True, plays_flat=False,
                                plays_portrait=False), ModeHud(scripted_filter=True))

    assert shown in title_choices(HudKind.MAIN)
    assert slideshow_title(HudFacts(locked=True, latest=False, media=(True, False)),
                           loop="action") in title_choices(HudKind.SATELLITE)


def _second_row(**facts) -> tuple[Button, ...]:
    return hud_rows(HudKind.MAIN, _main_facts(latest=False, **facts))[1]


def test_portrait_and_landscape_lead_the_inclusion_pairs_then_2d_and_vr_in_both_modes():
    for mode in MainMode:
        commands = _commands(_second_row(main_mode=mode, plays_vr=True, plays_flat=True))
        orientation = commands.index("main_orientation_landscape")
        assert commands[orientation + 2:orientation + 4] == [
            "main_projection_vr", "main_projection_flat"], (mode, commands)


def test_a_library_of_one_kind_shows_the_2d_and_vr_pair_dimmed_rather_than_leaving_it_out():
    for mode in MainMode:
        shown = {b.command: b for b in _second_row(main_mode=mode, plays_vr=None, plays_flat=None)}
        assert shown["main_projection_vr"].dim, mode
        assert shown["main_projection_flat"].dim, mode


def test_genaus_flip_ends_its_row():
    assert _commands(_second_row(main_mode=MainMode.GENAU))[-1] == "genau_flip_ends"


def test_compilation_full_scene_and_versions_close_kinos_row_as_one_group():
    row = _second_row(main_mode=MainMode.KINO)
    last_three = row[-3:]

    assert [b.command for b in last_three] == [
        "main_funestra_compilation", "main_funestra_clip_jump", "main_funestra_cycle_version"]
    assert [b.group_break for b in last_three] == [True, False, False]


def test_trash_and_the_lock_touch_with_no_gap_between_them():
    for kind, facts in ((HudKind.SATELLITE, HudFacts(funestra="portrait")),
                        (HudKind.MAIN, _main_facts(main_mode=MainMode.GENAU))):
        row = hud_rows(kind, facts)[1]
        lock = next(index for index, b in enumerate(row) if b.command.endswith("_lock"))
        assert "trash" in row[lock - 1].command
        assert not row[lock].group_break, kind


def _trash_of(kind: HudKind, facts: HudFacts) -> Button:
    return next(b for row in hud_rows(kind, facts) for b in row if "trash" in b.command)


_EVERY_TRASH = ((HudKind.MAIN, _main_facts(main_mode=MainMode.KINO), "main_trash"),
                (HudKind.MAIN, _main_facts(main_mode=MainMode.GENAU), "genau_trash_flick"),
                (HudKind.SATELLITE, HudFacts(funestra="portrait"), "portrait_trash"),
                (HudKind.SLIDESHOW, HudFacts(funestra="landscape"), "landscape_trash"))


def test_every_hud_has_a_trash_kino_on_the_main_funestra_included():
    for kind, facts, command in _EVERY_TRASH:
        assert _trash_of(kind, facts).command == command
        assert _trash_of(kind, facts).icon == shared_icon("trash")


def test_on_a_favorite_every_trash_becomes_the_star_struck_through_posting_the_same_verb():
    for kind, facts, command in _EVERY_TRASH:
        button = _trash_of(kind, replace(facts, favorite=True))
        assert button.command == command
        assert button.icon == UNFAVORITE_ICON
        assert button.tooltip.startswith("Unfavorite")


def test_genau_has_a_reset_that_puts_everything_back():
    reset = next(b for b in _second_row(main_mode=MainMode.GENAU) if b.command == "genau_reset")

    assert reset.tooltip.startswith("Reset")
    assert next(b for b in _second_row(main_mode=MainMode.GENAU, nothing_to_reset=True)
                if b.command == "genau_reset").dim


def test_every_button_kino_and_genau_share_sits_in_the_same_place_in_both():
    def placed(mode):
        row = _second_row(main_mode=mode, plays_vr=True, plays_flat=True)
        return {short: rect for rect, b in place_rows([list(row)], x=0, y=0)
                for short in (b.command.removeprefix("main_").removeprefix("genau_"),)}

    kino, genau = placed(MainMode.KINO), placed(MainMode.GENAU)
    kino["trash_flick"] = kino.pop("trash")
    shared = {"trash_flick", "lock", "fmode", "reset", "shuffle", "latest",
              "orientation_portrait", "orientation_landscape", "projection_vr", "projection_flat"}

    assert {name: kino[name][0] for name in shared} == {name: genau[name][0] for name in shared}


def test_genaus_stroke_seconds_follow_the_playback_speed_on_kinos_speed_row():
    kino = hud_rows(HudKind.MAIN, _main_facts(main_mode=MainMode.KINO))[-1]
    genau = hud_rows(HudKind.MAIN, _main_facts(main_mode=MainMode.GENAU))[-1]

    assert _commands(genau)[:len(kino)] == _commands(kino)
    assert genau[len(kino)].icon == "Pip seconds"
    assert genau[len(kino)].group_break
