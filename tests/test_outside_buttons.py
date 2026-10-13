from __future__ import annotations

import numpy as np
import pytest

from funestra.hud_corners import plus_bgra, plus_button, tooltip_size
from funestra.hud_minimize import BUTTON, MINIMIZE_TOOLTIP, RESTORE_TOOLTIP, name_slab
from funestra.hud_panel import to_bgra
from funestra.hud_placement import HudCorner, HudEdge
from funestra.outside_buttons import OutsideButtons

OPEN = OutsideButtons("portrait")
MINIMIZED = OutsideButtons("portrait", minimized=True)


class TestThePlusBesideASide:
    def test_asks_for_the_hud_along_that_side(self):
        assert OPEN.plus_beside(HudEdge.LEFT).command == "portrait_hud_restore_at|left"

    @pytest.mark.parametrize(("edge", "corner_plus_drawn_alike"), [
        (HudEdge.LEFT, HudCorner.UPPER_RIGHT),
        (HudEdge.RIGHT, HudCorner.UPPER_LEFT),
        (HudEdge.UPPER, HudCorner.LOWER_LEFT),
        (HudEdge.LOWER, HudCorner.UPPER_LEFT),
    ])
    def test_sits_nearest_the_picture_with_its_name_running_away_from_it(
            self, edge, corner_plus_drawn_alike):
        drawn_alike = plus_bgra(plus_button("portrait", edge, minimized=False),
                                corner_plus_drawn_alike)

        assert np.array_equal(OPEN.plus_beside(edge).bgra, drawn_alike)

    def test_beside_a_minimized_hud_it_offers_to_show_the_hud_there(self):
        shows_it_there = plus_bgra(plus_button("portrait", HudEdge.LEFT, minimized=True),
                                   HudCorner.UPPER_RIGHT)

        assert np.array_equal(MINIMIZED.plus_beside(HudEdge.LEFT).bgra, shows_it_there)


class TestTheButtonBetweenThePictureAndTheHud:
    def test_is_one_button_square(self):
        assert OPEN.toggle(pointed=False).bgra.shape == (BUTTON, BUTTON, 4)

    def test_pointed_at_it_lights_up(self):
        assert not np.array_equal(OPEN.toggle(pointed=True).bgra, OPEN.toggle(pointed=False).bgra)

    @pytest.mark.parametrize(("outside", "name"), [
        (OPEN, MINIMIZE_TOOLTIP),
        (MINIMIZED, RESTORE_TOOLTIP),
    ])
    def test_its_name_is_painted_to_hang_beside_it(self, outside, name):
        width, height = tooltip_size(name)

        assert outside.toggle_tip().shape == (height, width, 4)


class TestTheNameOfWhatHasJustStarted:
    def test_minimized_it_is_painted_as_the_hud_paints_it_beside_its_plus(self):
        flashing = OutsideButtons("portrait", minimized=True, flash="scene one")

        assert np.array_equal(flashing.name_flash(), to_bgra(name_slab("scene one")))

    def test_an_open_hud_names_the_video_itself(self):
        assert OutsideButtons("portrait", flash="scene one").name_flash() is None

    def test_with_nothing_flashing_there_is_none(self):
        assert MINIMIZED.name_flash() is None
