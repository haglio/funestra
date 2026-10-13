"""The HUD at its smallest: the plus, and the name it flashes beside it."""
from __future__ import annotations

import numpy as np
import pytest

from funestra.hud_minimize import BUTTON, FLASH_S, NameFlash, collapsed_button
from funestra.hud_panel import TINY_PT, load_font, text_width
from funestra.hud_placement import HudCorner


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class TestTheNameItFlashes:
    def test_a_video_that_has_just_started_is_named(self):
        flash = NameFlash(clock=lambda: 0.0)

        assert flash.showing("scene one") == "scene one"

    @pytest.mark.parametrize(("after", "shown"), [(FLASH_S - 0.1, "scene one"), (FLASH_S, "")])
    def test_the_name_is_up_for_a_few_seconds_and_then_gone(self, after, shown):
        clock = _Clock()
        flash = NameFlash(clock=clock)
        flash.showing("scene one")

        clock.now += after

        assert flash.showing("scene one") == shown

    def test_the_next_video_is_named_in_its_turn(self):
        clock = _Clock()
        flash = NameFlash(clock=clock)
        flash.showing("scene one")
        clock.now += FLASH_S + 5

        assert flash.showing("scene two") == "scene two"

    def test_nothing_on_screen_names_nothing(self):
        clock = _Clock()
        flash = NameFlash(clock=clock)
        flash.showing("scene one")

        assert flash.showing("") == ""


class TestTheNameBesideThePlus:
    def test_the_hud_widens_by_the_name_and_keeps_the_plus_height(self):
        bare, _buttons = collapsed_button("portrait")

        named, _buttons = collapsed_button("portrait", flash="scene one")

        assert named.size[0] >= bare.size[0] + text_width(load_font(TINY_PT), "scene one")
        assert named.size[1] == bare.size[1] == BUTTON

    @pytest.mark.parametrize("corner", list(HudCorner))
    def test_the_plus_keeps_its_corner_and_the_name_runs_toward_the_middle(self, corner):
        bare, _buttons = collapsed_button("portrait", corner)
        named, [((x, _y, w, _h), _plus)] = collapsed_button("portrait", corner,
                                                            flash="scene one")
        alpha = np.asarray(named)[:, :, 3]
        beside = np.nonzero(alpha.any(axis=0))[0]
        beside = beside[(beside < x) | (beside >= x + w)]

        assert x == (named.width - BUTTON if corner.right else 0)
        assert np.array_equal(np.asarray(named)[:, x:x + w], np.asarray(bare))
        assert beside.size
        assert (beside < x).all() if corner.right else (beside >= x + w).all()

    def test_pointed_at_the_plus_names_itself_in_the_names_place(self):
        on_the_plus = (BUTTON // 2, BUTTON // 2)
        tip, _buttons = collapsed_button("portrait", hover=on_the_plus)

        named, _buttons = collapsed_button("portrait", hover=on_the_plus, flash="scene one")

        assert np.array_equal(np.asarray(named), np.asarray(tip))
