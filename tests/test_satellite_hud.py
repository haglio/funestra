"""The satellite's in-video lock HUD: model, geometry and hit-testing."""
from __future__ import annotations

import json

from satellite_rows import band, funestra_rows
from shared_ui.icon_geometry import GLYPHS, tooltip_for
from shared_ui.spacing import BUTTON_GAP, BUTTON_GROUP_GAP

from funestra.console import OSR2_PARKED, VALUE_W
from funestra.hud_button import Button
from funestra.hud_marks import shared_mark
from funestra.hud_placement import HudCorner, HudEdge
from funestra.modes import Osr2State
from funestra.satellite_hud import (
    CTRL_BTN,
    DOUBLE_CLICK_S,
    ELLIPSIS,
    FILTER_BTN,
    LOOP_BTN,
    MAP_CELLS,
    MAP_GAP,
    PAD,
    ROW_GAP,
    TITLE_X,
    HudCell,
    HudClicks,
    HudModel,
    HudTargets,
    act_is_filtered,
    action_label_blocks,
    build_click_targets,
    button_row_rects,
    button_tooltip,
    ellipsis_rects,
    expand_button_rect,
    filter_button_rects,
    hit_test_targets,
    hud_text,
    label_is_filtered,
    largest_size_that_fits,
    loop_button_rects,
    looped_group_rect,
    map_row_width,
    map_window,
    name_line,
    panel_width,
    parse_hud,
    picture_rect,
    slot_rects,
    slot_width,
    speed_row,
)

# Fabricated: the words a source says the library writes in front of an act.
CAMERA_WORDS = ("Side", "XYZ")


def _squares(x: int, y: int, buttons) -> list:
    """*buttons* laid out as a row of squares from ``(x, y)``."""
    return button_row_rects(x, y, buttons, [CTRL_BTN] * len(buttons))


# --- the title ---------------------------------------------------------


def test_the_panel_is_as_wide_as_its_map_or_its_file_name_whichever_asks_for_more():
    for_map = panel_width("portrait")
    room = for_map - TITLE_X - PAD

    assert panel_width("portrait", name_width=room) == for_map
    assert panel_width("portrait", name_width=room + 20) == for_map + 20


def test_parse_hud_reads_whether_this_side_has_the_floor():
    """Absent means idle: a satellite reading a panel written before the flag
    existed must not light its dot on a missing key."""
    assert parse_hud(json.dumps({"funestra": "portrait", "active": True})).active is True
    assert parse_hud(json.dumps({"funestra": "portrait", "active": False})).active is False
    assert parse_hud(json.dumps({"funestra": "portrait"})).active is False


def test_parse_hud_reads_the_panel_fun_time_published():
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
    """What the dashboard's panel said by turning green — now a mark on the HUD,
    so it is read off the Funestra showing the clip rather than off a schematic."""
    assert parse_hud(json.dumps({"funestra": "portrait", "is_favorite": True})).is_favorite is True
    assert parse_hud(json.dumps({"funestra": "portrait"})).is_favorite is False


def test_parse_hud_defaults_an_empty_panel():
    """A satellite with nothing to map (no clip yet) still parses — it simply has
    no corner, so nothing is drawn."""
    model = parse_hud(json.dumps({"funestra": "landscape", "locked": False, "title": "Unlocked"}))

    assert model is not None
    assert model.corner is None
    assert model.seeds == ()
    assert model.actions == ()
    assert model.playing == ("corner", 0)


def test_parse_hud_rejects_garbage():
    """A half-written file (fun_time writes it while the Funestra reads) must not
    crash the Funestra — it just keeps the HUD it already had."""
    assert parse_hud('{"funestra": "portrait"') is None
    assert parse_hud("") is None


# --- the window a long loop is drawn through ---------------------------------
# The window is a count, not a measurement: MAP_CELLS of an axis however long, and
# whatever shape the clips in it are.
_LOOP = 12


def test_a_loop_short_enough_to_fit_is_drawn_whole():
    window = map_window(MAP_CELLS, playing=0)

    assert (window.start, window.count) == (0, MAP_CELLS)
    assert window.more_before is False
    assert window.more_after is False


def test_a_loop_just_started_opens_on_the_clip_on_screen():
    """The loop's head is the clip it started on, so at that moment the window opens
    there — the clip you pressed loop on is drawn in the corner, never mid-row."""
    window = map_window(_LOOP, playing=0)

    assert (window.start, window.count) == (0, MAP_CELLS)
    assert window.more_after is True
    assert window.more_before is False


def test_a_loop_partway_through_keeps_the_clip_on_screen_in_the_middle():
    """Once the loop has advanced past the first cells the window slides with it, so
    the lit thumbnail stays in the middle instead of walking off the end of the map
    and leaving nothing highlighted."""
    window = map_window(_LOOP, playing=5)

    assert (window.start, window.count) == (4, 3)  # 4, 5, 6 — the playing one centerd
    assert window.more_before is True
    assert window.more_after is True


def test_a_loop_near_its_end_clamps_rather_than_running_off():
    window = map_window(_LOOP, playing=11)

    assert (window.start, window.count) == (9, 3)
    assert window.more_before is True
    assert window.more_after is False


def test_an_axis_shorter_than_the_window_gives_only_what_it_has():
    window = map_window(2, playing=0)

    assert (window.start, window.count) == (0, 2)
    assert window.more_after is False


def test_an_empty_axis_has_no_window():
    window = map_window(0, playing=0)

    assert (window.start, window.count) == (0, 0)


def _filter_targets(*labels: str) -> HudTargets:
    """Press targets for a gutter of filter buttons, stacked 20px apart."""
    return HudTargets(
        click=[], loop=[],
        filter=[((0, i * 20, 18, 20), label) for i, label in enumerate(labels)],
        expand=None,
    )


def test_pressing_a_rows_filter_button_filters_the_side_to_its_act():
    clicks = HudClicks("portrait")

    assert clicks.press(_filter_targets("Theta Motion"), 5, 5, now=0.0) == "filter_portrait_theta_motion"


def test_pressing_the_lit_filter_button_turns_the_filter_off():
    """The button is a toggle, as the loop buttons are: it filters to that act, and
    pressing the lit one drops the filter — so the way out is the same control as
    the way in."""
    clicks = HudClicks("portrait")
    clicks.active_filter = "alpha"

    assert clicks.press(_filter_targets("Alpha"), 5, 5, now=0.0) == "portrait_no_filter"


def test_pressing_another_rows_filter_button_while_filtered_moves_the_filter():
    clicks = HudClicks("portrait")
    clicks.active_filter = "alpha"

    assert clicks.press(_filter_targets("Gamma"), 5, 5, now=0.0) == "filter_portrait_gamma"


def test_pressing_a_partly_matching_button_narrows_the_filter_before_lifting_it():
    """A row the filter keeps without being exactly it ("Side Gamma" under "gamma") is
    the act you reached for, so the first press moves the filter onto that whole row
    and only a press on the row the filter already is turns it off.  Lifting on the
    first press left no way to tighten a broad filter from the map."""
    clicks = HudClicks("portrait")
    clicks.active_filter = "gamma"

    assert clicks.press(_filter_targets("Side Gamma"), 5, 5, now=0.0) == "filter_portrait_side_gamma"
    assert clicks.active_filter == "side gamma"
    assert clicks.press(_filter_targets("Side Gamma"), 5, 5, now=1.0) == "portrait_no_filter"


def test_pressing_a_two_act_rows_button_filters_to_both_of_its_acts():
    """A clip carrying two acts filters to the pair, which is the query fun_time
    keeps clips having both under — and pressing it again lifts it, since that row is
    now exactly the filter."""
    clicks = HudClicks("portrait")

    command = clicks.press(_filter_targets("Gamma, Theta Motion"), 5, 5, now=0.0)

    assert command == "filter_portrait_gamma,_theta_motion"
    assert clicks.press(_filter_targets("Gamma, Theta Motion"), 5, 5, now=1.0) == "portrait_no_filter"


def test_slot_rects_lays_the_row_and_the_column_out_in_fixed_slots_three_to_a_side():
    corner, seeds, actions = slot_rects(map_x=100, map_y=50, slot_w=30, seeds=5, actions=5)

    assert corner == (100, 50, 30, 54)
    assert seeds == [(100 + 30 + MAP_GAP, 50, 30, 54), (100 + 2 * (30 + MAP_GAP), 50, 30, 54)]
    assert actions == [(100, 50 + 54 + ROW_GAP, 30, 54), (100, 50 + 2 * (54 + ROW_GAP), 30, 54)]


def test_slot_rects_draws_only_the_slots_an_axis_has_clips_for():
    _corner, seeds, actions = slot_rects(map_x=0, map_y=0, slot_w=30, seeds=1, actions=0)

    assert len(seeds) == 1
    assert actions == []


def test_the_action_column_hangs_under_the_playing_seed():
    _corner, seeds, actions = slot_rects(map_x=100, map_y=50, slot_w=30, seeds=2, actions=2,
                                         playing=("seed", 0))

    assert [x for x, _y, _w, _h in actions] == [seeds[0][0]] * 2


def test_the_column_stays_under_the_corner_off_the_seed_row():
    for playing in (("corner", 0), ("action", 0)):
        _corner, _seeds, actions = slot_rects(map_x=100, map_y=50, slot_w=30, seeds=1,
                                              actions=1, playing=playing)
        assert actions[0][0] == 100


def test_a_playing_seed_that_was_not_drawn_leaves_the_column_on_the_corner():
    _corner, _seeds, actions = slot_rects(map_x=100, map_y=50, slot_w=30, seeds=1, actions=1,
                                          playing=("seed", 5))

    assert actions[0][0] == 100


def test_a_column_under_the_rows_last_seed_ends_where_the_row_does():
    _corner, seeds, actions = slot_rects(map_x=0, map_y=0, slot_w=slot_width("portrait"),
                                         seeds=2, actions=1, playing=("seed", 1))
    ax, _ay, aw, _ah = actions[0]

    assert ax + aw == seeds[-1][0] + seeds[-1][2] == map_row_width("portrait")


def test_a_picture_stands_in_the_middle_of_its_slot():
    assert picture_rect((100, 50, 44, 54), (30, 54)) == (107, 50, 30, 54)
    assert picture_rect((100, 50, 44, 54), (44, 24)) == (100, 65, 44, 24)


def test_the_columns_chrome_follows_it_under_the_playing_seed():
    corner = (10, 10, 20, 20)
    column = (40, 10, 24, 20)
    actions = [(40, 42, 24, 20)]

    loop_action, _loop_seed = loop_button_rects(
        corner, row_end=300, column_end=250, column_rect=column)
    assert loop_action == (40, 250 + MAP_GAP, 24, LOOP_BTN)

    rect = looped_group_rect(corner, [column], actions, "action", column_rect=column)
    assert rect == (40, 10, 24, (42 + 20) - 10)

    before, after = ellipsis_rects(corner, [column], actions, "action", column_rect=column)
    assert before == (40, 10 - MAP_GAP - ELLIPSIS, 24, ELLIPSIS)
    assert after == (40, 42 + 20 + MAP_GAP, 24, ELLIPSIS)


def test_the_loop_buttons_stand_past_the_rows_and_the_columns_fixed_ends():
    corner = (10, 10, 20, 20)
    loop_action, loop_seed = loop_button_rects(corner, row_end=150, column_end=180, reserve=7)

    assert loop_action == (10, 180 + 7 + MAP_GAP, 20, LOOP_BTN)
    assert loop_seed == (150 + 7 + MAP_GAP, 10, LOOP_BTN, 20)
    assert loop_button_rects(None, row_end=150, column_end=180) == (None, None)


def test_expand_button_sits_in_the_row_right_of_the_seed_loop_button():
    loop_seed = (60, 10, 18, 30)

    assert expand_button_rect(loop_seed) == (60 + 18 + MAP_GAP, 10, LOOP_BTN, 30)
    assert expand_button_rect(None) is None


def test_build_and_hit_test_click_targets():
    """Targets zip the drawn rects to their paths — corner=current, then each
    seed, then each action — and a point resolves to the clip it falls in."""
    corner = (10, 10, 20, 20)
    seeds = [(40, 10, 20, 20)]
    actions = [(10, 40, 20, 20)]

    targets = build_click_targets(
        corner, seeds, actions,
        HudCell(path="cur.mp4"), [HudCell(path="s1.mp4")], [HudCell(path="a1.mp4")],
    )

    assert targets == [
        ((10, 10, 20, 20), "cur.mp4"),
        ((40, 10, 20, 20), "s1.mp4"),
        ((10, 40, 20, 20), "a1.mp4"),
    ]
    assert hit_test_targets(targets, 15, 15) == "cur.mp4"
    assert hit_test_targets(targets, 45, 15) == "s1.mp4"
    assert hit_test_targets(targets, 15, 45) == "a1.mp4"
    assert hit_test_targets(targets, 100, 100) == ""  # empty area hits nothing


def test_build_click_targets_skips_a_missing_corner():
    assert build_click_targets(None, [], [], None, [], []) == []


def test_filter_button_rects_puts_one_at_the_head_of_each_row():
    """Each row gets a filter button at the gutter's left edge, as tall as the row
    and left of its action name: the corner's is the current action, the rows below
    their siblings.  A row with no act name gets none — nothing to filter to."""
    corner = (60, 50, 30, 54)
    actions = [(60, 110, 30, 54), (60, 170, 30, 54)]

    rects = filter_button_rects(
        corner, actions, gutter_x=10,
        current_action="Alpha", action_labels=["Gamma", ""],
    )

    assert rects == [((10, 50, FILTER_BTN, 54), "Alpha"), ((10, 110, FILTER_BTN, 54), "Gamma")]
    assert filter_button_rects(None, [], 10, "", []) == []


def test_label_is_filtered_reads_a_filter_the_way_fun_time_applies_it():
    """fun_time keeps a clip when the query is a substring of its metadata, so a row
    it keeps has to light even when its label is not the query exactly — "Side Gamma"
    and "Gamma, Theta" are both clips a "gamma" filter holds you to.

    The cases below are the rule as this repo owns it.  That it still agrees with
    fun_time's own matcher — the authority it mirrors — is pinned over THERE, in
    fun_time's test_media_metadata, because only the wearer of this HUD can import
    both sides; this suite runs with funestra alone on the path.  The empty query
    is the one deliberate difference: it matches every clip there, and lights no row
    here.
    """
    cases = [
        ("Gamma", "gamma", True),               # the row that names it
        ("Side Gamma", "gamma", True),          # the query is one act of the row
        ("Side Gamma", "side gamma", True),     # the filter set from that very row
        ("Gamma, Theta", "gamma", True),        # one of two acts on the clip
        ("Gamma   Theta", "gamma theta", True),  # whitespace collapsed on both sides
        ("Gamma, Theta", "gamma, theta", True),  # the filter set from that very clip
        ("Gamma", "gamma, theta", False),       # …which does not keep a one-act clip
        ("Alpha", "gamma", False),
        ("Gam", "gamma", False),                # the label is not the longer query
    ]
    for label, query, expected in cases:
        assert label_is_filtered(label, query, CAMERA_WORDS) is expected, (label, query)

    assert label_is_filtered("Gamma", "", CAMERA_WORDS) is False


def test_act_is_filtered_picks_out_which_of_a_rows_acts_the_filter_named():
    """The row says whether the clip is here; this says which of its acts is why —
    the rule that whitens one line of a label and leaves its neighbours gray."""
    def lit(act: str, filter_query: str) -> bool:
        return act_is_filtered(act, filter_query, CAMERA_WORDS)

    assert lit("Gamma", "gamma") is True
    assert lit("XYZ", "gamma") is False        # a camera word is not the act
    assert lit("Side", "gamma") is False
    assert lit("Theta Gamma", "gamma") is True  # an act the query is part of
    # A filter set from a two-act clip names both, so both of that row's acts light.
    assert lit("Gamma", "gamma, theta") is True
    assert lit("Theta", "gamma, theta") is True
    assert lit("Alpha", "gamma, theta") is False
    # And one set from a camera-scoped row names the camera word and the act apart.
    assert lit("Gamma", "xyz gamma") is True
    assert lit("XYZ", "xyz gamma") is True
    assert lit("Gamma", "") is False


def test_button_tooltip_names_each_button():
    """Every glyph on the panel is cryptic on purpose, so each one names itself on
    hover — a declared button by the tooltip its source gave it, the map's own
    chrome and the favorite mark by the words the panel has for them."""
    targets = HudTargets(
        click=[],
        loop=[((0, 0, 20, 20), "action"), ((30, 0, 20, 20), "seed")],
        filter=[((0, 100, FILTER_BTN, 54), "gamma")],
        expand=(30, 30, 18, 18),
        buttons=_squares(0, 60, band(newest=False)),
        favorite=(300, 60, CTRL_BTN, CTRL_BTN),
    )

    assert button_tooltip(targets, 5, 5) == "Loop this action column"
    assert button_tooltip(targets, 35, 5) == "Loop this seed row"
    assert button_tooltip(targets, 5, 105) == "Filter to this action"
    assert button_tooltip(targets, 35, 35) == "More seeds — widen the net"
    # Probed off the rects the row was actually laid out at rather than off a
    # fixed pitch: the band breaks into groups, so a stride is not the answer.
    for (bx, by, _w, _h), button in targets.buttons:
        assert button_tooltip(targets, bx + 5, by + 5) == button.tooltip
    assert button_tooltip(targets, 305, 65) == "In the favorites"
    assert button_tooltip(targets, 400, 400) == ""


def test_a_declared_button_wearing_a_mark_this_version_lacks_says_why_on_hover():
    auto = Button("auto", shared_mark("a_mark_from_another_version"), "Generate on its own")

    targets = _targets(buttons=_squares(0, 0, (auto,)))

    assert button_tooltip(targets, 5, 5) == auto.tooltip_on_hover


def test_the_map_s_own_controls_say_why_when_this_version_lacks_their_marks(monkeypatch):
    for mark in ("loop", "cross", "expand_horizontal", "star"):
        monkeypatch.delitem(GLYPHS, mark)
    targets = _targets(loop=[((0, 0, 20, 20), "action")], wrong_action=(30, 0, 20, 20),
                       expand=(60, 0, 20, 20), favorite=(90, 0, 20, 20))

    assert [button_tooltip(targets, x + 5, 5) for x in (0, 30, 60, 90)] == [
        tooltip_for("loop", "Loop this action column"),
        tooltip_for("cross", "Wrong action — strike it, and it gets asked about again"),
        tooltip_for("expand_horizontal", "More seeds — widen the net"),
        tooltip_for("star", "In the favorites"),
    ]


def test_a_declared_row_is_laid_out_as_wide_as_each_button_says():
    """A square is a square; a word button is as wide as the painter measured its
    word, handed in here because this module is font-free; and the wider gap
    opens before a button that says it starts a group."""
    rects = button_row_rects(10, 40, (
        Button("go_kino", "Kino", "Kino mode", width=0),
        Button("go_shows", "Origenerator", "Origenerator mode", width=0),
        Button("park", "\x00minimize", "Park it", group_break=True),
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
    assert rate == (80 + CTRL_BTN + MAP_GAP, 40, VALUE_W, CTRL_BTN)
    assert up == (rate[0] + VALUE_W + MAP_GAP, 40, CTRL_BTN, CTRL_BTN)


def test_the_speed_buttons_say_what_a_press_does_to_the_video():
    """In the words the main console's own pair says it in."""
    buttons, _rate = speed_row("landscape", 0, 0, label_width=70)
    targets = _targets(buttons=buttons)

    assert [button_tooltip(targets, x + 5, y + 5) for (x, y, _w, _h), _b in buttons] == [
        "Play the video slower", "Play the video faster"]


def test_a_name_too_long_for_its_line_is_shortened_so_the_note_after_it_stays_whole():
    line = name_line("folder one / seed 12345", "Enhancing…", room=25, width_of=len)

    assert line == "folder one…" + " · Enhancing…"


def test_a_name_and_a_note_that_fit_their_line_are_left_whole():
    assert name_line("clip", "Enhancing…", room=100, width_of=len) == "clip · Enhancing…"


def test_a_name_with_no_note_after_it_is_left_whole_however_long():
    assert name_line("a long name " * 5, "", room=10, width_of=len) == "a long name " * 5


def test_a_note_with_no_name_before_it_stands_alone():
    assert name_line("", "Enhancing…", room=100, width_of=len) == "Enhancing…"


def test_a_note_too_long_to_leave_any_of_the_name_stands_alone():
    assert name_line("clip", "Enhancing…", room=12, width_of=len) == "Enhancing…"


def test_a_title_that_fits_keeps_its_full_size():
    assert largest_size_that_fits(11, room=100, width_at=lambda size: 5 * size) == 11


def test_a_title_too_wide_takes_the_largest_size_that_fits():
    assert largest_size_that_fits(11, room=40, width_at=lambda size: 5 * size) == 8


def test_a_title_that_fits_at_no_size_takes_the_smallest():
    assert largest_size_that_fits(11, room=3, width_at=lambda size: 5 * size) == 1


def test_action_label_blocks_separate_comma_joined_acts():
    """Several acts on one clip ("Alpha, Theta Motion") become one block each
    (drawn with a gap between), commas dropped; one act is a single block."""
    assert action_label_blocks("alpha, theta motion", CAMERA_WORDS) == [["Alpha"], ["Theta", "Motion"]]
    assert action_label_blocks("", CAMERA_WORDS) == [["(unknown)"]]
    assert action_label_blocks("   ", CAMERA_WORDS) == [["(unknown)"]]
    assert action_label_blocks("epsilon", CAMERA_WORDS) == [["Epsilon"]]


def test_a_source_that_names_no_camera_words_has_a_rows_first_word_read_as_the_act():
    """A hosted Origenerator's rows are folders the user named, not the library's
    acts, so it names none and a row's first word is never set apart."""
    assert action_label_blocks("side gamma", ()) == [["Side", "Gamma"]]
    assert action_label_blocks("xyz gamma", ()) == [["Xyz", "Gamma"]]


def test_action_label_blocks_split_a_leading_camera_word_into_its_own_act():
    """A camera word in front of an act is not part of it, so it becomes its own
    block — which is what lets a "gamma" filter light "Gamma" and leave the camera
    word gray instead of whitening both.

    Every camera word the source names, since Evolver's backfill scopes every act it
    writes by one of them and never writes a bare act.
    """
    assert action_label_blocks("xyz gamma", CAMERA_WORDS) == [["XYZ"], ["Gamma"]]
    assert action_label_blocks("side gamma", CAMERA_WORDS) == [["Side"], ["Gamma"]]
    assert action_label_blocks("side theta motion", CAMERA_WORDS) == [["Side"], ["Theta", "Motion"]]
    assert action_label_blocks("xyz", CAMERA_WORDS) == [["XYZ"]]  # nothing to qualify: one act
    assert action_label_blocks("theta motion", CAMERA_WORDS) == [["Theta", "Motion"]]  # not a camera word


def _targets(**overrides) -> HudTargets:
    base = dict(click=[], loop=[], filter=[], expand=None)
    base.update(overrides)
    return HudTargets(**base)


def test_single_click_switches_and_double_click_locks():
    """A single click posts play_video once its double-click window lapses; a
    second click inside that window cancels it and posts lock_video instead."""
    clicks = HudClicks("landscape")
    targets = _targets(click=[((0, 0, 30, 30), "C:/v/pick.mp4")])

    assert clicks.press(targets, 10, 10, now=0.0) == ""      # deferred
    assert clicks.due(now=0.1) == ""                          # still inside the window
    assert clicks.due(now=1.0) == "landscape_play_video|C:/v/pick.mp4"
    assert clicks.due(now=2.0) == ""                          # fired once

    assert clicks.press(targets, 10, 10, now=10.0) == ""
    assert clicks.press(targets, 10, 10, now=10.2) == "landscape_lock_video|C:/v/pick.mp4"
    assert clicks.due(now=11.0) == ""                         # the single was cancelled


def test_a_second_click_past_the_window_is_another_single_click():
    """The window is what makes the second press a double.  Past it, the same
    cell pressed again is someone picking that clip a second time — it defers
    like any other single press rather than locking what it lands on."""
    clicks = HudClicks("landscape")
    targets = _targets(click=[((0, 0, 30, 30), "C:/v/pick.mp4")])

    assert clicks.press(targets, 10, 10, now=0.0) == ""
    assert clicks.press(targets, 10, 10, now=DOUBLE_CLICK_S * 4) == ""
    assert clicks.due(now=DOUBLE_CLICK_S * 8) == "landscape_play_video|C:/v/pick.mp4"


def test_clicking_a_declared_button_posts_what_it_declares():
    """Each button posts exactly the verb its source gave it — "portrait_prev",
    "landscape_trash" — so the dispatch loop needs no new verbs for a button,
    only for the thing it does."""
    for funestra in ("portrait", "landscape"):
        targets = _targets(buttons=_squares(0, 0, band(funestra)))

        for rect, button in targets.buttons:
            assert HudClicks(funestra).press(
                targets, rect[0] + 5, rect[1] + 5, now=0.0) == button.command
            assert button.command.startswith(f"{funestra}_")


def test_a_dimmed_button_posts_nothing_but_the_press_stays_on_the_panel():
    """Dimmed is at the end of its range or with nothing to act on: the press
    it would post is one nothing would answer, so nothing goes out."""
    targets = _targets(buttons=_squares(0, 0, (
        Button("portrait_step", "⏭", "Step", dim=True),)))

    assert HudClicks("portrait").press(targets, 5, 5, now=0.0) == ""


def test_a_side_control_posts_at_once_rather_than_waiting_out_a_double_click():
    """Only a thumbnail press is ambiguous (single switches, double locks).  A
    button means one thing, so it fires on the press and leaves nothing pending."""
    clicks = HudClicks("portrait")

    assert clicks.press(_targets(buttons=_squares(0, 0, band())), 5, 5, now=0.0) == "portrait_prev"
    assert clicks.due(now=5.0) == ""


def test_clicking_empty_space_posts_nothing():
    clicks = HudClicks("portrait")
    assert clicks.press(_targets(), 200, 200, now=0.0) == ""
    assert clicks.due(now=5.0) == ""


def test_loop_buttons_toggle_and_are_mutually_exclusive():
    """Clicking a loop button posts action_loop/seed_loop and marks it active; the
    other going on turns it off (they cannot coexist); clicking the active one
    again posts no_loop."""
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


def test_pressing_a_filter_button_filters_to_its_row_action():
    """A press on a row's filter button posts filter_<side>_<action>, the same
    command speaking "[side] gamma" would."""
    clicks = HudClicks("portrait")
    targets = _targets(filter=[((0, 0, FILTER_BTN, 20), "Gamma")])

    assert clicks.press(targets, 5, 5, now=0.0) == "filter_portrait_gamma"


def test_pressing_the_filter_button_of_a_two_word_action_slugs_it():
    """Multi-word acts carry an underscore in the command, as filter_vocab slugs
    them ("beta gamma" -> beta_gamma)."""
    clicks = HudClicks("landscape")
    targets = _targets(filter=[((0, 0, FILTER_BTN, 20), "Beta Gamma")])

    assert clicks.press(targets, 5, 5, now=0.0) == "filter_landscape_beta_gamma"


def test_a_funestra_less_command_is_posted_verbatim():
    """The mode pair's commands belong to the whole satellite side, so they
    carry no Funestra of their own and none is added."""
    mode_pair = funestra_rows(mode="kino")[0]
    targets = _targets(buttons=button_row_rects(0, 0, mode_pair, [60, 90, CTRL_BTN]))

    assert HudClicks("portrait").press(targets, 65, 5, now=0.0) == "origenerator_activate"


class TestThePublishedPanelIsWrittenWhereItIsRead:
    """A source publishes a HudModel as text and the Funestra parses it back; the
    keys are spelled once, here, rather than by the writer in one repo and the
    reader in another."""

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
                   Button("landscape_minimize", "\x00minimize", "Park", group_break=True)),
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

    def test_the_max_intensity_a_source_hands_this_funestra_survives_it_too(self):
        model = HudModel(funestra="portrait", osr2=Osr2State.ROBOT_HAND, max_intensity=35)

        assert parse_hud(hud_text(model)) == model

    def test_a_key_the_panel_no_longer_carries_is_passed_over(self):
        """The switches a Funestra's band was once lit from still come from a
        publisher on an older release; the panel reads the same without them."""
        parsed = parse_hud(json.dumps({
            "funestra": "portrait", "favorites_filter": True, "latest": False,
            "enhanced_filter": True, "satellites_mode": "video"}))

        assert parsed == HudModel(funestra="portrait")

    def test_a_title_published_before_it_was_called_the_title_still_reads(self):
        assert parse_hud(json.dumps({"funestra": "portrait", "lock_label": "Locked"})).title == (
            "Locked")

    def test_the_title_also_goes_out_where_a_reader_from_before_the_rename_looks(self):
        raw = json.loads(hud_text(HudModel(funestra="portrait", title="Locked")))

        assert raw["title"] == raw["lock_label"] == "Locked"

    def test_a_source_from_before_the_rename_still_hands_the_title_over(self):
        assert HudModel(funestra="portrait", lock_label="Locked").title == "Locked"

    def test_a_panel_with_no_clip_yet_round_trips_empty(self):
        parsed = parse_hud(hud_text(HudModel(funestra="portrait")))

        assert parsed.corner is None
        assert parsed.seeds == () and parsed.actions == ()
        assert parsed.playing == ("corner", 0)

    def test_the_text_is_the_json_a_funestra_already_reads(self):
        """A cell with nothing in its label carries no label key, and the playing
        cell is a two-element list, exactly as the panel was published before the
        writer moved here -- a Funestra on either side of the move reads it."""
        raw = json.loads(hud_text(HudModel(
            funestra="portrait", corner=HudCell(path="C:/v/cur.mp4"),
            actions=(HudCell(path="C:/v/a1.mp4", label="gamma"),), playing=("action", 0))))

        assert raw["corner"] == {"path": "C:/v/cur.mp4", "thumb": ""}
        assert raw["actions"] == [{"path": "C:/v/a1.mp4", "thumb": "", "label": "gamma"}]
        assert raw["playing"] == ["action", 0]


def test_the_published_panel_carries_where_it_sits_and_whether_it_is_minimized():
    read_back = parse_hud(hud_text(HudModel(
        funestra="landscape", hud_corner=HudCorner.LOWER_RIGHT, hud_edge=HudEdge.RIGHT,
        hud_minimized=True)))

    assert read_back.hud_corner is HudCorner.LOWER_RIGHT
    assert read_back.hud_edge is HudEdge.RIGHT
    assert read_back.hud_minimized is True


def test_a_panel_published_without_a_corner_is_drawn_in_the_upper_left():
    read_back = parse_hud(json.dumps({"funestra": "portrait"}))

    assert read_back.hud_corner is HudCorner.UPPER_LEFT
    assert read_back.hud_edge is HudEdge.LOWER
    assert read_back.hud_minimized is False
