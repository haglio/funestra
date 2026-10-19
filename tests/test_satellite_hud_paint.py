"""Pixel-level checks on the HUD bitmap mpv composites into the satellite video."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw
from satellite_rows import funestra_rows, short_name
from shared_ui import colors
from shared_ui.app_icon import LETTERS
from shared_ui.palette import BLUE, BORDER_PANEL, GREEN, TEXT_MUTED, TEXT_PRIMARY, WHITE
from shared_ui.spacing import BUTTON_GAP

from funestra import satellite_hud_paint
from funestra.console import OSR2_DRIVING, OSR2_PARKED
from funestra.drive_layout import MAX_INTENSITY, SECTION_W
from funestra.drive_readout import (
    CONTROL_TIPS,
    DRIVEN_BY_ROBOT_HAND,
    DriveHud,
    section_size,
    track_command,
    tracks,
)
from funestra.geometry import Rect
from funestra.hud_button import Button
from funestra.hud_minimize import RESTORE_TOOLTIP, minimize_command
from funestra.hud_minimize import ROOM as MINUS_ROOM
from funestra.hud_panel import ACTIVE_DOT
from funestra.hud_placement import HudCorner
from funestra.hud_row import SCRUBBER, RowHud, row_part
from funestra.hud_sections import DIVIDER_H, SECTION_GAP
from funestra.modes import Osr2State
from funestra.satellite_hud import (
    COL_LABEL_GAP,
    COL_LABEL_H,
    CTRL_BAND_H,
    CTRL_BTN,
    ELLIPSIS_ROOM,
    FILTER_BTN,
    MAP_CELLS,
    MAP_GAP,
    MAP_RIGHT_RESERVE,
    MAP_THUMB_H,
    PAD,
    ROW_LABEL_GUTTER,
    TITLE_BAND_H,
    TITLE_X,
    HudCell,
    HudClicks,
    HudModel,
    button_tooltip,
    ellipsis_rects,
    looped_group_rect,
    map_row_width,
    slot_width,
)
from funestra.satellite_hud_paint import HudRenderer
from funestra.volume import VolumeHud


def _declared(rendered) -> list:
    """The buttons the source declared, without the panel's own minimize."""
    return [(rect, button) for rect, button in rendered.targets.buttons
            if button.command != minimize_command(button.command.split("_")[0])]


def _names(rendered) -> list[str]:
    """What each drawn button is for, in the order they were laid out."""
    return [short_name(button) for _rect, button in _declared(rendered)]


def _rects(rendered) -> dict:
    """Each drawn button's rect, by what it is for."""
    return {short_name(button): rect for rect, button in rendered.targets.buttons}


@pytest.fixture
def thumb(tmp_path: Path) -> str:
    path = tmp_path / "thumb.jpg"
    Image.new("RGB", (40, 60), (30, 30, 30)).save(path)
    return str(path)


CLIP_SHAPES = {
    "portrait": [(90, 160), (132, 160), (160, 90)],
    "landscape": [(160, 90), (160, 125), (160, 69)],
}


@pytest.fixture
def clip_thumb(tmp_path: Path):
    """``(side, shape) -> thumbnail path`` for the shapes above."""
    def make(funestra: str, shape: tuple[int, int]) -> str:
        path = tmp_path / f"{funestra}-{shape[0]}x{shape[1]}.jpg"
        if not path.exists():
            Image.new("RGB", shape, (30, 30, 30)).save(path)
        return str(path)
    return make


def _sides_and_shapes() -> list[tuple[str, tuple[int, int]]]:
    return [(funestra, shape) for funestra, shapes in CLIP_SHAPES.items() for shape in shapes]


def _model(**overrides) -> HudModel:
    """A Funestra's panel, with the band its source declares unless *rows* says
    otherwise."""
    base = dict(funestra="portrait", locked=True, title="Locked")
    base.update(overrides)
    base.setdefault("rows", funestra_rows(base["funestra"]))
    return HudModel(**base)


def _rgb(bgra: np.ndarray) -> np.ndarray:
    """(H, W, 3) RGB view of an mpv BGRA buffer, for pixel assertions."""
    return bgra[:, :, [2, 1, 0]]


def _dividers(rendered) -> list[int]:
    rgba = rendered.bgra[:, :, [2, 1, 0, 3]]
    return [y for y in range(rgba.shape[0]) if (rgba[y] == (*BORDER_PANEL, 255)).all()]


def _lines_between(rendered, above_ends: int, below_starts: int) -> int:
    return sum(above_ends <= line < below_starts for line in _dividers(rendered))


def _map_top(rendered) -> int:
    corner_y = rendered.targets.click[0][0][1]
    return corner_y - ELLIPSIS_ROOM - COL_LABEL_GAP - COL_LABEL_H


def test_render_fills_the_panel_and_draws_the_map(thumb):
    rendered = HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb),
               seeds=(HudCell(path="s1.mp4", thumb=thumb),),
               actions=(HudCell(path="a1.mp4", thumb=thumb, label="alpha"),))
    )

    assert (rendered.bgra[:, :, 3] > 0).mean() > 0.5


def _crowded(funestra: str, thumb: str) -> HudModel:
    """A side with more seeds and more acts than any map draws."""
    return _model(
        funestra=funestra, locked=False, title="Unlocked · Shuffle", current_action="Alpha",
        corner=HudCell(path="c.mp4", thumb=thumb),
        seeds=tuple(HudCell(path=f"s{i}.mp4", thumb=thumb) for i in range(6)),
        actions=tuple(HudCell(path=f"a{i}.mp4", thumb=thumb, label="Alpha") for i in range(4)),
        seed_count=7, action_count=5,
    )


@pytest.mark.parametrize("funestra,shape", _sides_and_shapes())
def test_the_map_is_three_cells_a_side_whatever_shape_its_clips_are(funestra, shape, clip_thumb):
    rendered = HudRenderer(funestra).render(_crowded(funestra, clip_thumb(funestra, shape)))

    rects = [rect for rect, _path in rendered.targets.click]
    columns = {x for x, _y, _w, _h in rects}
    rows = {y for _x, y, _w, _h in rects}
    assert (len(columns), len(rows)) == (MAP_CELLS, MAP_CELLS)


@pytest.mark.parametrize("funestra,shape", _sides_and_shapes())
def test_the_panel_stops_where_its_last_controls_do(funestra, shape, clip_thumb):
    """No slab past the map wherever the map is what set the width: the expand
    button ends one margin in from the right edge and the action-loop button one
    margin up from the lower edge, so every pixel of the panel is carrying something —
    for a wide cell as much as a narrow one.  (A status longer than the map is the
    other case, and there it is the line that reaches the far edge.)"""
    rendered = HudRenderer(funestra).render(_crowded(funestra, clip_thumb(funestra, shape)))
    height, width = rendered.bgra.shape[:2]

    ex, _ey, ew, _eh = rendered.targets.expand
    loop = dict((kind, rect) for rect, kind in rendered.targets.loop)
    _lx, ly, _lw, lh = loop["action"]
    assert ex + ew == width - PAD
    assert ly + lh == height - PAD


@pytest.mark.parametrize("funestra", CLIP_SHAPES)
def test_the_map_holds_its_cells_and_buttons_in_place_whatever_shape_its_clips_are(
        funestra, clip_thumb):
    renderer = HudRenderer(funestra)
    lone = renderer.render(_model(funestra=funestra, corner=HudCell(
        path="c.mp4", thumb=clip_thumb(funestra, CLIP_SHAPES[funestra][0]))))
    crowded = [renderer.render(_crowded(funestra, clip_thumb(funestra, shape)))
               for shape in CLIP_SHAPES[funestra]]

    assert len({rendered.bgra.shape for rendered in [lone, *crowded]}) == 1
    assert len({tuple(rect for rect, _path in rendered.targets.click)
                for rendered in crowded}) == 1
    assert len({(rendered.targets.expand, tuple(rendered.targets.loop))
                for rendered in [lone, *crowded]}) == 1


def test_the_panel_is_as_tall_with_one_act_on_its_map_as_with_three(thumb):
    renderer = HudRenderer("portrait")
    corner = HudCell(path="c.mp4", thumb=thumb)
    one = renderer.render(_model(corner=corner))
    three = renderer.render(_model(corner=corner, actions=(
        HudCell(path="a1.mp4", thumb=thumb, label="beta"),
        HudCell(path="a2.mp4", thumb=thumb, label="gamma"))))

    assert one.bgra.shape[0] == three.bgra.shape[0]


def test_the_column_loop_button_stays_at_the_foot_of_the_map_however_long_the_column(thumb):
    renderer = HudRenderer("portrait")
    corner = HudCell(path="c.mp4", thumb=thumb)
    one = renderer.render(_model(corner=corner))
    three = renderer.render(_model(corner=corner, actions=(
        HudCell(path="a1.mp4", thumb=thumb, label="beta"),
        HudCell(path="a2.mp4", thumb=thumb, label="gamma"))))

    def column_loop(rendered):
        return dict((kind, rect) for rect, kind in rendered.targets.loop)["action"]

    assert column_loop(one) == column_loop(three)
    assert column_loop(one)[1] + column_loop(one)[3] == one.bgra.shape[0] - PAD


def test_a_satellite_with_no_clip_yet_keeps_the_room_its_map_will_take(thumb):
    renderer = HudRenderer("portrait")
    shell = renderer.render(_model(title="Unlocked"))
    mapped = renderer.render(_model(title="Unlocked",
                                    corner=HudCell(path="c.mp4", thumb=thumb)))

    assert shell.bgra.shape == mapped.bgra.shape


def test_render_rings_the_locked_clip_in_white(thumb):
    """The white ring marks a lock: a locked panel rings the corner, an unlocked
    one leaves no near-white ink on the map (below the lock band, where the
    "Locked" word can't be mistaken for the ring)."""
    def ring_ink(locked: bool) -> int:
        rendered = HudRenderer("portrait").render(
            _model(locked=locked, title="Locked" if locked else "Unlocked",
                   corner=HudCell(path="c.mp4", thumb=thumb))
        )
        rgb = _rgb(rendered.bgra)[PAD + TITLE_BAND_H:, :]
        return int((rgb > 248).all(axis=2).sum())

    assert ring_ink(True) > 0
    assert ring_ink(False) == 0


def test_the_lock_ring_follows_the_clip_being_held(thumb):
    """A lock taken inside a loop holds whichever clip the loop had reached, and
    the map stays anchored where the loop started — so the ring has to land on the
    cell that clip is drawn in.  Left on the corner it rings a clip that is neither
    playing nor locked."""
    def ring_ink(playing) -> tuple[int, int]:
        rendered = HudRenderer("portrait").render(
            _model(playing=playing, active_loop="seed",
                   title="Looping seeds · Locked · Shuffle",
                   corner=HudCell(path="c.mp4", thumb=thumb),
                   seeds=(HudCell(path="s1.mp4", thumb=thumb),)))
        rgb = _rgb(rendered.bgra)

        def white_in(rect) -> int:
            x, y, w, h = rect
            return int((rgb[y:y + h, x:x + w] > 248).all(axis=2).sum())

        corner_rect, seed_rect = rendered.targets.click[0][0], rendered.targets.click[1][0]
        return white_in(corner_rect), white_in(seed_rect)

    corner_ringed, seed_bare = ring_ink(("corner", 0))
    corner_bare, seed_ringed = ring_ink(("seed", 0))
    assert corner_ringed > corner_bare
    assert seed_ringed > seed_bare


def test_render_without_a_corner_still_draws_the_shell():
    """A satellite with no clip yet gets the lock band and nothing else — and no
    click targets, so a stray press over the empty panel posts nothing."""
    rendered = HudRenderer("landscape").render(
        HudModel(funestra="landscape", locked=False, title="Unlocked"))

    assert (rendered.bgra[:, :, 3] > 0).any()
    assert rendered.targets.click == []
    assert rendered.targets.expand is None


def test_the_dot_lights_up_only_on_the_active_side(thumb):
    """The dot beside the title says whether a bare "lock" or "next" would
    land here.  Lit is white, idle is the palette's gray — never absent, because a
    missing dot could not be told from an idle one, and then the lit one on the
    other Funestra would be the only readable state."""
    def dot(active: bool) -> np.ndarray:
        rendered = HudRenderer("portrait").render(
            _model(active=active, title="Unlocked · Shuffle",
                   corner=HudCell(path="c.mp4", thumb=thumb)))
        # The middle of the dot, left of where the title starts, past the
        # minus in the panel's corner: the disc's rim is antialiased into the panel.
        left = PAD + MINUS_ROOM
        return _rgb(rendered.bgra)[PAD + 5:PAD + 11, left + 3:left + 9]

    assert np.allclose(dot(True).reshape(-1, 3).mean(axis=0), WHITE, atol=40)
    assert np.allclose(dot(False).reshape(-1, 3).mean(axis=0), TEXT_MUTED, atol=40)


def test_the_title_starts_clear_of_the_dot(thumb):
    """Drawn over each other they would be illegible, and the width the line asks
    the panel for is measured from the room the dot leaves, not from the far edge."""
    rendered = HudRenderer("portrait").render(
        _model(active=True, title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb)))
    rgb = _rgb(rendered.bgra)

    # TITLE_X is absolute, so the gap runs from the dot's right edge to it —
    # skipping the 2px where the round dot's antialiased edge feathers out, which
    # is the dot, not text starting early.
    gap = rgb[PAD:PAD + 14, MINUS_ROOM + PAD + ACTIVE_DOT + 2:MINUS_ROOM + TITLE_X]
    assert (gap > 200).all(axis=2).sum() == 0, "text ink in the gap before the text starts"


def test_a_status_too_wide_for_the_map_is_drawn_smaller_or_cut_short_rather_than_widening_the_panel(thumb):
    def rendered(label: str):
        return HudRenderer("portrait").render(
            _model(title=label, corner=HudCell(path="c.mp4", thumb=thumb)))

    short = rendered("Locked")
    long = rendered("Looping actions · Locked · Latest · F-Mode · Enhanceds · beta gamma")
    band = _rgb(long.bgra)[PAD:PAD + TITLE_BAND_H, TITLE_X:]
    inked_columns = np.nonzero((band > 200).all(axis=2).any(axis=0))[0]

    assert long.bgra.shape == short.bgra.shape
    assert TITLE_X + inked_columns.max() < long.bgra.shape[1] - PAD


def _control_band_top(rendered) -> int:
    """Where the side's own control buttons start — the row under the status block,
    and so how deep that block ended up."""
    return min(y for (_x, y, _w, _h), _button in _declared(rendered))


def test_the_file_on_screen_is_named_in_muted_gray_under_the_title(thumb):
    renderer = HudRenderer("portrait")
    model = _model(title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb))
    named = renderer.render(model, video="example clip one")

    strip = _rgb(named.bgra)[PAD + TITLE_BAND_H:_dividers(named)[0], TITLE_X:-PAD]
    assert (strip > 80).any(axis=2).sum() > 0
    assert (strip > 200).all(axis=2).sum() == 0


def test_the_line_the_file_name_takes_is_kept_while_there_is_no_name(thumb):
    renderer = HudRenderer("portrait")
    model = _model(title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb))
    bare = renderer.render(model)
    named = renderer.render(model, video="example clip one")

    assert bare.bgra.shape == named.bgra.shape
    assert _control_band_top(bare) == _control_band_top(named)


def test_a_file_name_too_wide_for_the_map_widens_the_panel(thumb):
    """Names run long, and a name cut off mid-word says nothing about which clip this
    is — which is the whole reason it is drawn.  So it takes the width it needs, the
    way the title above it does."""
    renderer = HudRenderer("portrait")
    model = _model(title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb))

    short = renderer.render(model, video="clip")
    long = renderer.render(
        model, video="a considerably longer example clip name than the map is wide,"
                     " made longer still so that no map could ever be as wide")

    assert long.bgra.shape[1] > short.bgra.shape[1]
    assert long.bgra.shape[0] == short.bgra.shape[0]


def test_a_note_after_a_name_shortens_the_name_rather_than_widening_the_panel(thumb):
    renderer = HudRenderer("portrait")
    corner = HudCell(path="c.mp4", thumb=thumb)
    name = "Example Folder / seed 123456789012345"

    named = renderer.render(_model(title="Unlocked", corner=corner), video=name)
    noted = renderer.render(
        _model(title="Unlocked", corner=corner,
               item_note="Enhance 1 — 1 of 2 · Enhancing…"),
        video=name)

    assert noted.bgra.shape == named.bgra.shape


def test_a_note_about_a_clip_with_no_name_is_drawn_on_the_kept_name_line(thumb):
    renderer = HudRenderer("portrait")
    corner = HudCell(path="c.mp4", thumb=thumb)

    bare = renderer.render(_model(title="Unlocked", corner=corner))
    noted = renderer.render(_model(title="Unlocked", corner=corner, item_note="Enhancing…"))

    def name_line_ink(rendered) -> int:
        line = _rgb(rendered.bgra)[PAD + TITLE_BAND_H:_dividers(rendered)[0], PAD:-PAD]
        return int((line > 80).any(axis=2).sum())

    assert name_line_ink(noted) > name_line_ink(bare) == 0
    assert noted.bgra.shape == bare.bgra.shape


def test_the_map_sits_where_it_sits_however_long_the_status_is(thumb):
    """The status band is one line deep and stays one line deep, so the map is
    anchored at the same place on every panel — a side that has picked up a filter
    does not find its map a line lower than the side that has not."""
    def corner(label: str):
        rendered = HudRenderer("portrait").render(
            _model(title=label, corner=HudCell(path="c.mp4", thumb=thumb)))
        (x, y, _w, _h), _path = rendered.targets.click[0]
        return x, y

    assert (corner("Looping actions · Latest · F-Mode · beta gamma")
            == corner("Locked · Shuffle") == corner(""))


def test_render_exposes_the_controls_it_drew(thumb):
    """Every drawn thumbnail, loop button and filter button comes back as a hit
    target, so what is clickable is exactly what is visible."""
    rendered = HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb),
               seeds=(HudCell(path="s1.mp4", thumb=thumb),),
               actions=(HudCell(path="a1.mp4", thumb=thumb, label="gamma"),),
               current_action="alpha")
    )

    assert [path for _rect, path in rendered.targets.click] == ["c.mp4", "s1.mp4", "a1.mp4"]
    assert sorted(kind for _rect, kind in rendered.targets.loop) == ["action", "seed"]
    assert [name for _rect, name in rendered.targets.filter] == ["alpha", "gamma"]
    assert rendered.targets.expand is not None


def test_a_panel_that_declares_no_buttons_holds_no_band_open_for_them():
    renderer = HudRenderer("landscape")
    bare = renderer.render(HudModel(funestra="landscape", title="Unlocked"))
    one_row = renderer.render(HudModel(funestra="landscape", title="Unlocked",
                                       rows=(funestra_rows("landscape")[-1],)))

    assert _declared(bare) == []
    assert one_row.bgra.shape[0] - bare.bgra.shape[0] == CTRL_BTN + 2 * SECTION_GAP + DIVIDER_H


def test_render_draws_the_sides_own_controls_even_with_no_clip():
    """The buttons are the side's, not the map's, so they are there before the
    first clip arrives — a satellite that came up empty can still be stepped off
    it, and still narrowed to its favorites."""
    rendered = HudRenderer("landscape").render(
        _model(funestra="landscape", locked=False, title="Unlocked"))

    assert _names(rendered) == [
        "prev", "next", "lock", "trash", "fmode", "reset", "minimize",
    ]


def test_the_minimize_button_wears_a_bar_rather_than_a_font_glyph():
    """The minimize mark Windows uses lives in a face these buttons don't load, and
    Pillow draws a ".notdef" tofu for a codepoint a face doesn't carry — so it is
    drawn: one horizontal run of ink across the middle of the button, wider than it
    is tall, which is what a title bar's minimize looks like everywhere."""
    rendered = HudRenderer("landscape").render(
        _model(funestra="landscape", title="Unlocked"))
    x, y, w, h = _rects(rendered)["minimize"]
    # The button's own outline is its border, so only the interior is the mark --
    # and the interior is the button's ground now, itself gray, so the mark is
    # what is BRIGHTER than that ground.
    inside = _rgb(rendered.bgra)[y + 2:y + h - 2, x + 2:x + w - 2]
    ys, xs = np.nonzero((inside > 150).all(axis=2))

    assert len(ys), "the minimize button drew no mark at all"
    assert xs.max() - xs.min() > ys.max() - ys.min()  # a bar, not a square or a glyph


def _lit_ink(rect, rendered) -> int:
    """How many pixels inside *rect* are the green a lit control fills with."""
    x, y, w, h = rect
    rgb = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)
    green = (rgb[:, :, 1] > 100) & (rgb[:, :, 0] < 100) & (rgb[:, :, 2] < 100)
    return int(green.sum())


def test_the_state_controls_and_favorite_mark_light_up_when_they_apply():
    """Green is what the dashboard's panel used, so everything that is a *state*
    keeps it: the lock button while the Funestra is locked, the F button while
    the Funestra is in F-mode, the star while the clip is a favorite."""
    def rendered_with(*, locked=False, favorites=False, is_favorite=False):
        return HudRenderer("landscape").render(
            _model(funestra="landscape", locked=locked, title="Unlocked",
                   is_favorite=is_favorite,
                   rows=funestra_rows("landscape", locked=locked, favorites=favorites)),
            video="example - scene one")

    off = rendered_with()
    on = rendered_with(locked=True, is_favorite=True, favorites=True)
    rects = _rects(on)

    assert _lit_ink(rects["lock"], on) > _lit_ink(rects["lock"], off)
    assert _lit_ink(rects["fmode"], on) > _lit_ink(rects["fmode"], off)
    assert _lit_ink(on.targets.favorite, on) > _lit_ink(off.targets.favorite, off)


def test_the_star_is_centered_under_the_dot():
    rendered = HudRenderer("landscape").render(
        HudModel(funestra="landscape", title="Unlocked", active=True, is_favorite=True),
        video="example - scene one")
    rgb = _rgb(rendered.bgra).astype(int)
    _x, star_top, _w, star_h = rendered.targets.favorite
    left_column = slice(PAD + MINUS_ROOM - 2, MINUS_ROOM + TITLE_X - 2)
    dot = (rgb[PAD:PAD + 14, left_column] > 200).all(axis=2)
    star_band = rgb[star_top:star_top + star_h, left_column]
    star = star_band[:, :, 1] - np.maximum(star_band[:, :, 0], star_band[:, :, 2]) > 40

    def middle(ink) -> float:
        columns = np.nonzero(ink.any(axis=0))[0]
        return (columns.min() + columns.max()) / 2

    assert abs(middle(dot) - middle(star)) <= 0.5


def test_the_bin_draws_red_because_it_takes_something_away():
    """Origenerator's Delete is red and the act reads the same wherever it
    appears, so the drawn button is what has to be red — a table saying which
    control is destructive says nothing about what came out on the panel."""
    rendered = HudRenderer("landscape").render(
        _model(funestra="landscape", title="Unlocked"))
    rects = _rects(rendered)

    def red_ink(name: str) -> int:
        """How far the reddest pixel of *name*'s button leads its own green."""
        x, y, w, h = rects[name]
        pixels = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)
        return int((pixels[:, :, 0] - pixels[:, :, 1]).max())

    assert red_ink("trash") > 60
    assert red_ink("prev") == 0  # and the red is the bin's, not the whole band's


def test_f_mode_wears_its_own_badge_rather_than_a_typed_letter():
    """`fmode_icon.ico` is a magenta five-by-five "F" — the mark the mode has on the
    taskbar and on the main console — and a letter set in the body face is a
    thin thing beside it.  The mark holds whether or not the mode is on; only what
    is beneath it changes."""
    for favorites in (False, True):
        rendered = HudRenderer("landscape").render(_model(
            funestra="landscape", title="Unlocked",
            rows=funestra_rows("landscape", favorites=favorites)))
        x, y, w, h = _rects(rendered)["fmode"]
        pixels = _rgb(rendered.bgra)[y:y + h, x:x + w]
        magenta = (pixels == np.array((200, 80, 160), dtype=pixels.dtype)).all(axis=2)
        ys, xs = np.nonzero(magenta)
        cell = (xs.max() - xs.min() + 1) / 5
        drawn = [
            "".join("#" if magenta[int(ys.min() + (r + 0.5) * cell),
                                   int(xs.min() + (c + 0.5) * cell)] else "."
                    for c in range(5))
            for r in range(5)
        ]

        assert drawn == list(LETTERS["F"]), favorites


def test_a_running_loops_button_fills_white_and_not_the_locks_green(thumb):
    """The lock and the star are the panel's two favorites marks, and green is
    theirs alone; a loop is just this side repeating a group, so its button lights
    in the plain white every other control here uses."""
    rendered = HudRenderer("portrait").render(_loop_model(thumb, ("corner", 0)))
    x, y, w, h = dict((kind, rect) for rect, kind in rendered.targets.loop)["seed"]
    rgb = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)

    assert (rgb > 240).all(axis=2).any()
    green = (rgb[:, :, 1] > 100) & (rgb[:, :, 0] < 100) & (rgb[:, :, 2] < 100)
    assert not green.any()


def test_the_playing_cell_is_brighter_than_the_others(tmp_path: Path):
    """The clip actually on screen is drawn at full opacity and the rest dim, so
    the bright one reads as "this is what's on" even mid-loop."""
    bright_thumb = tmp_path / "bright.jpg"
    Image.new("RGB", (40, 60), (240, 240, 240)).save(bright_thumb)
    cells = dict(
        corner=HudCell(path="c.mp4", thumb=str(bright_thumb)),
        seeds=(HudCell(path="s1.mp4", thumb=str(bright_thumb)),),
    )

    def corner_and_seed(playing) -> tuple[float, float]:
        rendered = HudRenderer("portrait").render(_model(playing=playing, **cells))
        corner_rect, seed_rect = rendered.targets.click[0][0], rendered.targets.click[1][0]

        def mean(rect):
            x, y, w, h = rect
            return float(_rgb(rendered.bgra)[y + 5:y + h - 5, x + 5:x + w - 5].mean())

        return mean(corner_rect), mean(seed_rect)

    corner_lit, seed_dim = corner_and_seed(("corner", 0))
    corner_dim, seed_lit = corner_and_seed(("seed", 0))
    assert corner_lit > corner_dim
    assert seed_lit > seed_dim


def _loop_model(thumb: str, playing, *, count: int = 12, loop: str = "seed") -> HudModel:
    """A seed row far longer than the map can draw, at *playing*."""
    return _model(
        locked=False, title=f"Looping {count + 1} seeds" if loop else "Unlocked",
        corner=HudCell(path="c.mp4", thumb=thumb),
        seeds=tuple(HudCell(path=f"s{i}.mp4", thumb=thumb) for i in range(count)),
        active_loop=loop, playing=playing,
    )


def _tail_ink(rendered) -> int:
    """Ink in the slot kept past the right-hand end of the drawn row, inset from its
    edges so the loop rectangle's own border is never counted as a mark."""
    corner_rect = rendered.targets.click[0][0]
    seed_rects = [rect for rect, _p in rendered.targets.click[1:]]
    _before, after = ellipsis_rects(corner_rect, seed_rects, [], "seed")
    x, y, w, h = after
    return int((_rgb(rendered.bgra)[y + 2:y + h - 2, x + 2:x + w - 2] > 100).sum())


def test_a_map_with_more_clips_than_fit_says_so_even_off_a_loop(thumb):
    """The mark is about the map, not about looping: a browse row longer than the
    panel draws what fits and says there is more, rather than dropping the rest
    silently."""
    long_row = HudRenderer("portrait").render(_loop_model(thumb, ("corner", 0), loop=""))
    short_row = HudRenderer("portrait").render(_loop_model(thumb, ("corner", 0), count=1, loop=""))

    assert _tail_ink(long_row) > 0
    assert _tail_ink(short_row) == 0


def test_switching_a_loop_off_leaves_the_map_exactly_where_it_was(thumb):
    """The whole of what a loop toggle may change is the loop's own chrome.  Given the
    same cells, the drawn map — which clips, in which rects — is identical looping and
    not, so turning the loop off takes away the lit button and the rectangle and
    nothing else."""
    renderer = HudRenderer("portrait")
    looping = renderer.render(_loop_model(thumb, ("seed", 5)))
    ended = renderer.render(_loop_model(thumb, ("seed", 5), loop=""))

    assert looping.targets.click == ended.targets.click
    assert looping.targets.expand == ended.targets.expand
    assert [rect for rect, _kind in looping.targets.loop] == [rect for rect, _kind in ended.targets.loop]


def test_the_more_mark_reads_as_three_dots(thumb):
    """Fat dots at a tight spacing merged into one pill.  The mark has to read as
    three dots, so there are gaps between them."""
    rendered = HudRenderer("portrait").render(_loop_model(thumb, ("corner", 0)))
    corner_rect = rendered.targets.click[0][0]
    seed_rects = [rect for rect, _p in rendered.targets.click[1:]]
    _before, after = ellipsis_rects(corner_rect, seed_rects, [], "seed")
    x, y, w, h = after
    row = (_rgb(rendered.bgra)[y + h // 2, x:x + w] > 100).any(axis=1)

    runs = sum(1 for i, on in enumerate(row) if on and not (i and row[i - 1]))
    assert runs == 3


def _marks_drawn(monkeypatch, painter: str) -> list[str]:
    drawn: list[str] = []
    real = getattr(satellite_hud_paint, painter)

    def spy(image, name, frame, color):
        drawn.append(name)
        real(image, name, frame, color)

    monkeypatch.setattr(satellite_hud_paint, painter, spy)
    return drawn


def test_the_more_marks_are_the_familys_dots_along_the_row_and_down_the_column(
        thumb, monkeypatch):
    drawn = _marks_drawn(monkeypatch, "paste_glyph")

    HudRenderer("portrait").render(_crowded("portrait", thumb))

    assert {"more", "more_vertical"} <= set(drawn)


def test_the_filter_button_wears_the_familys_filter(thumb, monkeypatch):
    drawn = _marks_drawn(monkeypatch, "draw_mark")

    HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb), current_action="alpha"))

    assert "filter" in drawn


def test_the_more_mark_does_not_touch_the_loop_rectangle(thumb):
    """Dots drawn hard against the rectangle read as part of its border rather than
    as a mark inside it."""
    rendered = HudRenderer("portrait").render(_loop_model(thumb, ("seed", 5)))
    corner_rect = rendered.targets.click[0][0]
    seed_rects = [rect for rect, _p in rendered.targets.click[1:]]
    rect = looped_group_rect(corner_rect, seed_rects, [], "seed", reserve=ELLIPSIS_ROOM)
    before, _after = ellipsis_rects(corner_rect, seed_rects, [], "seed")

    assert before[0] - rect[0] >= MAP_GAP
    bx, by, bw, bh = rect
    # The strip just inside the rectangle's left border carries no ink at all.
    assert int((_rgb(rendered.bgra)[by + 2:by + bh - 2, bx + 2:bx + MAP_GAP] > 100).sum()) == 0


def test_a_long_loop_draws_a_window_that_holds_the_clip_on_screen(thumb):
    """The reported bug: a loop longer than the map could draw kept showing its
    first cells, so once it advanced past them nothing was lit and the clip playing
    was not among the thumbnails at all.  The map now follows the loop."""
    rendered = HudRenderer("portrait").render(_loop_model(thumb, ("seed", 8)))

    drawn = [path for _rect, path in rendered.targets.click]
    assert "s8.mp4" in drawn


def test_a_loop_just_started_draws_the_clip_on_screen_in_the_corner(thumb):
    """At the moment the loop starts, the clip on screen is its head — so it is the
    top-left cell, never somewhere in the middle of the row."""
    rendered = HudRenderer("portrait").render(_loop_model(thumb, ("corner", 0)))

    drawn = [path for _rect, path in rendered.targets.click]
    assert drawn[0] == "c.mp4"


def test_a_long_loop_lights_the_clip_on_screen_wherever_it_has_got_to(tmp_path: Path):
    """The window is only worth having if the highlight lands on the right cell in
    it: the clip playing is drawn bright and its neighbors dim."""
    bright = tmp_path / "bright.jpg"
    Image.new("RGB", (40, 60), (240, 240, 240)).save(bright)
    rendered = HudRenderer("portrait").render(_loop_model(str(bright), ("seed", 8)))

    by_path = {path: rect for rect, path in rendered.targets.click}

    def mean(rect):
        x, y, w, h = rect
        return float(_rgb(rendered.bgra)[y + 5:y + h - 5, x + 5:x + w - 5].mean())

    lit = mean(by_path["s8.mp4"])
    others = [mean(rect) for path, rect in by_path.items() if path != "s8.mp4"]
    assert others and lit > max(others)


def test_a_long_loop_marks_that_it_runs_on_past_the_map(thumb):
    """"…" at the end of the row says the loop holds more than is drawn — without it
    a three-cell map of a thirty-clip loop looks like the whole set."""
    renderer = HudRenderer("portrait")
    long_loop = renderer.render(_loop_model(thumb, ("corner", 0)))
    short_loop = renderer.render(_loop_model(thumb, ("corner", 0), count=1))

    assert _tail_ink(long_loop) > 0
    assert _tail_ink(short_loop) == 0


def test_a_sliding_loop_window_never_shifts_the_map(thumb):
    """The map must hold still as the window slides — the ellipses appearing and
    going is exactly when a shifting layout would be most distracting.  Two
    mid-loop frames are the like-for-like pair: the one deliberate move — the
    action column stepping out to hang under the lit cell — happens as the loop
    leaves its head, not per advance."""
    renderer = HudRenderer("portrait")
    at_start = renderer.render(_loop_model(thumb, ("corner", 0)))
    midway = renderer.render(_loop_model(thumb, ("seed", 5)))
    later = renderer.render(_loop_model(thumb, ("seed", 6)))

    assert [rect for rect, _p in midway.targets.click] == [rect for rect, _p in later.targets.click]
    assert midway.targets.loop == later.targets.loop
    assert midway.targets.expand == later.targets.expand
    # The row itself never moves at all, head of the loop included; the action
    # button is the one thing that follows the column out along it.
    assert at_start.targets.click[0][0] == midway.targets.click[0][0]
    assert at_start.targets.expand == midway.targets.expand
    seed_buttons = lambda t: [rect for rect, kind in t.loop if kind == "seed"]
    assert seed_buttons(at_start.targets) == seed_buttons(midway.targets)


def test_the_action_column_stands_under_the_lit_cell_mid_loop(thumb):
    """Mid-loop the drawn column is the playing seed's own acts, so it hangs under
    the lit cell — left under the corner it would read as the corner seed's."""
    rendered = HudRenderer("portrait").render(_model(
        locked=False, title="Looping 13 seeds",
        corner=HudCell(path="c.mp4", thumb=thumb),
        seeds=tuple(HudCell(path=f"s{i}.mp4", thumb=thumb) for i in range(12)),
        actions=(HudCell(path="a0.mp4", thumb=thumb, label="Zeta"),),
        active_loop="seed", playing=("seed", 5),
    ))

    rects = {path: rect for rect, path in rendered.targets.click}
    corner_rect = rendered.targets.click[0][0]
    assert rects["a0.mp4"][0] == rects["s5.mp4"][0]  # under the lit cell…
    assert rects["a0.mp4"][0] != corner_rect[0]      # …not under the corner slot


def test_the_map_prints_how_big_each_axis_is(thumb):
    """The map draws only the cells that fit, so its top-left corner carries the
    counts — the only place the real size of each axis can be read.  They are always
    there, loop or no loop."""
    renderer = HudRenderer("portrait")

    def corner_ink(**counts) -> int:
        rendered = renderer.render(_model(corner=HudCell(path="c.mp4", thumb=thumb), **counts))
        (cx, cy, _cw, _ch), _path = rendered.targets.click[0]
        block = _rgb(rendered.bgra)[_map_top(rendered):cy, PAD:cx - MAP_GAP]
        return int((block > 80).sum())

    assert corner_ink(seed_count=12, action_count=4) > 0
    assert corner_ink() == 0  # nothing to say before the index has answered


def test_the_filtered_actions_label_is_lit(thumb):
    """A filter shows on the map, on the row it holds you to — so which act you are
    filtered to is readable where you would act on it, beside the lit button that
    lifts it."""
    renderer = HudRenderer("portrait")

    def gutter_ink(filter_query: str) -> int:
        rendered = renderer.render(_model(
            corner=HudCell(path="c.mp4", thumb=thumb),
            actions=(HudCell(path="a1.mp4", thumb=thumb, label="gamma"),),
            current_action="alpha", filter_query=filter_query,
        ))
        # The corner's own row label, in the gutter beside it — "alpha".  Past
        # the filter button at the gutter's head: its funnel is drawn at full
        # strength like every resting mark on this panel, so counting from the
        # gutter's left edge would count the button rather than the label.
        band = _label_band(rendered)
        # Near-white in all three channels: the strike under the act is drawn
        # red, whose own red channel is as bright as a lit label's.
        return int(band.sum())

    assert gutter_ink("alpha") > 0
    assert gutter_ink("") == 0
    assert gutter_ink("gamma") == 0  # …that row's label lights, not this one


def _filter_button_fill(rendered, action: str) -> int:
    """How much lit ground the *action* row's filter button carries.

    The family's blue, which is what "in force" looks like on every panel in the
    room: green across these HUDs means the favorites and the funscripts, and a
    filter is neither.  Only the lock keeps a color of its own.
    """

    want = (colors.BLUE.red(), colors.BLUE.green(), colors.BLUE.blue())
    x, y, w, h = dict((name, rect) for rect, name in rendered.targets.filter)[action]
    rgb = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)
    return int((abs(rgb - want).max(axis=2) <= 2).sum())


def test_the_filter_button_lights_on_the_act_the_side_is_filtered_to(thumb):
    """The filter button is the loop buttons' twin — lit while its row is one the
    filter keeps, so the control that lifts a filter is the lit one that set it, and
    a filter set any other way still shows on the row it holds you to."""
    renderer = HudRenderer("portrait")

    def lit_ink(filter_query: str) -> int:
        return _filter_button_fill(renderer.render(_model(
            corner=HudCell(path="c.mp4", thumb=thumb),
            actions=(HudCell(path="a1.mp4", thumb=thumb, label="gamma"),),
            current_action="alpha", filter_query=filter_query,
        )), "alpha")

    assert lit_ink("alpha") > 0
    assert lit_ink("") == 0
    assert lit_ink("gamma") == 0  # …that row's button lights, not this one


def test_a_row_the_filter_only_partly_matches_still_lights(thumb):
    """fun_time keeps a "Side Gamma" clip under a "gamma" filter, so its row stays
    lit while it is on screen.  Lighting only an exact "gamma" put the mark out the
    moment such a clip came up and back on at the next exact one — the panel saying
    the filter had dropped while the playlist under it had not changed at all."""
    renderer = HudRenderer("portrait")

    def lit_ink(current_action: str) -> int:
        return _filter_button_fill(renderer.render(_model(
            corner=HudCell(path="c.mp4", thumb=thumb),
            current_action=current_action, filter_query="gamma",
        )), current_action)

    assert lit_ink("gamma") > 0
    assert lit_ink("side gamma") > 0      # the query is one word of the act
    assert lit_ink("gamma, theta") > 0    # one of the clip's two acts
    assert lit_ink("alpha") == 0


def _label_band(rendered):
    """The corner row's act names as a near-white mask: the gutter between the
    filter button at its head and the map beside it, down as far as the strike
    that hangs under the words.

    Bounded by the strike rather than by the row, because the words and the
    strike are centered in the row together — so half the ROW is no longer the
    seam between a two-act label's two acts.
    """
    (cx, cy, _cw, ch), _path = rendered.targets.click[0]
    lower = rendered.targets.wrong_action[1] if rendered.targets.wrong_action else cy + ch
    return (_rgb(rendered.bgra)[cy:lower, PAD + FILTER_BTN + MAP_GAP:cx - MAP_GAP] > 200).all(axis=2)


def _white_halves(rendered) -> tuple[int, int]:
    """Near-white ink across the corner row's act names, split into the upper and
    lower halves of the words — a row carrying two acts draws one in each.

    Measured past the filter button at the head of the row: that button fills white
    when it is lit, which is the same ink the labels use.
    """
    band = _label_band(rendered)
    half = band.shape[0] // 2
    return int(band[:half].sum()), int(band[half:].sum())


def test_only_the_act_the_filter_matched_is_lit_on_a_two_act_row(thumb):
    """A clip can carry two acts ("Gamma, Theta") and a one-act filter keeps it for
    one of them, so only that one goes white — lighting the whole label named an act
    the filter has nothing to do with.  The acts stack in order, so the lit one moves
    between the halves of the row as the query changes."""
    renderer = HudRenderer("portrait")

    def halves(filter_query: str) -> tuple[int, int]:
        return _white_halves(renderer.render(_model(
            corner=HudCell(path="c.mp4", thumb=thumb),
            current_action="gamma, theta", filter_query=filter_query,
        )))

    gamma_upper, gamma_lower = halves("gamma")
    theta_upper, theta_lower = halves("theta")

    assert gamma_upper > 0 and gamma_lower == 0
    assert theta_lower > 0 and theta_upper == 0
    assert halves("alpha") == (0, 0)


def test_a_filter_set_from_a_two_act_clip_lights_both_of_its_acts(thumb):
    """Pressing a two-act row's button filters to both acts, and fun_time keeps the
    clip for both — so both go white.  Neither did: the two-act query matched neither
    act on its own, so the row you had just filtered to read as unfiltered."""
    rendered = HudRenderer("portrait").render(_model(
        corner=HudCell(path="c.mp4", thumb=thumb),
        current_action="gamma, theta motion", filter_query="gamma, theta motion",
    ))

    upper, lower = _white_halves(rendered)

    assert upper > 0 and lower > 0


@pytest.mark.parametrize("camera", ["xyz", "side"])
def test_a_leading_camera_word_stays_gray_when_its_act_is_filtered(camera, thumb):
    """A camera word in front of an act is drawn as an act of its own: under a
    "gamma" filter only "Gamma" is why the clip is here, so the camera word stays
    gray rather than reading as part of what was asked for.

    Every word the source names, because Evolver's backfill scopes every act it
    records by one of them — so reading only the first would leave every clip
    scoped by another lighting both of its words.
    """
    renderer = HudRenderer("portrait")

    def halves(filter_query: str) -> tuple[int, int]:
        return _white_halves(renderer.render(_model(
            corner=HudCell(path="c.mp4", thumb=thumb), camera_words=("Side", "XYZ"),
            current_action=f"{camera} gamma", filter_query=filter_query,
        )))

    scope, gamma = halves("gamma")

    assert scope == 0 and gamma > 0
    # …and a filter on the row itself names both, so both light.
    assert all(half > 0 for half in halves(f"{camera} gamma"))


def test_the_filter_button_carries_a_funnel_and_not_an_empty_square(thumb):
    """The funnel is drawn rather than typed — no face on the machine carries one —
    so what has to hold is that there is a mark inside the button's border at all:
    an empty square says nothing about what the button does."""
    rendered = HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb), current_action="alpha"))

    x, y, w, h = dict((name, rect) for rect, name in rendered.targets.filter)["alpha"]
    # Inside the rounded border, so the square itself can't be what is counted.
    inside = _rgb(rendered.bgra)[y + 3:y + h - 3, x + 3:x + w - 3]
    assert (inside > 80).all(axis=2).sum() > 0


def test_a_long_action_name_is_never_drawn_over_its_filter_button(thumb):
    """The gutter holds the button and the name beside it, so the name is sized into
    what is left rather than reaching back across the button — which would stamp a
    funnel through the middle of the word."""
    renderer = HudRenderer("portrait")

    def button_pixels(action: str) -> np.ndarray:
        rendered = renderer.render(
            _model(corner=HudCell(path="c.mp4", thumb=thumb), current_action=action))
        x, y, w, h = dict((name, rect) for rect, name in rendered.targets.filter)[action]
        return _rgb(rendered.bgra)[y:y + h, x:x + w]

    assert np.array_equal(button_pixels("motion"), button_pixels("iota"))


def test_the_map_stands_in_the_same_place_whatever_its_acts_are_called(thumb):
    renderer = HudRenderer("portrait")

    def rendered(act: str):
        return renderer.render(_model(
            corner=HudCell(path="c.mp4", thumb=thumb), current_action=act,
            actions=(HudCell(path="a1.mp4", thumb=thumb, label=act),)))

    short, long = rendered("iota"), rendered("wmw longestword")

    assert short.bgra.shape == long.bgra.shape
    assert short.targets.click == long.targets.click


def test_a_missing_thumbnail_still_draws_the_map():
    """A clip whose thumbnail fun_time hasn't produced yet gets a placeholder, so
    the map appears instantly instead of waiting on a frame grab."""
    rendered = HudRenderer("portrait").render(_model(corner=HudCell(path="c.mp4")))

    assert rendered.targets.click == [(rendered.targets.click[0][0], "c.mp4")]
    x, y, w, h = rendered.targets.click[0][0]
    assert (w, h) == (slot_width("portrait"), MAP_THUMB_H)


def test_hovering_a_button_draws_its_tooltip(thumb):
    """The tooltip is drawn into the panel — there is no native tooltip inside a
    video frame — so hovering adds ink the un-hovered render doesn't have."""
    renderer = HudRenderer("portrait")
    model = _model(corner=HudCell(path="c.mp4", thumb=thumb))

    plain = renderer.render(model)
    tipped = renderer.render(model, hover_loop="seed", hover_tip="Loop this seed row",
                             hover_pos=(40, 40))

    assert not np.array_equal(plain.bgra, tipped.bgra)


def test_a_panel_with_no_clip_yet_still_names_the_button_under_the_pointer():
    renderer = HudRenderer("landscape")
    model = _model(funestra="landscape", title="Unlocked")
    x, y, _w, _h = _rects(renderer.render(model))["lock"]

    short_tip = renderer.render(model, hover_tip="Lock", hover_pos=(x + 2, y + 2))
    long_tip = renderer.render(model, hover_tip="Lock this clip", hover_pos=(x + 2, y + 2))

    assert not np.array_equal(short_tip.bgra, long_tip.bgra)


def test_a_tooltip_longer_than_the_panel_is_wide_stays_on_the_panel(thumb):
    """The reported bug: the trash button's tooltip wants more width than a
    portrait panel has, so it was drawn straight off the right edge and read
    "…when it is not a favo".  It wraps now, which is funestra's job — this
    guards that the satellite actually hands it the panel's own bounds, since
    passing anything wider would put the tooltip back over the edge."""
    renderer = HudRenderer("portrait")
    model = _model(corner=HudCell(path="c.mp4", thumb=thumb))
    plain = _rgb(renderer.render(model).bgra)

    def tooltip_bounds(text: str) -> tuple[int, int, int]:
        """(upper, lower, right) of what hovering with *text* added to the panel."""
        tipped = _rgb(renderer.render(model, hover_tip=text, hover_pos=(33, 44)).bgra)
        rows, cols = np.nonzero((tipped != plain).any(axis=2))
        assert len(rows), f"hovering with {text!r} drew nothing"
        return rows.min(), rows.max(), cols.max()

    upper, lower, right = tooltip_bounds(
        "Unfavorite it — or mark weird when it is not a favorite, and it is asked"
        " about again the next time it comes round")
    short_upper, short_lower, _ = tooltip_bounds("Bin")

    assert right < plain.shape[1] - 1  # it stopped short of the far edge
    assert lower - upper > short_lower - short_upper  # having wrapped to fit


def test_the_reset_button_is_never_lit():
    """The lock and F-mode are states the Funestra sits in, so they light while
    they are on; a reset is over the moment it lands, and a button that stayed
    lit would say the Funestra was sitting in one."""
    def rendered_with(**state):
        return HudRenderer("landscape").render(_model(
            funestra="landscape", title="Locked", rows=funestra_rows("landscape", **state)))

    resting = rendered_with()
    lit = rendered_with(locked=True, favorites=True)
    rects = _rects(lit)

    assert _lit_ink(rects["lock"], lit)  # the states that do light are alight
    assert _lit_ink(rects["reset"], lit) == 0
    assert _lit_ink(rects["reset"], resting) == 0


def test_column_labels_are_clipped_to_their_column(thumb):
    renderer = HudRenderer("portrait")
    rendered = renderer.render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb),
               seeds=(HudCell(path="s1.mp4", thumb=thumb),))
    )

    (cx, _cy, cw, _ch), _path = rendered.targets.click[0]
    (sx, _sy, _sw, _sh), _seed = rendered.targets.click[1]
    strip_y = _map_top(rendered)
    header = _rgb(rendered.bgra)[strip_y:strip_y + COL_LABEL_H, cx + cw:sx]
    assert (header > 60).sum() == 0


def test_the_mode_pair_renders_and_is_pressable(thumb):
    # The satellite counterpart of the console's Video/Genau row: with a
    # session mode published, the pair is on the control band with real hit
    # targets, and a press posts the other mode's activation verbatim.
    rendered = HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb),
               rows=funestra_rows("portrait", mode="kino"))
    )

    assert _names(rendered)[:2] == ["satellites_kino_activate", "origenerator_activate"]
    clicks = HudClicks("portrait")
    rect = _rects(rendered)["origenerator_activate"]
    assert clicks.press(rendered.targets, rect[0] + 2, rect[1] + 2,
                        now=0.0) == "origenerator_activate"


def test_the_mode_row_leads_and_minimize_rides_it(thumb):
    """Like the main console: the mode pair gets a row of its own above the
    controls, and minimize — being about the side's window, not the clip —
    rides that row rather than sitting among the transport."""
    rendered = HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb),
               rows=funestra_rows("portrait", mode="kino"))
    )

    by_name = _rects(rendered)
    mode_y = by_name["satellites_kino_activate"][1]
    # Minimize shares the mode row, to the right of the pair.
    assert by_name["minimize"][1] == mode_y
    assert by_name["minimize"][0] > by_name["origenerator_activate"][0]
    # The rest of the controls sit on their own band, one below.
    for name in ("prev", "next", "lock", "trash", "fmode"):
        assert by_name[name][1] == mode_y + CTRL_BAND_H
    # From its new home the button still posts the side's own command.
    clicks = HudClicks("portrait")
    rect = by_name["minimize"]
    assert clicks.press(rendered.targets, rect[0] + 2, rect[1] + 2,
                        now=0.0) == "portrait_minimize"


def test_a_mode_label_stays_white_on_its_blue(thumb):
    """The mark reverses out of a LIGHT fill only.  Dark ink on the mode pair's
    blue turned those labels black while the main console's stayed white for
    the same state, which is the inconsistency the shared dressing exists to
    prevent."""

    renderer = HudRenderer("portrait")
    rendered = renderer.render(_model(
        corner=HudCell(path="c.mp4", thumb=thumb),
        rows=funestra_rows("portrait", mode="origenerator"),
    ))
    rect = _rects(rendered)["origenerator_activate"]
    x, y, w, h = rect
    rgb = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)

    assert (abs(rgb - np.array(BLUE)).max(axis=2) <= 2).any()   # it is on blue
    assert (abs(rgb - np.array(WHITE)).max(axis=2) <= 2).any()  # the word is white


def test_the_unlit_mode_keeps_its_ordinary_ink(thumb):

    renderer = HudRenderer("portrait")
    rendered = renderer.render(_model(
        corner=HudCell(path="c.mp4", thumb=thumb),
        rows=funestra_rows("portrait", mode="origenerator"),
    ))
    rect = _rects(rendered)["satellites_kino_activate"]
    x, y, w, h = rect
    rgb = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)

    assert (abs(rgb - np.array(TEXT_PRIMARY)).max(axis=2) <= 2).any()


def _blue_ink(rect, rendered) -> int:
    """How many pixels inside *rect* are the family's mode blue."""
    x, y, w, h = rect
    rgb = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)
    blue = (rgb[:, :, 2] > 140) & (rgb[:, :, 2] > rgb[:, :, 0] + 40) & (
        rgb[:, :, 2] > rgb[:, :, 1] + 30)
    return int(blue.sum())


def _order_band(*, newest: bool | None = None, **overrides):
    return HudRenderer("landscape").render(_model(
        funestra="landscape", title="Unlocked",
        rows=funestra_rows("landscape", newest=newest), **overrides))


def test_exactly_one_of_the_browse_order_pair_is_lit_and_it_lights_blue():
    """Neither is ever off — the side browses in one order or the other — so the
    light says which of the two you are in, and it says it in the family's mode
    blue rather than in the active gray a plain toggle takes."""
    shuffled, newest = _order_band(newest=False), _order_band(newest=True)
    rects = _rects(newest)

    assert _blue_ink(rects["shuffle"], shuffled) > _blue_ink(rects["shuffle"], newest)
    assert _blue_ink(rects["latest"], newest) > _blue_ink(rects["latest"], shuffled)
    # And never the favorites' green, which would say the wrong thing entirely.
    assert _lit_ink(rects["shuffle"], shuffled) == 0
    assert _lit_ink(rects["latest"], newest) == 0


def test_the_panel_is_wide_enough_for_the_band_it_grew():
    """The control band is five groups now and outruns a portrait map on its own.
    A row the panel cannot hold clips away in silence — the buttons past the edge
    are simply not drawn — so the panel is measured around the band."""
    rendered = _order_band(newest=False)
    width = rendered.bgra.shape[1]
    last = max(x + w for (x, _y, w, _h), _button in rendered.targets.buttons)

    assert last + PAD <= width


def test_a_funestra_that_says_its_rate_carries_a_playback_speed_row():
    def names(**overrides):
        return _names(_order_band(**overrides))

    assert "speed_down" not in names()
    assert names(playback_speed=1.0)[-2:] == ["speed_down", "speed_up"]


def test_the_speed_row_is_a_band_of_its_own_between_the_controls_and_the_map(thumb):
    corner = HudCell(path="c.mp4", thumb=thumb)
    without = HudRenderer("portrait").render(_model(corner=corner))
    with_row = HudRenderer("portrait").render(_model(corner=corner, playback_speed=1.0))
    rows = {short_name(button): rect[1] for rect, button in with_row.targets.buttons}

    assert with_row.bgra.shape[0] == without.bgra.shape[0] + CTRL_BAND_H
    assert rows["speed_down"] == rows["prev"] + CTRL_BAND_H
    assert with_row.targets.click[0][0][1] == without.targets.click[0][0][1] + CTRL_BAND_H


def test_the_speed_row_draws_its_buttons_and_reads_out_the_rate():
    normal, faster = _order_band(playback_speed=1.0), _order_band(playback_speed=1.5)
    buttons = {short_name(button): rect for rect, button in normal.targets.buttons}
    _x, row_y, _w, row_h = buttons["speed_down"]

    assert not np.array_equal(normal.bgra[row_y:row_y + row_h], faster.bgra[row_y:row_y + row_h])
    for name in ("speed_down", "speed_up"):
        x, y, w, h = buttons[name]
        assert (_rgb(normal.bgra)[y:y + h, x:x + w].min(axis=2) > 200).any(), name


def _amber_ink(rect, rendered) -> int:
    """How many pixels inside *rect* are the amber an enhanced mark is drawn in."""
    x, y, w, h = rect
    rgb = _rgb(rendered.bgra)[y:y + h, x:x + w].astype(int)
    amber = (rgb[:, :, 0] > 200) & (rgb[:, :, 1] > 150) & (rgb[:, :, 2] < 160) & (rgb[:, :, 1] < rgb[:, :, 0])
    return int(amber.sum())


def test_the_enhanced_switch_wears_amber_and_fills_with_it_when_on():
    """Amber is what an enhanced picture is marked with across this family, so
    the switch that keeps only those wears its mark in amber at rest and its
    whole ground in amber while it is on — never the favorites' green, which
    would say the wrong thing about what was kept."""
    def rendered_with(on: bool):
        return HudRenderer("landscape").render(_model(
            funestra="landscape", title="Unlocked",
            rows=funestra_rows("landscape", enhanced=on)))

    off, on = rendered_with(False), rendered_with(True)
    rect = _rects(on)["enhanced"]

    assert _amber_ink(rect, off) > 0                      # the mark itself, at rest
    assert _amber_ink(rect, on) > _amber_ink(rect, off)   # the ground, when on
    assert _lit_ink(rect, on) == 0                        # and no green anywhere in it


def test_the_enhanced_switch_keeps_its_place_under_a_mode_row(thumb):
    """With the mode pair leading the panel, the switch stays on the control band
    just ahead of reset, and the band is measured with it — so a portrait panel,
    whose map is narrower than its controls, still holds the whole row."""
    rendered = HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb),
               rows=funestra_rows("portrait", mode="origenerator", enhanced=False)))
    by_name = _rects(rendered)
    width = rendered.bgra.shape[1]

    assert by_name["enhanced"][1] == by_name["fmode"][1] == by_name["reset"][1]
    assert by_name["fmode"][0] < by_name["enhanced"][0] < by_name["reset"][0]
    assert by_name["reset"][0] + by_name["reset"][2] + PAD <= width


class TestTheDeviceOnAHostThatDrivesItself:
    """A host that drives the OSR2 itself wears ONE panel, not two.

    Origenerator's shows floated this HUD for the set and the main console
    underneath it for the device, which put two titles that disagreed
    and two copies of prev/next/lock/trash on one screen.  So a source that
    has a device to report says so on its own panel: the same line and the
    same readout the main console draws, from the same code.
    """

    @staticmethod
    def _rendered(**extra):
        return HudRenderer("portrait").render(
            _model(title="Unlocked", **extra))

    def test_a_source_that_names_no_driver_grows_no_device_line(self):
        """Every satellite is one: fun_time's Funestras report the set and
        nothing about the OSR2, and their panel must not change shape."""
        assert self._rendered().bgra.shape == self._rendered().bgra.shape
        assert (self._rendered(osr2=Osr2State.ROBOT_HAND).bgra.shape[0]
                > self._rendered().bgra.shape[0])

    def test_the_line_says_which_driver_has_the_device(self):
        rgb = _rgb(self._rendered(osr2=Osr2State.ROBOT_HAND).bgra)
        assert (rgb == np.array(BLUE)).all(axis=-1).any()

    def test_a_control_on_that_line_is_pressable(self):
        park = Button("robot_hand_park", "P", "Parked")
        rendered = self._rendered(osr2=Osr2State.ROBOT_HAND, osr2_controls=(park,))
        assert park in [button for _rect, button in rendered.targets.buttons]

    def test_the_max_intensity_on_that_line_is_a_slider_a_press_sets(self):
        rendered = self._rendered(osr2=Osr2State.ROBOT_HAND, max_intensity=35)
        (max_intensity,) = [band for band in rendered.targets.tracks if band.axis == MAX_INTENSITY]
        x, y, w, h = max_intensity.rect

        assert track_command(max_intensity, x + w - 1, y + h // 2) == "max_intensity_100"

    def test_a_hold_is_named_ahead_of_whoever_would_have_been_driving(self):
        """The host says what the wire says AND what it is doing to the device,
        the way the main console's source does, and the panel resolves the two
        the same way the console resolves them."""
        driving = _rgb(self._rendered(osr2=Osr2State.FUNSCRIPT).bgra)
        parked = _rgb(self._rendered(osr2=Osr2State.FUNSCRIPT,
                                     osr2_control=OSR2_PARKED).bgra)

        assert (driving == np.array(GREEN)).all(axis=-1).any()
        assert not (parked == np.array(GREEN)).all(axis=-1).any()

    def test_a_paused_rooms_line_reads_as_a_parked_ones_does(self):
        def panel(control: str, *, paused: bool) -> np.ndarray:
            return self._rendered(osr2=Osr2State.ROBOT_HAND, osr2_control=control,
                                  paused=paused).bgra

        paused = panel(OSR2_DRIVING, paused=True)

        assert np.array_equal(paused, panel(OSR2_PARKED, paused=False))
        assert not np.array_equal(paused, panel(OSR2_DRIVING, paused=False))

    def test_the_readouts_speed_amp_and_center_buttons_take_presses_in_a_paused_room(self):
        rendered = self._rendered(osr2=Osr2State.ROBOT_HAND, osr2_control=OSR2_DRIVING,
                                  paused=True, drive=_wave())
        placed = {button.command: rect for rect, button in rendered.targets.buttons}
        clicks = HudClicks("portrait")

        def posts(command: str) -> str:
            x, y, w, h = placed[command]
            return clicks.press(rendered.targets, x + w // 2, y + h // 2, now=0.0)

        assert {command for command in CONTROL_TIPS if posts(command) == command} == set(CONTROL_TIPS)

    def test_the_readout_is_drawn_under_the_line(self):
        with_readout = self._rendered(osr2=Osr2State.ROBOT_HAND, drive=DriveHud())
        line_only = self._rendered(osr2=Osr2State.ROBOT_HAND)
        assert with_readout.bgra.shape[0] > line_only.bgra.shape[0]
        assert with_readout.bgra.shape[1] >= SECTION_W + 2 * PAD

    def test_the_readouts_own_marks_post_what_they_are_pressed_for(self):
        rendered = self._rendered(osr2=Osr2State.ROBOT_HAND,
                                  drive=DriveHud(driven=DRIVEN_BY_ROBOT_HAND))
        posted = [button.command for _rect, button in rendered.targets.buttons]
        assert "robot_hand_speed_up" in posted

    def test_the_map_hangs_under_the_device_at_the_outside_of_the_panel(self, thumb):
        rendered = HudRenderer("portrait").render(_model(
            title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb),
            seeds=(HudCell(path="s.mp4", thumb=thumb),), seed_count=2,
            osr2=Osr2State.ROBOT_HAND,
            drive=DriveHud(driven=DRIVEN_BY_ROBOT_HAND)))
        map_top = min(y for (_x, y, _w, _h), _path in rendered.targets.click)

        assert rendered.targets.tracks
        assert all(band.rect[1] + band.rect[3] <= map_top for band in rendered.targets.tracks)

    def test_the_rows_that_aim_the_device_stay_between_the_sets_bands_and_the_readout(
            self, thumb):
        aim = (Button("robot_hand_toggle_learned", "hi", "Human inspired"),
               Button("robot_hand_park", "P", "Parked"))
        rendered = HudRenderer("portrait").render(_model(
            title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb),
            seeds=(HudCell(path="s.mp4", thumb=thumb),), seed_count=2,
            osr2=Osr2State.ROBOT_HAND, osr2_rows=(aim,),
            drive=DriveHud(driven=DRIVEN_BY_ROBOT_HAND)))
        placed = {button.command: rect for rect, button in rendered.targets.buttons}

        assert placed["robot_hand_toggle_learned"][1] > placed["portrait_prev"][1]
        assert all(band.rect[1] > placed["robot_hand_park"][1]
                   for band in rendered.targets.tracks)

    def test_the_map_is_set_off_from_the_device_by_a_line(self, thumb):
        drive = DriveHud(driven=DRIVEN_BY_ROBOT_HAND)
        rendered = HudRenderer("portrait").render(_model(
            title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb),
            seeds=(HudCell(path="s.mp4", thumb=thumb),), seed_count=2,
            osr2=Osr2State.ROBOT_HAND, drive=drive))
        readout_top = rendered.targets.tracks[0].rect[1] - tracks(0, 0, drive)[0].rect[1]
        readout_end = readout_top + section_size()[1]

        assert _lines_between(rendered, readout_end, _map_top(rendered)) == 1

    def test_a_press_in_a_band_takes_hold_of_it_and_sets_it(self):
        rendered = self._rendered(osr2=Osr2State.ROBOT_HAND,
                                  drive=DriveHud(driven=DRIVEN_BY_ROBOT_HAND))
        clicks = HudClicks("portrait")
        band = rendered.targets.tracks[0]
        x, y, w, h = band.rect

        posted = clicks.press(rendered.targets, x + w // 2, y + h // 2, now=0.0)

        assert posted.startswith(f"robot_hand_{band.axis}_")
        assert clicks.holding is True
        clicks.release()
        assert clicks.holding is False


def _wave(offset: float = 0.0) -> DriveHud:
    return DriveHud(speed=50, amplitude=80, center=50,
                    waveform=tuple(0.5 + 0.4 * np.sin(i / 6 + offset) for i in range(80)))


class TestTheReadoutIsDrawnAsTheMainConsoleDrawsIt:
    def test_the_trace_holds_still_while_nothing_is_driving(self):
        renderer = HudRenderer("portrait")
        first = renderer.render(_model(osr2=Osr2State.OFF, drive=_wave(0.0))).bgra.copy()

        later = renderer.render(_model(osr2=Osr2State.OFF, drive=_wave(3.0))).bgra

        assert np.array_equal(later, first)

    def test_it_moves_again_the_moment_something_is_driving(self):
        renderer = HudRenderer("portrait")
        still = renderer.render(_model(osr2=Osr2State.OFF, drive=_wave(0.0))).bgra.copy()

        moving = renderer.render(_model(osr2=Osr2State.ROBOT_HAND, drive=_wave(3.0))).bgra

        assert not np.array_equal(moving, still)

    def test_a_funestras_own_composed_trace_keeps_sliding_while_the_device_is_on(self):
        renderer = HudRenderer("portrait")
        first = renderer.render(_model(osr2=Osr2State.FUNSCRIPT, drive=_wave(0.0),
                                       drive_composed=True)).bgra.copy()

        later = renderer.render(_model(osr2=Osr2State.FUNSCRIPT, drive=_wave(3.0),
                                       drive_composed=True)).bgra

        assert not np.array_equal(later, first)

    def test_a_funestras_own_composed_trace_holds_still_with_the_device_off(self):
        renderer = HudRenderer("portrait")
        first = renderer.render(_model(osr2=Osr2State.OFF, drive=_wave(0.0),
                                       drive_composed=True)).bgra.copy()

        later = renderer.render(_model(osr2=Osr2State.OFF, drive=_wave(3.0),
                                       drive_composed=True)).bgra

        assert np.array_equal(later, first)

    def test_a_held_device_is_a_gray_line_nobody_can_press(self):
        rendered = HudRenderer("portrait").render(_model(
            osr2=Osr2State.ROBOT_HAND, osr2_control=OSR2_PARKED, drive=_wave()))
        band = rendered.targets.tracks[0]
        x, y, w, h = band.rect

        assert not (_rgb(rendered.bgra) == np.array(BLUE)).all(axis=-1).any()
        assert HudClicks("portrait").press(
            rendered.targets, x + w // 2, y + h // 2, now=0.0) == ""


class _Block:
    """A source's own block: a slab of a fixed size in a color nothing else on
    the panel wears, with one control."""

    MARK = (3, 250, 7)

    def __init__(self, size: tuple[int, int] = (120, 30)) -> None:
        self._size = size
        self.button = Button("cancel|j1", "Cancel", "Cancel this run")
        self.painted_at: tuple[int, int, int] | None = None
        self.pointer: tuple[int, int] | None = None

    def size(self) -> tuple[int, int]:
        return self._size

    def paint(self, image, x, y, width, pointer):
        self.painted_at, self.pointer = (x, y, width), pointer
        ImageDraw.Draw(image).rectangle(
            [x, y, x + self._size[0] - 1, y + self._size[1] - 1], fill=(*self.MARK, 255))
        return [((x, y, 40, 18), self.button)]


class TestTheBlockASourcePaintsAtTheFoot:
    """A host that is more than a Funestra says the rest of it here.

    Everything above is the panel's own — the set, and the device on a host
    that drives one — and a host with work of its own to report would need a
    second panel for it, which is the two-panels-on-one-screen this HUD grew
    the device block to end.  So the panel leaves room at its foot and the
    source paints there, in the panel's own look, with its controls pressed
    and named like the panel's own.
    """

    @staticmethod
    def _rendered(block=None, **extra):
        return HudRenderer("portrait").render(
            _model(title="Unlocked", foot=block, **extra))

    def test_a_source_with_no_block_of_its_own_grows_none(self):
        """Every satellite is one, and their panels must not change shape."""
        block = _Block()
        assert (self._rendered(block).bgra.shape[0]
                > self._rendered().bgra.shape[0])

    def test_it_is_painted_under_the_device_and_over_the_map(self, thumb):
        block = _Block()
        rendered = self._rendered(
            block, corner=HudCell(path="c.mp4", thumb=thumb),
            seeds=(HudCell(path="s.mp4", thumb=thumb),), seed_count=2,
            osr2=Osr2State.ROBOT_HAND, drive=DriveHud(driven=DRIVEN_BY_ROBOT_HAND))
        painted = np.argwhere((_rgb(rendered.bgra) == np.array(_Block.MARK)).all(axis=-1))

        assert painted.size
        assert painted[:, 0].min() > max(band.rect[1] + band.rect[3]
                                         for band in rendered.targets.tracks)
        assert painted[:, 0].max() < _map_top(rendered)

    def test_the_map_is_set_off_from_it_by_a_line(self, thumb):
        block = _Block()
        rendered = self._rendered(
            block, corner=HudCell(path="c.mp4", thumb=thumb),
            seeds=(HudCell(path="s.mp4", thumb=thumb),), seed_count=2)
        painted = np.argwhere((_rgb(rendered.bgra) == np.array(_Block.MARK)).all(axis=-1))

        assert _lines_between(rendered, painted[:, 0].max() + 1, _map_top(rendered)) == 1

    def test_it_is_set_off_from_the_sets_own_bands_by_a_line(self):
        block = _Block()
        rendered = self._rendered(block)
        painted = np.argwhere((_rgb(rendered.bgra) == np.array(_Block.MARK)).all(axis=-1))
        bands_end = max(y + h for (_x, y, _w, h), button in rendered.targets.buttons
                        if button is not block.button)

        assert _lines_between(rendered, bands_end, painted[:, 0].min()) == 1

    def test_the_panel_widens_to_hold_it(self):
        wide = _Block(size=(600, 30))
        assert self._rendered(wide).bgra.shape[1] >= 600 + 2 * PAD

    def test_it_is_painted_across_the_panels_own_width(self):
        block = _Block()
        width = self._rendered(block).bgra.shape[1]

        assert block.painted_at == (PAD, block.painted_at[1], width - 2 * PAD)

    def test_its_controls_are_pressed_and_named_like_the_panels_own(self):
        block = _Block()
        rendered = self._rendered(block)
        x, y, w, h = next(rect for rect, button in rendered.targets.buttons
                          if button is block.button)

        posted = HudClicks("portrait").press(rendered.targets, x + w // 2, y + h // 2,
                                             now=0.0)

        assert posted == "cancel|j1"
        assert button_tooltip(rendered.targets, x + w // 2, y + h // 2) == block.button.tooltip

    def test_a_hovered_control_of_its_own_is_told_where_the_pointer_is(self):
        block = _Block()
        self._rendered(block)  # no hover: the block is told there is none
        assert block.pointer is None

        HudRenderer("portrait").render(_model(title="Unlocked", foot=block),
                                       hover_tip="Cancel this run", hover_pos=(40, 300))
        assert block.pointer == (40, 300)

    def test_a_panel_with_no_map_at_all_still_paints_it(self):
        """A source can have work to report before it has anything to browse."""
        block = _Block()
        rendered = self._rendered(block, corner=None)

        assert block.painted_at is not None
        assert block.button in [button for _rect, button in rendered.targets.buttons]


class TestTheRowThePanelCarriesForItsClip:
    """Where in the video you are, and how loud it is, on the panel rather than
    along the lower edge of the picture.

    A row over the picture is a second panel on a screen that already carries
    one -- and on a wrapped video it is smeared round the nadir, which is why
    the headset put it on the console first.
    """

    @staticmethod
    def _rendered(row=None, **extra):
        return HudRenderer("portrait").render(
            _model(title="Unlocked", **extra), item_row=row)

    def test_a_funestra_that_hands_over_no_row_grows_none(self):
        row = RowHud(position_ms=1_000, duration_ms=60_000, volume=VolumeHud(volume=40))
        assert (self._rendered(row).bgra.shape[0]
                > self._rendered().bgra.shape[0])

    def test_it_sits_over_the_device_with_the_map_hanging_under_both(self, thumb):
        row = RowHud(position_ms=1_000, duration_ms=60_000, volume=VolumeHud(volume=40))
        rendered = self._rendered(
            row, corner=HudCell(path="c.mp4", thumb=thumb),
            seeds=(HudCell(path="s.mp4", thumb=thumb),), seed_count=2,
            osr2=Osr2State.ROBOT_HAND, drive=DriveHud(driven=DRIVEN_BY_ROBOT_HAND))
        placed = rendered.targets.row.rect

        assert placed is not None
        assert all(band.rect[1] >= placed[1] + placed[3] for band in rendered.targets.tracks)
        assert all(band.rect[1] + band.rect[3] < _map_top(rendered)
                   for band in rendered.targets.tracks)

    def test_a_press_on_it_is_placed_in_the_rows_own_coordinates(self):
        row = RowHud(position_ms=0, duration_ms=60_000, volume=VolumeHud(volume=40))
        rendered = self._rendered(row)
        row = rendered.targets.row
        _x, _y, width, height = row.rect

        assert row_part(width // 2, height - 2, row) == SCRUBBER


def _bands(rendered) -> dict[int, tuple[int, int]]:
    bands: dict[int, tuple[int, int]] = {}
    for (x, y, w, _h), _button in _declared(rendered):
        left, right = bands.get(y, (x, x + w))
        bands[y] = (min(left, x), max(right, x + w))
    return bands


def test_a_band_starts_at_the_left_pad_in_a_left_hand_corner(thumb):
    rendered = HudRenderer("portrait").render(
        _model(corner=HudCell(path="c.mp4", thumb=thumb)))

    assert {left for left, _right in _bands(rendered).values()} == {PAD}


def test_a_band_ends_at_the_right_pad_in_a_right_hand_corner(thumb):
    rendered = HudRenderer("portrait").render(
        _model(hud_corner=HudCorner.UPPER_RIGHT, corner=HudCell(path="c.mp4", thumb=thumb)))
    width = rendered.bgra.shape[1]

    assert {right for _left, right in _bands(rendered).values()} == {width - PAD}


def test_the_status_block_moves_to_the_corner_the_panel_sits_in(thumb):
    def rendered(corner):
        return HudRenderer("portrait").render(
            _model(hud_corner=corner, active=True, is_favorite=True, title="Locked",
                   corner=HudCell(path="c.mp4", thumb=thumb)), video="one.mp4")

    left = rendered(HudCorner.UPPER_LEFT)
    right = rendered(HudCorner.UPPER_RIGHT)

    assert left.targets.favorite is not None and right.targets.favorite is not None
    assert left.targets.favorite[0] < PAD + MINUS_ROOM + ACTIVE_DOT
    assert right.targets.favorite[0] > left.bgra.shape[1] // 2


def _map_corner_x(rendered) -> int:
    return rendered.targets.click[0][0][0]


def test_the_map_moves_to_the_corner_the_panel_sits_in(thumb):
    def rendered(corner):
        return HudRenderer("portrait").render(
            _model(hud_corner=corner, corner=HudCell(path="c.mp4", thumb=thumb),
                   seeds=(HudCell(path="s.mp4", thumb=thumb),), seed_count=2),
            video="a name far longer than the map is wide, by a good margin.mp4")

    left, right = rendered(HudCorner.UPPER_LEFT), rendered(HudCorner.UPPER_RIGHT)
    width = right.bgra.shape[1]

    assert _map_corner_x(left) == PAD + ROW_LABEL_GUTTER + ELLIPSIS_ROOM
    assert _map_corner_x(right) == (width - PAD - MAP_RIGHT_RESERVE - ELLIPSIS_ROOM
                                   - map_row_width("portrait"))


def test_the_speed_row_moves_to_the_corner_the_panel_sits_in(thumb):
    def rendered(corner):
        return HudRenderer("portrait").render(
            _model(hud_corner=corner, playback_speed=1.0,
                   corner=HudCell(path="c.mp4", thumb=thumb)),
            video="a name far longer than the map is wide, by a good margin.mp4")

    right = rendered(HudCorner.UPPER_RIGHT)
    width = right.bgra.shape[1]
    speed_y = min(y for (_x, y, _w, _h), button in right.targets.buttons
                  if button.command.endswith("_speed_up"))
    speeds = [(x, w) for (x, y, w, _h), _b in right.targets.buttons if y == speed_y]

    assert max(x + w for x, w in speeds) == width - PAD
    left = rendered(HudCorner.UPPER_LEFT)
    assert min(rect[0] for rect, _b in left.targets.buttons) == PAD


def test_the_device_block_moves_to_the_corner_the_panel_sits_in(thumb):
    def rendered(corner):
        return HudRenderer("portrait").render(
            _model(hud_corner=corner, osr2=Osr2State.ROBOT_HAND,
                   drive=DriveHud(driven=DRIVEN_BY_ROBOT_HAND),
                   corner=HudCell(path="c.mp4", thumb=thumb)),
            video="a name far longer than the map is wide, by a good margin.mp4")

    right = rendered(HudCorner.UPPER_RIGHT)
    left = rendered(HudCorner.UPPER_LEFT)
    width = right.bgra.shape[1]

    assert right.targets.tracks, "the readout drew no bands to place"
    moved = width - 2 * PAD - section_size()[0]
    assert moved > 0, "the panel is no wider than the readout, so nothing can move"
    assert (min(band.rect[0] for band in right.targets.tracks)
            - min(band.rect[0] for band in left.targets.tracks)) == moved

def test_the_max_intensity_moves_with_its_line_to_the_corner_the_panel_sits_in(thumb):
    park = Button("robot_hand_park", "P", "Parked")

    def rendered(corner):
        return HudRenderer("portrait").render(
            _model(hud_corner=corner, osr2=Osr2State.ROBOT_HAND, osr2_controls=(park,),
                   max_intensity=35, corner=HudCell(path="c.mp4", thumb=thumb)),
            video="a name far longer than the map is wide, by a good margin.mp4")

    def slider_past_park(panel) -> int:
        (max_intensity,) = [band for band in panel.targets.tracks if band.axis == MAX_INTENSITY]
        return max_intensity.rect[0] - _button_rect(panel, "robot_hand_park")[0]

    left, right = rendered(HudCorner.UPPER_LEFT), rendered(HudCorner.UPPER_RIGHT)

    assert (_button_rect(right, "robot_hand_park")[0]
            > _button_rect(left, "robot_hand_park")[0]), "the line did not move"
    assert slider_past_park(right) == slider_past_park(left)


def _button_rect(rendered, command: str) -> Rect:
    rects = [rect for rect, button in rendered.targets.buttons if button.command == command]
    assert len(rects) == 1, f"{command} drew {len(rects)} buttons"
    return rects[0]


def _drawn_columns(rendered, rows: range, *, leaving_out: Rect) -> list[int]:
    """The columns of *rows* something is drawn in, other than the slab, its
    border and the lines between its sections, and other than *leaving_out*."""
    rgba = rendered.bgra[:, :, [2, 1, 0, 3]].astype(int)
    width = rgba.shape[1]
    fill = rgba[rows.start + len(rows) // 2, 2]
    lx, ly, lw, lh = leaving_out
    lines = set(_dividers(rendered))
    return sorted({x for y in rows if y not in lines for x in range(2, width - 2)
                   if not (lx <= x < lx + lw and ly <= y < ly + lh)
                   and abs(rgba[y, x] - fill).sum() > 12})


@pytest.mark.parametrize("corner", [HudCorner.UPPER_LEFT, HudCorner.UPPER_RIGHT])
def test_the_title_moves_over_for_the_minus_in_the_panels_corner(thumb, corner):
    rendered = HudRenderer("portrait").render(
        _model(hud_corner=corner, corner=HudCell(path="c.mp4", thumb=thumb)), video="one.mp4")
    minus = _button_rect(rendered, "portrait_hud_minimize")
    first_band = min(rect[1] for rect, _button in _declared(rendered))

    drawn = _drawn_columns(rendered, range(PAD, first_band), leaving_out=minus)

    x, _y, w, _h = minus
    assert drawn, "the title drew nothing"
    assert ((max(drawn) < x - BUTTON_GAP) if corner.right
            else (min(drawn) >= x + w + BUTTON_GAP))


@pytest.mark.parametrize("corner", [HudCorner.LOWER_LEFT, HudCorner.LOWER_RIGHT])
@pytest.mark.parametrize("cells", [0, 1, MAP_CELLS])
def test_in_a_lower_corner_the_minus_sits_in_room_the_map_leaves_free(thumb, corner, cells):
    """The map is the panel's last block whether or not it has anything on it,
    and nothing it draws reaches the corner the minus takes."""
    model = _model(
        hud_corner=corner, current_action="alpha",
        corner=HudCell(path="c.mp4", thumb=thumb) if cells else None,
        seeds=tuple(HudCell(path=f"s{i}.mp4", thumb=thumb) for i in range(cells)),
        actions=tuple(HudCell(path=f"a{i}.mp4", thumb=thumb, label=label)
                      for i, label in zip(range(cells), ("alpha", "beta", "gamma"))))
    with_it = HudRenderer("portrait").render(model, video="one.mp4")
    without_it = HudRenderer("portrait").render(model, video="one.mp4", minus_on_the_panel=False)
    x, y, w, h = _button_rect(with_it, "portrait_hud_minimize")

    rgba = without_it.bgra[:, :, [2, 1, 0, 3]].astype(int)
    fill = rgba[rgba.shape[0] // 2, 2]
    spot = rgba[y:y + h, x:x + w]
    assert (np.abs(spot - fill).sum(axis=2) <= 12).all(), "something is drawn where the minus sits"


def test_the_pointer_on_a_minimized_panel_names_what_the_plus_does(thumb):
    """It is the one control on the panel and every other control names itself
    on hover, so the plus does too -- in the panel's own bitmap, since a HUD
    painted into a video has no tooltip to fall back on."""
    rendered = HudRenderer("portrait").render(
        _model(hud_minimized=True, corner=HudCell(path="c.mp4", thumb=thumb)),
        video="one.mp4", hover_tip=RESTORE_TOOLTIP, hover_pos=(CTRL_BTN // 2, CTRL_BTN // 2))
    height, width = rendered.bgra.shape[:2]
    (rect, button), = rendered.targets.buttons

    assert (width, height) > (CTRL_BTN, CTRL_BTN)
    assert rect == (0, 0, CTRL_BTN, CTRL_BTN)
    assert button.command == "portrait_hud_restore"


def test_a_minimized_panel_is_the_restore_button_and_nothing_else(thumb):
    rendered = HudRenderer("portrait").render(
        _model(hud_minimized=True, corner=HudCell(path="c.mp4", thumb=thumb)),
        video="one.mp4")
    height, width = rendered.bgra.shape[:2]

    assert (width, height) == (CTRL_BTN, CTRL_BTN)
    assert [button.command for _rect, button in rendered.targets.buttons] == [
        "portrait_hud_restore"]
    assert rendered.targets.click == []




def _span(rects) -> tuple[int, int]:
    rects = list(rects)
    return min(y for _x, y, _w, _h in rects), max(y + h for _x, y, _w, h in rects)


class TestEverySectionIsSetOffFromTheNextByALine:
    @staticmethod
    def _status(rendered) -> tuple[int, int]:
        return _span([_button_rect(rendered, "portrait_hud_minimize"),
                      rendered.targets.favorite])

    @staticmethod
    def _controls(rendered) -> tuple[int, int]:
        return _span(rect for rect, button in rendered.targets.buttons
                     if button.command.startswith("portrait_")
                     and button.command != "portrait_hud_minimize")

    @staticmethod
    def _device(rendered, drive: DriveHud) -> tuple[int, int]:
        top, _end = _span(rect for rect, button in rendered.targets.buttons
                             if button.command.startswith("robot_hand_toggle"))
        readout_top = rendered.targets.tracks[0].rect[1] - tracks(0, 0, drive)[0].rect[1]
        return top, readout_top + section_size()[1]

    @staticmethod
    def _map(rendered) -> tuple[int, int]:
        return _map_top(rendered), rendered.bgra.shape[0] - PAD

    def test_a_panel_carrying_every_section_has_a_line_between_each_and_the_next(self, thumb):
        block = _Block()
        drive = DriveHud(driven=DRIVEN_BY_ROBOT_HAND)
        rendered = HudRenderer("portrait").render(
            _model(title="Unlocked", corner=HudCell(path="c.mp4", thumb=thumb),
                   playback_speed=1.0, osr2=Osr2State.ROBOT_HAND, drive=drive, foot=block,
                   osr2_rows=((Button("robot_hand_toggle_learned", "hi", "Human inspired"),),)),
            video="example clip one", item_row=RowHud(duration_ms=60_000))
        painted = np.argwhere((_rgb(rendered.bgra) == np.array(_Block.MARK)).all(axis=-1))
        _x, row_y, _w, row_h = rendered.targets.row.rect
        sections = [self._status(rendered), self._controls(rendered), (row_y, row_y + row_h),
                    self._device(rendered, drive),
                    (painted[:, 0].min(), painted[:, 0].max() + 1), self._map(rendered)]

        lines = _dividers(rendered)

        assert len(lines) == len(sections) - 1
        for (_top, above_ends), line, (below_starts, _end) in zip(sections, lines, sections[1:]):
            assert above_ends <= line < below_starts

