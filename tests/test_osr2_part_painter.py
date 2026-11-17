from __future__ import annotations

import numpy as np
from main_hud_rows import main_hud_rows, motion_rows
from shared_ui.palette import BG_PRIMARY, BORDER_PANEL

from funestra.geometry import Rect
from funestra.hud_minimize import minimize_command
from funestra.hud_placement import HudCorner
from funestra.main_hud import MainHudModel, osr2_controls
from funestra.main_hud_painter import _PAD as PAD
from funestra.main_hud_painter import MainHud, hud_xy
from funestra.modes import MainMode, Osr2State
from funestra.osr2_part_painter import Osr2PartPainter
from funestra.osr2_visualizer import DriveHud


def _drive() -> DriveHud:
    return DriveHud(speed=50, amplitude=80, center=50, shape="sine",
                    waveform=tuple(0.5 + 0.4 * np.sin(i / 6) for i in range(80)))


def _hud(**model) -> MainHud:
    return MainHud(
        main_hud_model=MainHudModel(**{
            "main_mode": MainMode.GENAU, "osr2": Osr2State.ROBOT_HAND,
            "rows": main_hud_rows("genau"), "osr2_rows": motion_rows(),
            "osr2_controls": osr2_controls(broker_running=True), **model}),
        drive=_drive())


def _painted(**model) -> tuple[Osr2PartPainter, np.ndarray]:
    painter = Osr2PartPainter()
    return painter, painter.bgra(_hud(**model))


def _rgb(bgra: np.ndarray) -> np.ndarray:
    return bgra[:, :, [2, 1, 0]]


def _dividers(bgra: np.ndarray) -> list[int]:
    rgba = bgra[:, :, [2, 1, 0, 3]]
    return [y for y in range(rgba.shape[0]) if (rgba[y] == (*BORDER_PANEL, 255)).all()]


def _button_rect(painter: Osr2PartPainter, command: str) -> Rect:
    rects = [rect for rect, button in painter.buttons if button.command == command]
    assert len(rects) == 1, f"{command} drew {len(rects)} buttons"
    return rects[0]


def test_it_has_no_minus_since_nothing_under_it_could_be_uncovered():
    painter, _bgra = _painted()

    assert minimize_command("main") not in [button.command for _r, button in painter.buttons]


def test_its_first_line_is_the_row_that_aims_the_device():
    painter, bgra = _painted()

    assert _button_rect(painter, "robot_hand_learned_on")[1] == PAD
    assert _dividers(bgra) == []


def test_nothing_is_drawn_beside_the_row_that_aims_the_device():
    painter, bgra = _painted()
    x, y, w, h = _button_rect(painter, "robot_hand_learned_on")

    assert (_rgb(bgra)[y:y + h, x + w:-1] == BG_PRIMARY).all()


def test_it_keeps_no_room_for_a_minus_in_a_lower_corner():
    painter, _bgra = _painted(hud_corner=HudCorner.LOWER_LEFT)

    assert _button_rect(painter, "robot_hand_learned_on")[0] == PAD


def test_the_drive_visualizer_is_drawn_with_bars_to_drag():
    painter, _bgra = _painted()

    assert painter.tracks


def test_a_press_on_the_row_that_aims_the_device_asks_for_its_command():
    painter, _bgra = _painted()
    x, y, _w, _h = _button_rect(painter, "robot_hand_learned_on")
    left, top = hud_xy()

    assert painter.covers(x + left + 1, y + top + 1)
    assert painter.press_at(x + left + 1, y + top + 1) == "robot_hand_learned_on"
    assert not painter.holding


def test_it_is_placed_in_the_corner_its_part_names():
    painter = Osr2PartPainter()
    width, height = painter.rgba(_hud(hud_corner=HudCorner.LOWER_RIGHT))[1]

    left, top = painter.place(viewport=(1000, 800))

    assert (left + width, top + height) == (1000 - hud_xy()[0], 800 - hud_xy()[1])
