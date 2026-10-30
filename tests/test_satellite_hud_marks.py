"""The satellite HUD wears the family's marks, not lookalikes of them.

The HUD is painted into the video frame with Pillow and there is no Qt in a
satellite process, so every mark here used to be whatever Segoe UI Symbol
carried -- a loop that was one arc where the family's is a circuit.  The
HUD's own marks come out of shared_ui's geometry now, through funestra's
HUD chrome, and these hold them to it; the faces a source declares for its
buttons are held to it where they are declared.
"""
from __future__ import annotations

from PIL import Image, ImageDraw
from shared_ui.icon_geometry import icon_names
from shared_ui.palette import TEXT_PRIMARY

from funestra.satellite_hud import (
    EXPAND_MARK,
    FAVORITE_MARK,
    LOOP_MARK,
    WRONG_ACTION_MARK,
)
from funestra.satellite_hud_paint import HudRenderer


def _named() -> dict[str, str]:
    return {"loop": LOOP_MARK, "favorite": FAVORITE_MARK, "expand": EXPAND_MARK,
            "wrong action": WRONG_ACTION_MARK}


def test_the_loop_buttons_wear_the_circuit_rather_than_a_single_arc():
    # A single arc says "back one step", which is undo's job. The family's loop
    # is two arrows chasing each other around a rounded rectangle.
    assert _named()["loop"] == "loop"


def test_the_favorite_mark_is_the_familys_star():
    # The same star Origenerator paints on a starred tile, so a bookmark learned
    # in one app reads in the other.
    assert _named()["favorite"] == "star"


def test_the_marks_the_hud_names_all_exist():
    missing = {key: name for key, name in _named().items() if name not in icon_names()}
    assert not missing, f"HUD faces naming marks shared_ui does not have: {missing}"


def test_the_expand_arrow_is_drawn_rather_than_typed():
    # Typed it was U+2194, a hairline beside the solid arrowheads of the
    # transport buttons it shares a HUD with.
    assert _named()["expand"] == "expand_horizontal"


def test_a_resting_button_draws_its_mark_full_strength():
    # The satellite HUDs read as dim and half-disabled beside the main
    # Funestra's console, which draws its own resting marks at full strength.
    # Both had muted the mark AND the square; only the square should be muted.
    ink = HudRenderer("portrait")._button_square(
        ImageDraw.Draw(Image.new("RGBA", (18, 18))), (0, 0, 18, 18), on=False)
    assert ink[:3] == TEXT_PRIMARY
