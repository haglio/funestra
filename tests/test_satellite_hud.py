from __future__ import annotations

import json
import math

from satellite_rows import bar, funestra_rows
from shared_ui.icon_geometry import tooltip_for
from shared_ui.spacing import BUTTON_GAP, BUTTON_GROUP_GAP
from shared_ui.testing import icons_lacking
from shared_ui.type_scale import SIZE_BODY, SIZE_SMALL, SIZE_TINY

from funestra import satellite_hud
from funestra.hud import load_font
from funestra.hud_button import Button
from funestra.hud_icons import MINIMIZE_ICON, shared_icon
from funestra.hud_placement import HudCorner, HudEdge
from funestra.main_hud import OSR2_PARKED, VALUE_W
from funestra.modes import Osr2State
from funestra.satellite_hud import (
    CTRL_BTN,
    ELLIPSIS,
    FILTER_BTN,
    LOOP_BTN,
    NAV_MAP_CELLS,
    NAV_MAP_GAP,
    PAD,
    ROW_GAP,
    TITLE_X,
    HudCell,
    HudModel,
    HudTargets,
    NavMapRects,
    PaintedFoot,
    act_is_filtered,
    action_label_blocks,
    build_click_targets,
    button_row_rects,
    ellipsis_rects,
    expand_button_rect,
    filter_button_rects,
    hit_test_targets,
    hud_text,
    hud_width,
    label_is_filtered,
    largest_size_that_fits,
    loop_button_rects,
    looped_group_rect,
    name_line,
    nav_map_row_width,
    nav_map_window,
    parse_hud,
    place_rects,
    place_width,
    speed_row,
    thumbnail_rect,
)
from funestra.satellite_hud_clicks import DOUBLE_CLICK_S, HudClicks, button_tooltip

CAMERA_WORDS = ("Side", "XYZ")


def _squares(x: int, y: int, buttons) -> list:
    return button_row_rects(x, y, buttons, [CTRL_BTN] * len(buttons))


def test_the_hud_is_as_wide_as_its_nav_map_or_its_file_name_whichever_asks_for_more():
    for_nav_map = hud_width("portrait")
    room = for_nav_map - TITLE_X - PAD

    assert hud_width("portrait", name_width=room) == for_nav_map
    assert hud_width("portrait", name_width=room + 20) == for_nav_map + 20


def test_a_text_naming_no_funestra_is_not_a_hud():
    assert parse_hud('{"player": "landscape"}') is None


def test_parse_hud_reads_whether_this_side_has_the_floor():
    assert parse_hud(json.dumps({"funestra": "portrait", "active": True})).active is True
    assert parse_hud(json.dumps({"funestra": "portrait", "active": False})).active is False
    assert parse_hud(json.dumps({"funestra": "portrait"})).active is False


def test_parse_hud_reads_the_hud_fun_time_published():
    text = json.dumps({
        "funestra": "portrait",
        "locked": True,
        "title": "Locked · Shuffle · alpha",
        "active_loop": "seed",
        "playing": ["seed", 1],
        "current_action": "alpha",
        "corner": {"path": "C:/v/cur.mp4", "thumb": "C:/t/cur.jpg"},
        "seeds": [{"path": "C:/v/s1.mp4", "thumb": "C:/t/s1.jpg"}],
        "actions": [{"path": "C:/v/a1.mp4", "thumb": "C:/t/a1.jpg", "label": "gamma"}],
    })

    model = parse_hud(text)

    assert model is not None
    assert model.funestra == "portrait"
    assert model.locked is True
    assert model.title == "Locked · Shuffle · alpha"
    assert model.active_loop == "seed"
    assert model.playing == ("seed", 1)
    assert model.current_action == "alpha"
    assert model.corner == HudCell(path="C:/v/cur.mp4", thumb="C:/t/cur.jpg")
    assert model.seeds == (HudCell(path="C:/v/s1.mp4", thumb="C:/t/s1.jpg"),)
    assert model.actions == (HudCell(path="C:/v/a1.mp4", thumb="C:/t/a1.jpg", label="gamma"),)


def test_parse_hud_reads_whether_the_clip_is_a_favorite():
    assert parse_hud(json.dumps({"funestra": "portrait", "is_favorite": True})).is_favorite is True
    assert parse_hud(json.dumps({"funestra": "portrait"})).is_favorite is False


def test_parse_hud_defaults_an_empty_hud():
    model = parse_hud(json.dumps({"funestra": "landscape", "locked": False, "title": "Unlocked"}))

    assert model is not None
    assert model.corner is None
    assert model.seeds == ()
    assert model.actions == ()
    assert model.playing == ("corner", 0)


def test_parse_hud_rejects_garbage():
    assert parse_hud('{"funestra": "portrait"') is None
    assert parse_hud("") is None


_LOOP = 12


def test_a_loop_short_enough_to_fit_is_drawn_whole():
    window = nav_map_window(NAV_MAP_CELLS, playing=0)

    assert (window.start, window.count) == (0, NAV_MAP_CELLS)
    assert window.more_before is False
    assert window.more_after is False


def test_a_loop_just_started_opens_on_the_clip_on_screen():
    window = nav_map_window(_LOOP, playing=0)

    assert (window.start, window.count) == (0, NAV_MAP_CELLS)
    assert window.more_after is True
    assert window.more_before is False


def test_a_loop_partway_through_keeps_the_clip_on_screen_in_the_middle():
    window = nav_map_window(_LOOP, playing=5)

    assert (window.start, window.count) == (4, 3)
    assert window.more_before is True
    assert window.more_after is True


def test_a_loop_near_its_end_clamps_rather_than_running_off():
    window = nav_map_window(_LOOP, playing=11)

    assert (window.start, window.count) == (9, 3)
    assert window.more_before is True
    assert window.more_after is False


def test_an_axis_shorter_than_the_window_gives_only_what_it_has():
    window = nav_map_window(2, playing=0)

    assert (window.start, window.count) == (0, 2)
    assert window.more_after is False


def test_an_empty_axis_has_no_window():
    window = nav_map_window(0, playing=0)

    assert (window.start, window.count) == (0, 0)


def _filter_targets(*labels: str) -> HudTargets:
    return HudTargets(
        click=[], loop=[],
        filter=[((0, i * 20, 18, 20), label) for i, label in enumerate(labels)],
        expand=None,
    )


def test_pressing_a_rows_filter_button_filters_the_side_to_its_act():
    clicks = HudClicks("portrait")

    assert clicks.press(_filter_targets("Theta Motion"), 5, 5, now=0.0) == "filter_portrait_theta_motion"


def test_pressing_the_lit_filter_button_turns_the_filter_off():
    clicks = HudClicks("portrait")
    clicks.active_filter = "alpha"

    assert clicks.press(_filter_targets("Alpha"), 5, 5, now=0.0) == "portrait_no_filter"


def test_pressing_another_rows_filter_button_while_filtered_moves_the_filter():
    clicks = HudClicks("portrait")
    clicks.active_filter = "alpha"

    assert clicks.press(_filter_targets("Gamma"), 5, 5, now=0.0) == "filter_portrait_gamma"


def test_pressing_a_partly_matching_button_narrows_the_filter_before_lifting_it():
    clicks = HudClicks("portrait")
    clicks.active_filter = "gamma"

    assert clicks.press(_filter_targets("Side Gamma"), 5, 5, now=0.0) == "filter_portrait_side_gamma"
    assert clicks.active_filter == "side gamma"
    assert clicks.press(_filter_targets("Side Gamma"), 5, 5, now=1.0) == "portrait_no_filter"


def test_pressing_a_two_act_rows_button_filters_to_both_of_its_acts():
    clicks = HudClicks("portrait")

    command = clicks.press(_filter_targets("Gamma, Theta Motion"), 5, 5, now=0.0)

    assert command == "filter_portrait_gamma,_theta_motion"
    assert clicks.press(_filter_targets("Gamma, Theta Motion"), 5, 5, now=1.0) == "portrait_no_filter"


def test_slot_rects_lays_the_row_and_the_column_out_in_fixed_slots_three_to_a_side():
    corner, seeds, actions, _column = place_rects(origin=(100, 50), place_w=30, seeds=5, actions=5)

    assert corner == (100, 50, 30, 54)
    assert seeds == [(100 + 30 + NAV_MAP_GAP, 50, 30, 54), (100 + 2 * (30 + NAV_MAP_GAP), 50, 30, 54)]
    assert actions == [(100, 50 + 54 + ROW_GAP, 30, 54), (100, 50 + 2 * (54 + ROW_GAP), 30, 54)]


def test_slot_rects_draws_only_the_slots_an_axis_has_clips_for():
    _corner, seeds, actions, _column = place_rects(origin=(0, 0), place_w=30, seeds=1, actions=0)

    assert len(seeds) == 1
    assert actions == []


def test_the_action_column_hangs_under_the_playing_seed():
    _corner, seeds, actions, _column = place_rects(origin=(100, 50), place_w=30, seeds=2, actions=2,
                                         playing=("seed", 0))

    assert [x for x, _y, _w, _h in actions] == [seeds[0][0]] * 2


def test_the_column_stays_under_the_corner_off_the_seed_row():
    for playing in (("corner", 0), ("action", 0)):
        _corner, _seeds, actions, _column = place_rects(origin=(100, 50), place_w=30, seeds=1,
                                              actions=1, playing=playing)
        assert actions[0][0] == 100


def test_a_playing_seed_that_was_not_drawn_leaves_the_column_on_the_corner():
    _corner, _seeds, actions, _column = place_rects(origin=(100, 50), place_w=30, seeds=1, actions=1,
                                          playing=("seed", 5))

    assert actions[0][0] == 100


def test_a_column_under_the_rows_last_seed_ends_where_the_row_does():
    _corner, seeds, actions, _column = place_rects(origin=(0, 0), place_w=place_width("portrait"),
                                         seeds=2, actions=1, playing=("seed", 1))
    ax, _ay, aw, _ah = actions[0]

    assert ax + aw == seeds[-1][0] + seeds[-1][2] == nav_map_row_width("portrait")


def test_a_thumbnail_stands_in_the_middle_of_its_slot():
    assert thumbnail_rect((100, 50, 44, 54), (30, 54)) == (107, 50, 30, 54)
    assert thumbnail_rect((100, 50, 44, 54), (44, 24)) == (100, 65, 44, 24)


def test_the_columns_chrome_follows_it_under_the_playing_seed():
    corner = (10, 10, 20, 20)
    column = (40, 10, 24, 20)
    actions = [(40, 42, 24, 20)]

    loop_action, _loop_seed = loop_button_rects(
        corner, row_end=300, column_end=250, column_rect=column)
    assert loop_action == (40, 250 + NAV_MAP_GAP, 24, LOOP_BTN)

    rects = NavMapRects(corner, [column], actions, column)
    rect = looped_group_rect(rects, "action")
    assert rect == (40, 10, 24, (42 + 20) - 10)

    before, after = ellipsis_rects(rects, "action")
    assert before == (40, 10 - NAV_MAP_GAP - ELLIPSIS, 24, ELLIPSIS)
    assert after == (40, 42 + 20 + NAV_MAP_GAP, 24, ELLIPSIS)


def test_the_loop_buttons_stand_past_the_rows_and_the_columns_fixed_ends():
    corner = (10, 10, 20, 20)
    loop_action, loop_seed = loop_button_rects(corner, row_end=150, column_end=180, reserve=7)

    assert loop_action == (10, 180 + 7 + NAV_MAP_GAP, 20, LOOP_BTN)
    assert loop_seed == (150 + 7 + NAV_MAP_GAP, 10, LOOP_BTN, 20)
    assert loop_button_rects(None, row_end=150, column_end=180) == (None, None)


def test_expand_button_sits_in_the_row_right_of_the_seed_loop_button():
    loop_seed = (60, 10, 18, 30)

    assert expand_button_rect(loop_seed) == (60 + 18 + NAV_MAP_GAP, 10, LOOP_BTN, 30)
    assert expand_button_rect(None) is None


def test_build_and_hit_test_click_targets():
    corner = (10, 10, 20, 20)
    seeds = [(40, 10, 20, 20)]
    actions = [(10, 40, 20, 20)]

    targets = build_click_targets(
        NavMapRects(corner, seeds, actions),
        HudModel(funestra="portrait", corner=HudCell(path="cur.mp4"),
                 seeds=(HudCell(path="s1.mp4"),), actions=(HudCell(path="a1.mp4"),)),
    )

    assert targets == [
        ((10, 10, 20, 20), "cur.mp4"),
        ((40, 10, 20, 20), "s1.mp4"),
        ((10, 40, 20, 20), "a1.mp4"),
    ]
    assert hit_test_targets(targets, 15, 15) == "cur.mp4"
    assert hit_test_targets(targets, 45, 15) == "s1.mp4"
    assert hit_test_targets(targets, 15, 45) == "a1.mp4"
    assert hit_test_targets(targets, 100, 100) == ""


def test_build_click_targets_skips_a_missing_corner():
    assert build_click_targets(NavMapRects(None, [], []), HudModel(funestra="portrait")) == []


def test_filter_button_rects_puts_one_at_the_head_of_each_row():
    corner = (60, 50, 30, 54)
    actions = [(60, 110, 30, 54), (60, 170, 30, 54)]

    rects = filter_button_rects(
        corner, actions, gutter_x=10,
        current_action="Alpha", action_labels=["Gamma", ""],
    )

    assert rects == [((10, 50, FILTER_BTN, 54), "Alpha"), ((10, 110, FILTER_BTN, 54), "Gamma")]
    assert filter_button_rects(None, [], 10, "", []) == []


def test_label_is_filtered_reads_a_filter_the_way_fun_time_applies_it_but_for_the_empty_filter_which_lights_no_row_here_with_fun_time_s_tests_holding_the_two_in_step():
    cases = [
        ("Gamma", "gamma", True),
        ("Side Gamma", "gamma", True),
        ("Side Gamma", "side gamma", True),
        ("Gamma, Theta", "gamma", True),
        ("Gamma   Theta", "gamma theta", True),
        ("Gamma, Theta", "gamma, theta", True),
        ("Gamma", "gamma, theta", False),
        ("Alpha", "gamma", False),
        ("Gam", "gamma", False),
    ]
    for label, query, expected in cases:
        assert label_is_filtered(label, query, CAMERA_WORDS) is expected, (label, query)

    assert label_is_filtered("Gamma", "", CAMERA_WORDS) is False


def test_act_is_filtered_picks_out_which_of_a_rows_acts_the_filter_named():
    def lit(act: str, filter_query: str) -> bool:
        return act_is_filtered(act, filter_query, CAMERA_WORDS)

    assert lit("Gamma", "gamma") is True
    assert lit("XYZ", "gamma") is False
    assert lit("Side", "gamma") is False
    assert lit("Theta Gamma", "gamma") is True
    assert lit("Gamma", "gamma, theta") is True
    assert lit("Theta", "gamma, theta") is True
    assert lit("Alpha", "gamma, theta") is False
    assert lit("Gamma", "xyz gamma") is True
    assert lit("XYZ", "xyz gamma") is True
    assert lit("Gamma", "") is False


def test_button_tooltip_names_each_button_probed_where_it_was_laid_out_since_the_bar_is_broken_into_groups_and_named_since_its_face_carries_no_word_and_a_painted_hud_has_no_other_tooltip():
    targets = HudTargets(
        click=[],
        loop=[((0, 0, 20, 20), "action"), ((30, 0, 20, 20), "seed")],
        filter=[((0, 100, FILTER_BTN, 54), "gamma")],
        expand=(30, 30, 18, 18),
        buttons=_squares(0, 60, bar(newest=False)),
        favorite=(300, 60, CTRL_BTN, CTRL_BTN),
    )

    assert button_tooltip(targets, 5, 5) == "Loop this action column"
    assert button_tooltip(targets, 35, 5) == "Loop this seed row"
    assert button_tooltip(targets, 5, 105) == "Filter to this action"
    assert button_tooltip(targets, 35, 35) == "More seeds — widen the net"
    for (bx, by, _w, _h), button in targets.buttons:
        assert button_tooltip(targets, bx + 5, by + 5) == button.tooltip
    assert button_tooltip(targets, 305, 65) == "In the favorites"
    assert button_tooltip(targets, 400, 400) == ""


def test_a_declared_button_wearing_a_mark_this_version_lacks_says_why_on_hover():
    auto = Button("auto", shared_icon("a_mark_from_another_version"), "Generate on its own")

    targets = _targets(buttons=_squares(0, 0, (auto,)))

    assert button_tooltip(targets, 5, 5) == auto.tooltip_on_hover


def test_the_nav_map_s_own_controls_say_why_when_this_version_lacks_their_marks():
    targets = _targets(loop=[((0, 0, 20, 20), "action")], wrong_action=(30, 0, 20, 20),
                       expand=(60, 0, 20, 20), favorite=(90, 0, 20, 20))

    with icons_lacking("loop", "cross", "expand_horizontal", "star"):
        assert [button_tooltip(targets, x + 5, 5) for x in (0, 30, 60, 90)] == [
            tooltip_for("loop", "Loop this action column"),
            tooltip_for("cross", "Wrong action — strike it, and it gets asked about again"),
            tooltip_for("expand_horizontal", "More seeds — widen the net"),
            tooltip_for("star", "In the favorites"),
        ]


def test_a_declared_row_is_laid_out_as_wide_as_each_button_says():
    rects = button_row_rects(10, 40, (
        Button("go_kino", "Kino", "Kino mode", width=0),
        Button("go_shows", "Origenerator", "Origenerator mode", width=0),
        Button("park", MINIMIZE_ICON, "Park it", group_break=True),
    ), [52, 90, CTRL_BTN])

    assert [rect for rect, _button in rects] == [
        (10, 40, 52, CTRL_BTN),
        (10 + 52 + BUTTON_GAP, 40, 90, CTRL_BTN),
        (10 + 52 + BUTTON_GAP + 90 + BUTTON_GROUP_GAP, 40, CTRL_BTN, CTRL_BTN),
    ]


def test_the_speed_row_puts_slower_the_rate_and_faster_after_its_name():

    buttons, rate = speed_row("portrait", 10, 40, label_width=70)

    assert [button.command for _rect, button in buttons] == [
        "portrait_speed_down", "portrait_speed_up"]
    (down, _), (up, _) = buttons
    assert down == (80, 40, CTRL_BTN, CTRL_BTN)
    assert rate == (80 + CTRL_BTN + NAV_MAP_GAP, 40, VALUE_W, CTRL_BTN)
    assert up == (rate[0] + VALUE_W + NAV_MAP_GAP, 40, CTRL_BTN, CTRL_BTN)


def test_the_speed_buttons_say_what_a_press_does_to_the_video_in_the_words_the_main_funestra_s_speed_pair_uses():
    buttons, _rate = speed_row("landscape", 0, 0, label_width=70)
    targets = _targets(buttons=buttons)

    assert [button_tooltip(targets, x + 5, y + 5) for (x, y, _w, _h), _b in buttons] == [
        "Play the video slower", "Play the video faster"]


def test_the_speed_buttons_wear_the_familys_minus_and_plus():
    buttons, _rate = speed_row("landscape", 0, 0, label_width=70)

    assert [button.icon for _rect, button in buttons] == [shared_icon("minus"), shared_icon("plus")]


_NOTE = "Enhancing…"


def test_a_name_too_long_for_its_line_is_shortened_so_the_note_after_it_stays_whole():
    font = load_font(SIZE_TINY)
    shortened = f"folder one … · {_NOTE}"

    line = name_line("folder one / seed 12345", _NOTE, math.ceil(font.getlength(shortened)), font)

    assert line == shortened


def test_a_name_and_a_note_that_fit_their_line_are_left_whole():
    assert name_line("clip", _NOTE, 1000, load_font(SIZE_TINY)) == f"clip · {_NOTE}"


def test_a_name_with_no_note_after_it_is_left_whole_however_long():
    assert name_line("a long name " * 5, "", 10, load_font(SIZE_TINY)) == "a long name " * 5


def test_a_note_with_no_name_before_it_stands_alone():
    assert name_line("", _NOTE, 1000, load_font(SIZE_TINY)) == _NOTE


def test_a_note_too_long_to_leave_any_of_the_name_stands_alone():
    font = load_font(SIZE_TINY)

    assert name_line("clip", _NOTE, math.floor(font.getlength(_NOTE)), font) == _NOTE


def test_a_title_that_fits_keeps_its_full_size():
    assert largest_size_that_fits(11, room=100, width_at=lambda size: 5 * size) == 11


def test_a_title_too_wide_takes_the_largest_of_the_familys_sizes_that_fits():
    assert largest_size_that_fits(SIZE_BODY, room=50, width_at=lambda size: 5 * size) == SIZE_SMALL


def test_a_title_that_fits_at_none_of_the_familys_sizes_takes_the_tiny_one():
    assert largest_size_that_fits(SIZE_BODY, room=3, width_at=lambda size: 5 * size) == SIZE_TINY


def test_action_label_blocks_separate_comma_joined_acts():
    assert action_label_blocks("alpha, theta motion", CAMERA_WORDS) == [["Alpha"], ["Theta", "Motion"]]
    assert action_label_blocks("", CAMERA_WORDS) == [["(unknown)"]]
    assert action_label_blocks("   ", CAMERA_WORDS) == [["(unknown)"]]
    assert action_label_blocks("epsilon", CAMERA_WORDS) == [["Epsilon"]]


def test_a_source_that_names_no_camera_words_has_a_rows_first_word_read_as_the_act_as_a_hosted_origenerator_s_folder_names_are_the_words_being_the_library_s_vocabulary_and_none_kept_here():
    assert action_label_blocks("side gamma", ()) == [["Side", "Gamma"]]
    assert action_label_blocks("xyz gamma", ()) == [["Xyz", "Gamma"]]


def test_action_label_blocks_split_a_leading_camera_word_into_its_own_act():
    assert action_label_blocks("xyz gamma", CAMERA_WORDS) == [["XYZ"], ["Gamma"]]
    assert action_label_blocks("side gamma", CAMERA_WORDS) == [["Side"], ["Gamma"]]
    assert action_label_blocks("side theta motion", CAMERA_WORDS) == [["Side"], ["Theta", "Motion"]]
    assert action_label_blocks("xyz", CAMERA_WORDS) == [["XYZ"]]
    assert action_label_blocks("theta motion", CAMERA_WORDS) == [["Theta", "Motion"]]


def _targets(**overrides) -> HudTargets:
    base = {"click": [], "loop": [], "filter": [], "expand": None}
    base.update(overrides)
    return HudTargets(**base)


def test_single_click_switches_and_double_click_locks():
    clicks = HudClicks("landscape")
    targets = _targets(click=[((0, 0, 30, 30), "C:/v/pick.mp4")])

    assert clicks.press(targets, 10, 10, now=0.0) == ""
    assert clicks.due(now=0.1) == ""
    assert clicks.due(now=1.0) == "landscape_play_video|C:/v/pick.mp4"
    assert clicks.due(now=2.0) == ""

    assert clicks.press(targets, 10, 10, now=10.0) == ""
    assert clicks.press(targets, 10, 10, now=10.2) == "landscape_lock_video|C:/v/pick.mp4"
    assert clicks.due(now=11.0) == ""


def test_a_second_click_past_the_window_is_another_single_click():
    clicks = HudClicks("landscape")
    targets = _targets(click=[((0, 0, 30, 30), "C:/v/pick.mp4")])

    assert clicks.press(targets, 10, 10, now=0.0) == ""
    assert clicks.press(targets, 10, 10, now=DOUBLE_CLICK_S * 4) == ""
    assert clicks.due(now=DOUBLE_CLICK_S * 8) == "landscape_play_video|C:/v/pick.mp4"


def test_clicking_a_declared_button_posts_what_it_declares():
    for funestra in ("portrait", "landscape"):
        targets = _targets(buttons=_squares(0, 0, bar(funestra)))

        for rect, button in targets.buttons:
            assert HudClicks(funestra).press(
                targets, rect[0] + 5, rect[1] + 5, now=0.0) == button.command
            assert button.command.startswith(f"{funestra}_")


def test_a_dimmed_button_posts_nothing_but_the_press_stays_on_the_hud():
    targets = _targets(buttons=_squares(0, 0, (
        Button("portrait_step", "⏭", "Step", dim=True),)))

    assert HudClicks("portrait").press(targets, 5, 5, now=0.0) == ""


def test_a_side_control_posts_at_once_rather_than_waiting_out_a_double_click():
    clicks = HudClicks("portrait")

    assert clicks.press(_targets(buttons=_squares(0, 0, bar())), 5, 5, now=0.0) == "portrait_prev"
    assert clicks.due(now=5.0) == ""


def test_clicking_empty_space_posts_nothing():
    clicks = HudClicks("portrait")
    assert clicks.press(_targets(), 200, 200, now=0.0) == ""
    assert clicks.due(now=5.0) == ""


def test_loop_buttons_toggle_and_are_mutually_exclusive():
    clicks = HudClicks("portrait")
    targets = _targets(loop=[((0, 0, 20, 20), "action"), ((30, 0, 20, 20), "seed")])

    assert clicks.press(targets, 5, 5, now=0.0) == "portrait_action_loop"
    assert clicks.active_loop == "action"
    assert clicks.press(targets, 35, 5, now=1.0) == "portrait_seed_loop"
    assert clicks.active_loop == "seed"
    assert clicks.press(targets, 35, 5, now=2.0) == "portrait_no_loop"
    assert clicks.active_loop == ""


def test_clicking_the_expand_button_posts_more_seeds():
    clicks = HudClicks("landscape")
    assert clicks.press(_targets(expand=(0, 0, 18, 18)), 5, 5, now=0.0) == "landscape_more_seeds"


def test_pressing_a_filter_button_filters_to_its_row_action_posting_the_command_the_spoken_filter_does():
    clicks = HudClicks("portrait")
    targets = _targets(filter=[((0, 0, FILTER_BTN, 20), "Gamma")])

    assert clicks.press(targets, 5, 5, now=0.0) == "filter_portrait_gamma"


def test_pressing_the_filter_button_of_a_two_word_action_slugs_it_with_underscores_as_fun_time_s_filter_vocabulary_joins_them():
    clicks = HudClicks("landscape")
    targets = _targets(filter=[((0, 0, FILTER_BTN, 20), "Beta Gamma")])

    assert clicks.press(targets, 5, 5, now=0.0) == "filter_landscape_beta_gamma"


def test_a_funestra_less_command_is_posted_verbatim():
    mode_pair = funestra_rows(mode="kino")[0]
    targets = _targets(buttons=button_row_rects(0, 0, mode_pair, [60, 90, CTRL_BTN]))

    assert HudClicks("portrait").press(targets, 65, 5, now=0.0) == "origenerator_activate"


class TestThePublishedHudIsWrittenWhereItIsRead:
    def test_every_field_survives_the_round_trip(self):
        model = HudModel(
            funestra="landscape", locked=True, title="Looping seeds · Locked · Latest",
            active=True, is_favorite=True,
            corner=HudCell(path="C:/v/cur.mp4", thumb="C:/t/cur.jpg"),
            seeds=(HudCell(path="C:/v/s1.mp4", thumb="C:/t/s1.jpg"),
                   HudCell(path="C:/v/s2.mp4")),
            actions=(HudCell(path="C:/v/a1.mp4", thumb="C:/t/a1.jpg", label="gamma"),),
            current_action="alpha", filter_query="alpha", active_loop="seed",
            camera_words=CAMERA_WORDS,
            seed_count=7, action_count=3, playing=("seed", 1),
            item_note="Enhance 1 — 1 of 2 · Enhancing…", paused=True,
            rows=((Button("origenerator_activate", "Origenerator", "Shows", width=0),
                   Button("landscape_minimize", MINIMIZE_ICON, "Park", group_break=True)),
                  (Button("landscape_lock", "🔒", "Hold", lit=True, favorite=True),)),
        )

        assert parse_hud(hud_text(model)) == model

    def test_the_osr2_section_a_source_hands_this_funestra_survives_the_round_trip(self):
        model = HudModel(
            funestra="portrait", osr2=Osr2State.ROBOT_HAND, osr2_control=OSR2_PARKED,
            osr2_rows=((Button("robot_hand_park", "\x00park", "Park", lit=True),
                        Button("robot_hand_release", "\x00release", "Drive")),),
            osr2_controls=(Button("broker_panel", "\x00broker", "Broker", warn=True),),
        )

        assert parse_hud(hud_text(model)) == model

    def test_a_foot_a_source_in_another_program_painted_survives_the_round_trip(self):
        model = HudModel(funestra="portrait", foot=PaintedFoot(
            file="C:/state/portrait_foot.png", width=120, height=40, stamp="a1",
            targets=(((4, 2, 18, 18), Button("cancel|job-one", "Cancel", "Drop it")),)))

        assert parse_hud(hud_text(model)) == model

    def test_the_max_intensity_a_source_hands_this_funestra_survives_it_too(self):
        model = HudModel(funestra="portrait", osr2=Osr2State.ROBOT_HAND, max_intensity=35)

        assert parse_hud(hud_text(model)) == model

    def test_a_key_the_hud_no_longer_carries_is_passed_over(self):
        parsed = parse_hud(json.dumps({
            "funestra": "portrait", "favorites_filter": True, "latest": False,
            "enhanced_filter": True, "satellites_mode": "video"}))

        assert parsed == HudModel(funestra="portrait")

    def test_a_hud_with_no_clip_yet_round_trips_empty(self):
        parsed = parse_hud(hud_text(HudModel(funestra="portrait")))

        assert parsed.corner is None
        assert parsed.seeds == ()
        assert parsed.actions == ()
        assert parsed.playing == ("corner", 0)

    def test_the_text_is_the_json_a_funestra_already_reads_since_an_older_release_may_be_on_either_side_of_the_file(self):
        raw = json.loads(hud_text(HudModel(
            funestra="portrait", corner=HudCell(path="C:/v/cur.mp4"),
            actions=(HudCell(path="C:/v/a1.mp4", label="gamma"),), playing=("action", 0))))

        assert raw["corner"] == {"path": "C:/v/cur.mp4", "thumb": ""}
        assert raw["actions"] == [{"path": "C:/v/a1.mp4", "thumb": "", "label": "gamma"}]
        assert raw["playing"] == ["action", 0]


def test_the_published_hud_carries_where_it_sits_and_whether_it_is_minimized():
    read_back = parse_hud(hud_text(HudModel(
        funestra="landscape", hud_corner=HudCorner.LOWER_RIGHT, hud_edge=HudEdge.RIGHT,
        hud_minimized=True)))

    assert read_back.hud_corner is HudCorner.LOWER_RIGHT
    assert read_back.hud_edge is HudEdge.RIGHT
    assert read_back.hud_minimized is True


def test_a_hud_published_without_a_corner_is_drawn_in_the_upper_left():
    read_back = parse_hud(json.dumps({"funestra": "portrait"}))

    assert read_back.hud_corner is HudCorner.UPPER_LEFT
    assert read_back.hud_edge is HudEdge.LOWER
    assert read_back.hud_minimized is False


def test_a_press_where_a_button_a_loop_and_a_clip_overlap_goes_to_the_button():
    square = (0, 0, 20, 20)
    targets = _targets(
        buttons=_squares(0, 0, (Button("portrait_step", "⏭", "Step"),)),
        loop=[(square, "action")], click=[(square, "C:/v/pick.mp4")], expand=square,
        wrong_action=square)

    assert HudClicks("portrait").press(targets, 5, 5, now=0.0) == "portrait_step"


def test_a_press_where_a_loop_a_wrong_action_and_a_clip_overlap_goes_to_the_loop():
    square = (0, 0, 20, 20)
    targets = _targets(loop=[(square, "seed")], click=[(square, "C:/v/pick.mp4")],
                       expand=square, wrong_action=square)

    assert HudClicks("portrait").press(targets, 5, 5, now=0.0) == "portrait_seed_loop"


def test_a_press_where_an_expand_a_wrong_action_and_a_filter_overlap_goes_to_the_expand():
    square = (0, 0, 20, 20)
    targets = _targets(filter=[(square, "Gamma")], expand=square, wrong_action=square)

    assert HudClicks("portrait").press(targets, 5, 5, now=0.0) == "portrait_more_seeds"


def test_a_press_where_a_wrong_action_and_a_filter_overlap_goes_to_the_wrong_action():
    square = (0, 0, 20, 20)
    targets = _targets(filter=[(square, "Gamma")], wrong_action=square)

    assert HudClicks("portrait").press(targets, 5, 5, now=0.0) == "portrait_wrong_action"


def test_a_tooltip_where_a_wrong_action_a_filter_and_an_expand_overlap_is_the_wrong_actions():
    square = (0, 0, 20, 20)
    targets = _targets(filter=[(square, "Gamma")], expand=square, wrong_action=square)

    assert button_tooltip(targets, 5, 5) == tooltip_for(
        "cross", "Wrong action — strike it, and it gets asked about again")
    assert button_tooltip(_targets(filter=[(square, "Gamma")], expand=square), 5, 5) == "Filter to this action"


def test_the_wrong_act_button_is_smaller_than_a_control_and_sits_right_under_the_act_s_name_since_it_is_about_that_name():
    assert satellite_hud.WRONG_BTN < CTRL_BTN
    assert satellite_hud.wrong_action_rect(100, 40) == (
        100 - satellite_hud.WRONG_BTN, 40 + satellite_hud.WRONG_GAP,
        satellite_hud.WRONG_BTN, satellite_hud.WRONG_BTN)


def test_a_column_header_carries_the_seed_s_real_number_so_a_window_opened_partway_along_does_not_restart_at_one():
    assert satellite_hud.seed_column_label(6) == "Seed 7"


def test_the_star_is_as_tall_as_the_line_beside_it_since_a_smaller_mark_reads_as_a_speck_and_not_a_state():
    assert satellite_hud.favorite_icon_rect(0, 0, 17)[2:] == (17, 17)


def test_a_label_and_the_strike_under_it_are_centered_in_the_row_together_so_a_two_act_label_never_runs_down_into_the_button():
    row_y, row_h, two_act_label_h = 100, 60, 30
    room_for_the_strike = satellite_hud.WRONG_GAP + satellite_hud.WRONG_BTN

    top = satellite_hud.label_stack_top(row_y, row_h, two_act_label_h, room_for_the_strike)
    _x, strike_y, _w, strike_h = satellite_hud.wrong_action_rect(0, top + two_act_label_h)

    assert strike_y >= top + two_act_label_h
    assert strike_y + strike_h <= row_y + row_h
