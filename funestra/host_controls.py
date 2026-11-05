from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from PIL import Image, ImageDraw
from shared_ui.dropdown_pil import ARROW_PX, paint_field, paint_list
from shared_ui.palette import TEXT_MUTED, TEXT_PRIMARY
from shared_ui.spacing import BUTTON_GAP, BUTTON_GROUP_GAP, BUTTON_PAD_H_TIGHT, BUTTON_SIZE_HUD
from shared_ui.type_scale import SIZE_TINY

from .geometry import Rect, contains
from .hud import draw_track, load_font

_GROUP_GAP = BUTTON_GROUP_GAP
_LEAST_BAR_W = 60


@dataclass(frozen=True)
class BarHud:
    label: str
    value: float
    low: float
    high: float
    unit: str = ""

    @property
    def share(self) -> float:
        return (self.value - self.low) / (self.high - self.low)

    def at(self, share: float) -> float:
        return self.low + min(1.0, max(0.0, share)) * (self.high - self.low)

    @property
    def reading(self) -> str:
        return f"{self.value:.0f}{self.unit}"

    @property
    def widest_reading(self) -> str:
        digits = max(len(f"{end:.0f}") for end in (self.low, self.high))
        return "0" * digits + self.unit


@dataclass(frozen=True)
class HostControlsHud:
    chosen: str
    choices: tuple[str, ...]
    bar: BarHud | None = None
    list_open: bool = False


class HostControls(Protocol):
    def hud(self) -> HostControlsHud | None: ...

    def pick(self, index: int) -> None: ...

    def set_bar(self, value: float) -> None: ...


@dataclass(frozen=True)
class HostControlsLayout:
    field: Rect
    bar: Rect | None
    rows: tuple[Rect, ...]


class HostControlsSection:
    height = BUTTON_SIZE_HUD

    def __init__(self) -> None:
        self._font = load_font(SIZE_TINY)

    def _field_width(self, hud: HostControlsHud) -> int:
        widest = max(self._font.getlength(name) for name in (hud.chosen, *hud.choices))
        return round(BUTTON_PAD_H_TIGHT + widest + BUTTON_GAP + ARROW_PX + BUTTON_GAP)

    def _words_width(self, bar: BarHud) -> int:
        return round(self._font.getlength(bar.label) + BUTTON_GAP
                     + self._font.getlength(bar.widest_reading))

    def least_width(self, hud: HostControlsHud) -> int:
        if hud.bar is None:
            return self._field_width(hud)
        return (self._field_width(hud) + _GROUP_GAP + self._words_width(hud.bar) + BUTTON_GAP
                + _LEAST_BAR_W)

    def layout(self, hud: HostControlsHud, rect: Rect) -> HostControlsLayout:
        x, y, width, height = rect
        field = (x, y, self._field_width(hud), height)
        rows = tuple((x, y - (len(hud.choices) - index) * height, field[2], height)
                     for index in range(len(hud.choices)))
        if hud.bar is None:
            return HostControlsLayout(field, None, rows)
        bar_x = x + field[2] + _GROUP_GAP + self._words_width(hud.bar) + BUTTON_GAP
        return HostControlsLayout(field, (bar_x, y, x + width - bar_x, height), rows)

    def draw(self, image: Image.Image, rect: Rect, hud: HostControlsHud) -> HostControlsLayout:
        placed = self.layout(hud, rect)
        pen = ImageDraw.Draw(image)
        paint_field(image, placed.field, hud.chosen, self._font)
        if hud.bar is not None:
            self._draw_bar(pen, placed, hud.bar)
        if hud.list_open:
            paint_list(image, [(row, name, name == hud.chosen)
                               for row, name in zip(placed.rows, hud.choices, strict=True)],
                       self._font)
        return placed

    def _draw_bar(self, pen: ImageDraw.ImageDraw, placed: HostControlsLayout,
                  bar: BarHud) -> None:
        field_x, _y, field_width, _height = placed.field
        x, y, width, height = placed.bar
        middle = y + height / 2
        pen.text((field_x + field_width + _GROUP_GAP, middle), bar.label, font=self._font,
                 anchor="lm", fill=(*TEXT_MUTED, 255))
        pen.text((x - BUTTON_GAP, middle), bar.reading, font=self._font, anchor="rm",
                 fill=(*TEXT_PRIMARY, 255))
        reach = round(bar.share * width)
        draw_track(pen, x, x + width - 1, y + height // 2,
                   filled_to=x + reach - 1 if reach > 0 else None)


class HostControlsPress:
    def __init__(self, host: HostControls | None) -> None:
        self._host = host
        self._shown: HostControlsHud | None = None
        self.holding = False

    def drawing(self) -> HostControlsHud | None:
        hud = None if self._host is None else self._host.hud()
        if hud is None:
            self._shown, self.holding = None, False
            return None
        list_open = self._shown is not None and self._shown.list_open
        self._shown = replace(hud, list_open=list_open)
        if hud.bar is None:
            self.holding = False
        return self._shown

    def press(self, px: int, py: int, *, layout: HostControlsLayout | None) -> bool:
        shown = self._shown
        if shown is None or layout is None:
            return False
        if shown.list_open:
            for index, row in enumerate(layout.rows):
                if contains(row, px, py):
                    self._host.pick(index)
            self._shown = replace(shown, list_open=False)
            return True
        if contains(layout.field, px, py):
            self._shown = replace(shown, list_open=True)
            return True
        if shown.bar is not None and layout.bar is not None and contains(layout.bar, px, py):
            self.holding = True
            return self.drag_to(px, py, layout=layout)
        return False

    def drag_to(self, px: int, _py: int, *, layout: HostControlsLayout | None) -> bool:
        if not self.holding or layout is None or layout.bar is None:
            return False
        x, _y, width, _height = layout.bar
        self._host.set_bar(self._shown.bar.at((px - x) / width))
        return True

    def release(self) -> None:
        self.holding = False
