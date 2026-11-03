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
    draw_icon,
    load_font,
)
from funestra.hud_button import Button
from funestra.hud_icons import TOGGLE_SWITCH, shared_icon, shared_icon_name


def _drawn(hud, draw, button) -> None:
    draw_button(hud, draw, (0, 0, 18, 18), button, hovered=False,
                icon_font=load_font(11, SYMBOL_FONT), word_font=load_font(8))


class TestNamingTheMarks:
    def test_a_marker_round_trips_through_the_name_it_carries(self):
        assert shared_icon_name(shared_icon("trash")) == "trash"


class TestDrawingThem:
    def test_a_mark_lands_inside_the_button_it_was_given(self):
        hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
        draw_icon(hud, "trash", (0, 0, 18, 18), (255, 255, 255, 255))
        ink = np.asarray(hud)[:, :, 0] > 128

        assert ink.any(), "the mark did not draw"
        assert not ink[:BUTTON_ICON_INSET, :].any()
        assert not ink[-BUTTON_ICON_INSET:, :].any()

    def test_a_mark_is_laid_over_what_the_button_already_painted(self):
        hud = Image.new("RGBA", (18, 18), (0, 90, 0, 255))
        draw_icon(hud, "reset", (0, 0, 18, 18), (255, 255, 255, 255))
        pixels = np.asarray(hud)

        assert (pixels[:, :, 3] == 255).all(), "the mark punched through the HUD"
        assert (pixels[:, :, 0] > 128).any(), "the mark did not draw"
        assert (pixels[:, :, 1] == 90).any(), "the fill is gone"

    def test_two_marks_are_two_different_drawings(self):
        def drawn(name: str) -> bytes:
            hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
            draw_icon(hud, name, (0, 0, 18, 18), (255, 255, 255, 255))
            return hud.tobytes()

        assert drawn("trash") != drawn("reset")
        assert drawn("reset") != drawn("wave")


class TestDangerIsRed:
    def test_a_dangerous_control_draws_its_mark_in_red(self):
        hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
        draw = ImageDraw.Draw(hud)
        _drawn(hud, draw, Button("x", shared_icon("trash"), "", danger=True))
        pixels = np.asarray(hud)

        reddest = pixels[:, :, 0].astype(int) - pixels[:, :, 1].astype(int)
        assert reddest.max() > 60, "the mark is not red"
        assert pixels[:, :, 0].max() >= RED[0] - 40


class TestButtonGrounds:
    def test_a_resting_control_sits_on_the_familys_button_ground(self):
        hud = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
        _drawn(hud, ImageDraw.Draw(hud), Button("x", "🔒", ""))
        middle = np.asarray(hud)[9, 3]

        assert tuple(middle[:3]) == BG_BUTTON

    def test_a_control_that_is_on_still_comes_forward(self):
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
                        icon_font=load_font(11, SYMBOL_FONT), word_font=load_font(8))
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
        def brightest(icon: str) -> int:
            hud = Image.new("RGBA", (60, 18), (0, 0, 0, 255))
            draw_button(hud, ImageDraw.Draw(hud), (0, 0, 60, 18), Button("", icon, ""),
                        hovered=False, icon_font=load_font(11, SYMBOL_FONT),
                        word_font=load_font(8))
            return int(np.asarray(hud)[:, :, :3].max())

        assert brightest("OSR2 control") < brightest("4s")
