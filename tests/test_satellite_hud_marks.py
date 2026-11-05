from __future__ import annotations

from PIL import Image, ImageDraw
from shared_ui.icon_geometry import icon_names
from shared_ui.palette import TEXT_PRIMARY

from funestra.satellite_hud import (
    EXPAND_ICON,
    FAVORITE_ICON,
    LOOP_ICON,
    WRONG_ACTION_ICON,
)
from funestra.satellite_hud_paint import HudRenderer


def _named() -> dict[str, str]:
    return {"loop": LOOP_ICON, "favorite": FAVORITE_ICON, "expand": EXPAND_ICON,
            "wrong action": WRONG_ACTION_ICON}


def test_the_loop_buttons_wear_the_circuit_rather_than_a_single_arc_which_means_undo():
    assert _named()["loop"] == "loop"


def test_the_favorite_mark_is_the_familys_star():
    assert _named()["favorite"] == "star"


def test_the_marks_the_hud_names_all_exist():
    missing = {key: name for key, name in _named().items() if name not in icon_names()}
    assert not missing, f"HUD faces naming marks shared_ui does not have: {missing}"


def test_the_expand_arrow_is_drawn_rather_than_typed_since_the_typed_one_was_a_hairline_beside_the_solid_transport_arrows():
    assert _named()["expand"] == "expand_horizontal"


def test_a_resting_button_draws_its_mark_full_strength():
    ink = HudRenderer("portrait")._button_square(
        ImageDraw.Draw(Image.new("RGBA", (18, 18))), (0, 0, 18, 18), on=False)
    assert ink[:3] == TEXT_PRIMARY
