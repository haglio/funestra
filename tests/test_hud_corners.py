from __future__ import annotations

import pytest
from funestra_fakes import FakeEngine
from shared_ui.spacing import BUTTON_GAP

from funestra.hud_corners import (
    CORNER_PLUS_OVERLAY_ID,
    HudCorners,
    HudPlace,
    plus_bgra,
    plus_button,
    tooltip_size,
)
from funestra.hud_minimize import BUTTON
from funestra.hud_placement import HudCorner

WINDOW = (1200, 800)
LOWER_RIGHT = (WINDOW[0] - 3, WINDOW[1] - 3)


class _Hud:
    def __init__(self, *, corner: HudCorner = HudCorner.UPPER_LEFT,
                 covering: tuple[int, int, int, int] = (0, 0, 0, 0)) -> None:
        self.hud_place = HudPlace("portrait", corner, 12)
        self._covering = covering

    def covers(self, x: int, y: int) -> bool:
        left, top, width, height = self._covering
        return left <= x < left + width and top <= y < top + height


def _corners(hud: _Hud | None = None,
             asked: list[str] | None = None) -> tuple[HudCorners, FakeEngine]:
    engine = FakeEngine()
    post = (asked if asked is not None else []).append
    return HudCorners(hud or _Hud(), engine, post=post), engine


def _pointed_at(corners: HudCorners, point: tuple[int, int]) -> None:
    corners.motion(*point)
    corners.paint(window=WINDOW)


class TestThePlus:
    def test_the_pointer_over_the_hud_puts_no_plus_under_it(self):
        corners, engine = _corners(_Hud(covering=(0, 0, *WINDOW)))

        _pointed_at(corners, LOWER_RIGHT)

        assert CORNER_PLUS_OVERLAY_ID not in engine.overlays

    def test_a_pointer_off_the_window_puts_no_plus_anywhere(self):
        corners, engine = _corners(_Hud(corner=HudCorner.LOWER_RIGHT))

        _pointed_at(corners, (-1, -1))

        assert CORNER_PLUS_OVERLAY_ID not in engine.overlays


    def test_a_plus_there_was_no_memory_to_put_up_goes_up_on_the_next_frame(self):
        corners, engine = _corners(_Hud(corner=HudCorner.UPPER_LEFT))
        corners.motion(*LOWER_RIGHT)
        engine.overlay = _no_memory_to_put_it_up
        with pytest.raises(MemoryError):
            corners.paint(window=WINDOW)

        del engine.overlay
        corners.paint(window=WINDOW)

        assert CORNER_PLUS_OVERLAY_ID in engine.overlays


def _no_memory_to_put_it_up(*_args) -> None:
    raise MemoryError


class TestAPress:
    def test_in_a_corner_the_hud_is_not_in_asks_for_the_hud_there(self):
        asked: list[str] = []
        corners, _engine = _corners(asked=asked)
        corners.paint(window=WINDOW)

        taken = corners.press(*LOWER_RIGHT)

        assert (taken, asked) == (True, ["portrait_hud_restore_at|lower_right"])

    def test_in_the_huds_own_corner_is_left_to_the_item(self):
        asked: list[str] = []
        corners, _engine = _corners(_Hud(corner=HudCorner.LOWER_RIGHT), asked)
        corners.paint(window=WINDOW)

        assert (corners.press(*LOWER_RIGHT), asked) == (False, [])

    def test_over_the_hud_is_left_to_the_hud(self):
        asked: list[str] = []
        corners, _engine = _corners(_Hud(covering=(0, 0, *WINDOW)), asked)
        corners.paint(window=WINDOW)

        assert (corners.press(*LOWER_RIGHT), asked) == (False, [])


class TestWhatThePlusSays:
    def test_beside_an_open_hud_it_moves_the_hud_there(self):
        button = plus_button("portrait", HudCorner.LOWER_RIGHT, minimized=False)

        assert button.tooltip == "Move this HUD here"

    def test_beside_a_minimized_hud_it_shows_the_hud_there(self):
        button = plus_button("portrait", HudCorner.LOWER_RIGHT, minimized=True)

        assert button.tooltip == "Show this HUD here"

    def test_a_press_on_it_asks_for_the_hud_at_the_place_it_names(self):
        assert plus_button("landscape", "left", minimized=False).command == (
            "landscape_hud_restore_at|left")


def test_the_plus_leaves_its_name_the_room_tooltip_size_gives_it():
    button = plus_button("portrait", HudCorner.LOWER_RIGHT, minimized=False)
    width, height = tooltip_size(button.tooltip)

    drawn = plus_bgra(button, HudCorner.LOWER_RIGHT)

    assert drawn.shape[:2] == (max(BUTTON, height), BUTTON + BUTTON_GAP + width)


class TestWhereAPlaceSits:
    def test_open_its_hud_sits_at_the_margin(self):
        place = HudPlace("portrait", HudCorner.LOWER_RIGHT, 12, inset=(10, 13))

        assert place.origin(hud=(200, 100), window=WINDOW) == (
            WINDOW[0] - 12 - 200, WINDOW[1] - 12 - 100)

    def test_minimized_its_plus_sits_in_from_the_margin_on_the_minus_spot(self):
        place = HudPlace("portrait", HudCorner.LOWER_RIGHT, 12, minimized=True, inset=(10, 13))

        assert place.origin(hud=(24, 24), window=WINDOW) == (
            WINDOW[0] - 12 - 10 - 24, WINDOW[1] - 12 - 13 - 24)
