"""The HUD wears the family's marks, not lookalikes of them.

A HUD is painted into the video frame with Pillow and there is no Qt in a Funestra
process, so for a long time every mark here was whatever a symbol font happened
to carry, or something hand-drawn on the spot.  The bin on this console had
nothing to do with the bin on Origenerator's toolbar.  Both sides now render one
list of geometry out of shared_ui, and these hold the painter to drawing it; the
marks a source names for its buttons are held to it where they are named.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from shared_ui.palette import BG_BUTTON, RED
from shared_ui.spacing import BUTTON_ICON_INSET
from shared_ui.toggle_geometry import TRACK_HUD
from shared_ui.toggle_switch_pil import paste_toggle_switch

from funestra.hud import (
    SYMBOL_FONT,
    draw_button,
    draw_mark,
    load_font,
)
from funestra.hud_button import Button
from funestra.hud_marks import TOGGLE_SWITCH, shared_mark, shared_mark_name


def _drawn(hud, draw, button) -> None:
    """One declared control, drawn the way every HUD here draws one."""
    draw_button(hud, draw, (0, 0, 18, 18), button, hovered=False,
                glyph_font=load_font(11, SYMBOL_FONT), word_font=load_font(8))


class TestNamingTheMarks:
    def test_a_marker_round_trips_through_the_name_it_carries(self):
        assert shared_mark_name(shared_mark("trash")) == "trash"


class TestDrawingThem:
    def test_a_mark_lands_inside_the_button_it_was_given(self):
        # HUD buttons draw their own rounded border, so a mark filling the whole
        # rect runs into it. The inset is what keeps the two apart.
        hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
        draw_mark(hud, "trash", (0, 0, 18, 18), (255, 255, 255, 255))
        ink = np.asarray(hud)[:, :, 0] > 128

        assert ink.any(), "the mark did not draw"
        assert not ink[:BUTTON_ICON_INSET, :].any()
        assert not ink[-BUTTON_ICON_INSET:, :].any()

    def test_a_mark_is_laid_over_what_the_button_already_painted(self):
        # It composites onto the button's fill rather than stamping a
        # transparent square over it, which would cut a gap in the HUD.
        hud = Image.new("RGBA", (18, 18), (0, 90, 0, 255))
        draw_mark(hud, "reset", (0, 0, 18, 18), (255, 255, 255, 255))
        pixels = np.asarray(hud)

        assert (pixels[:, :, 3] == 255).all(), "the mark punched through the HUD"
        assert (pixels[:, :, 0] > 128).any(), "the mark did not draw"
        assert (pixels[:, :, 1] == 90).any(), "the fill is gone"

    def test_two_marks_are_two_different_drawings(self):
        # The point of naming them: a control that names the wrong one shows the
        # wrong one, and only a difference here would ever reveal that.
        def drawn(name: str) -> bytes:
            hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
            draw_mark(hud, name, (0, 0, 18, 18), (255, 255, 255, 255))
            return hud.tobytes()

        assert drawn("trash") != drawn("reset")
        assert drawn("reset") != drawn("wave")


class TestDangerIsRed:
    def test_a_dangerous_control_draws_its_mark_in_red(self):
        hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
        draw = ImageDraw.Draw(hud)
        _drawn(hud, draw, Button("x", shared_mark("trash"), "", danger=True))
        pixels = np.asarray(hud)

        reddest = pixels[:, :, 0].astype(int) - pixels[:, :, 1].astype(int)
        assert reddest.max() > 60, "the mark is not red"
        assert pixels[:, :, 0].max() >= RED[0] - 40


class TestButtonGrounds:
    def test_a_resting_control_sits_on_the_familys_button_ground(self):
        # It was an outline over the slab and nothing else, which read as a gap
        # in the HUD rather than as the raised button every window in this
        # family offers for the same act.
        hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
        _drawn(hud, ImageDraw.Draw(hud), Button("x", "🔒", ""))
        middle = np.asarray(hud)[9, 3]

        assert tuple(middle[:3]) == BG_BUTTON

    def test_a_control_that_is_on_still_comes_forward(self):
        # The ground is the resting state, not the lit one: a lit control fills
        # white, and would say nothing if resting looked the same.
        def ground(lit: bool):
            hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
            _drawn(hud, ImageDraw.Draw(hud), Button("x", "🔒", "", lit=lit))
            return tuple(int(v) for v in np.asarray(hud)[9, 3][:3])

        assert ground(False) == BG_BUTTON
        assert ground(True) != BG_BUTTON
        assert sum(ground(True)) > sum(BG_BUTTON)


class TestTheFamilysSwitch:
    def test_a_switch_is_the_familys_own_switch_on_while_lit(self):
        width, height = TRACK_HUD

        def cell(lit: bool) -> bytes:
            hud = Image.new("RGBA", (width, 18), (0, 0, 0, 255))
            draw_button(hud, ImageDraw.Draw(hud), (0, 0, width, 18),
                        Button("x", TOGGLE_SWITCH, "", width=width, lit=lit), hovered=False,
                        glyph_font=load_font(11, SYMBOL_FONT), word_font=load_font(8))
            return hud.tobytes()

        def familys(on: bool) -> bytes:
            hud = Image.new("RGBA", (width, 18), (0, 0, 0, 255))
            paste_toggle_switch(hud, (0, (18 - height) // 2), on=on)
            return hud.tobytes()

        assert cell(lit=True) == familys(on=True)
        assert cell(lit=False) == familys(on=False)

    def test_the_word_on_the_side_the_switch_is_at_is_the_bright_one(self):
        def brightest(lit: bool) -> int:
            hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
            _drawn(hud, ImageDraw.Draw(hud), Button("", "On", "", lit=lit))
            return int(np.asarray(hud)[:, :, :3].max())

        assert brightest(lit=True) > brightest(lit=False)

    def test_a_read_out_that_starts_with_a_letter_names_something_and_is_drawn_muted(self):
        def brightest(glyph: str) -> int:
            hud = Image.new("RGBA", (60, 18), (0, 0, 0, 255))
            draw_button(hud, ImageDraw.Draw(hud), (0, 0, 60, 18), Button("", glyph, ""),
                        hovered=False, glyph_font=load_font(11, SYMBOL_FONT),
                        word_font=load_font(8))
            return int(np.asarray(hud)[:, :, :3].max())

        assert brightest("OSR2 control") < brightest("4s")
