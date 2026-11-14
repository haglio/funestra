from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np
from PIL import Image
from shared_ui.palette import BG_PRIMARY
from shared_ui.spacing import MARGIN_STANDARD

from .hud import Hud
from .main_hud_painter import MainHud, Osr2PartDrawing, PressableHud, Slot, hud_fonts


class Osr2PartPainter(PressableHud):
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(clock=clock)
        self._fonts = hud_fonts()
        self._part = Osr2PartDrawing(self._fonts)

    def bgra(self, hud: MainHud, *, hover: tuple[int, int] | None = None) -> np.ndarray:
        return self._bgra_of(hud, hover)

    def rgba(self, hud: MainHud, *,
             hover: tuple[int, int] | None = None) -> tuple[bytes, tuple[int, int]]:
        return self._rgba_of(hud, hover)

    def _paint(self, hud: MainHud, hover: tuple[int, int] | None) -> Image.Image:
        block = self._part.block(hud)
        width, height = 2 * MARGIN_STANDARD + block.width, 2 * MARGIN_STANDARD + block.height
        drawn = Hud(width, height, ground=hud.ground or BG_PRIMARY)
        self.buttons, self.tracks = self._part.draw(
            drawn, block, MARGIN_STANDARD, Slot(hud.main_hud_model.hud_corner, 0), hover)
        self._tooltip(drawn, hover, self._fonts.tiny)
        return drawn.image
