from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from .dashboard import ask
from .hud_button import Button
from .hud_corners import HudPlace
from .hud_placement import HudCorner, HudEdge, PointerReading
from .hud_row import ItemRowDraw, RowHud, RowLayout, RowPress, track_on_screen
from .modes import Osr2State
from .osr2_visualizer import DriveHud, DrivePublisher, read_drive
from .satellite_hud import (
    MARGIN,
    MINUS_INSET,
    HudClicks,
    HudModel,
    HudTargets,
    PaintedFoot,
    button_tooltip,
    button_under,
    hit_test_targets,
    parse_hud,
)
from .satellite_hud_paint import HudRenderer

HUD_OVERLAY_ID = 10

FOOT_PRESS = "foot_press"
FOOT_DRAG = "foot_drag"
FOOT_RELEASE = "foot_release"
FOOT_WHEEL = "foot_wheel"

_EMPTY_TARGETS = HudTargets(click=[], loop=[], filter=[], expand=None)


@dataclass(frozen=True)
class DrawnOn:
    engine: object
    overlay_id: int = HUD_OVERLAY_ID
    over_the_video: bool = True
    minus_on_the_hud: bool = True
    width: int | None = None


@dataclass(frozen=True)
class DriveFeed:
    file: Path | None = None
    gate: object = None
    visualizer: DrivePublisher | None = None


NO_DRIVE = DriveFeed()


class _Hover(NamedTuple):
    loop: str
    tip: str
    button: Button | None
    at: tuple[int, int] | None

    def is_on_the_same_control_as(self, other: _Hover) -> bool:
        return (self.loop, self.tip, self.button) == (other.loop, other.tip, other.button)


_ON_NO_CONTROL = _Hover("", "", None, None)


class PublishedHud:
    def __init__(self, hud_file: Path, command_file: Path) -> None:
        self._hud_file = Path(hud_file)
        self._command_file = Path(command_file)
        self._published = ""

    def next(self, shown: HudModel | None) -> tuple[HudModel | None, bool]:
        try:
            text = self._hud_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        except OSError:
            return shown, False
        if text == self._published:
            return shown, False
        self._published = text
        return (parse_hud(text) if text else None), True

    def post(self, command: str) -> None:
        ask(self._command_file, command)


class WindowsOwnHud:
    def __init__(self, hud: Callable[[], HudModel | None],
                 post: Callable[[str], None]) -> None:
        self._hud = hud
        self.post = post

    def next(self, shown: HudModel | None) -> tuple[HudModel | None, bool]:
        model = self._hud()
        return model, model != shown


class HudOverlay:
    def __init__(
        self,
        *,
        source: PublishedHud | WindowsOwnHud,
        drawn_on: DrawnOn,
        drive: DriveFeed = NO_DRIVE,
        row: RowPress | None = None,
        clock=time.monotonic,
    ) -> None:
        self._source = source
        self._drive_file = None if drive.file is None else Path(drive.file)
        self._drive_gate = drive.gate
        self._visualizer = drive.visualizer
        self._published_drive: DriveHud | None = None
        self._drive: DriveHud | None = None
        self._engine = drawn_on.engine
        self.overlay_id = drawn_on.overlay_id
        self._clock = clock
        self._over_the_video = drawn_on.over_the_video
        self._minus_on_the_hud = drawn_on.minus_on_the_hud
        self._renderer: HudRenderer | None = None
        self._clicks: HudClicks | None = None
        self._model: HudModel | None = None
        self._video = ""
        self._flash = ""
        self._playback_speed: float | None = None
        self._item_row: RowHud | None = None
        self._heatmap = None
        self._row = RowPress() if row is None else row
        self._hover: PointerReading[_Hover] = PointerReading(_ON_NO_CONTROL)
        self._pointer_at = (0, 0)
        self._foot_held = False
        self._shown = False
        self._draw_owed = False
        self._viewport: tuple[int, int] | None = None
        self._origin = (MARGIN, MARGIN)
        self._hud_size: tuple[int, int] | None = None
        self.targets: HudTargets = _EMPTY_TARGETS

    @property
    def hud_place(self) -> HudPlace | None:
        if self._model is None:
            return None
        return HudPlace(self._model.funestra, self._model.hud_corner, MARGIN,
                        minimized=self._model.hud_minimized, inset=MINUS_INSET)

    @property
    def edge(self) -> HudEdge:
        return self._model.hud_edge if self._model is not None else HudEdge.LOWER

    @property
    def minimized(self) -> bool:
        return self._model is not None and self._model.hud_minimized

    @property
    def active_loop(self) -> str:
        return self._clicks.active_loop if self._clicks is not None else ""

    def tick(self, *, video: str = "", playback_speed: float | None = None,
             viewport: tuple[int, int] | None = None,
             item_row: ItemRowDraw | None = None, flash: str = "") -> None:
        row, heatmap = (None, None) if item_row is None else item_row
        redraw = (video != self._video or playback_speed != self._playback_speed
                  or viewport != self._viewport or flash != self._flash
                  or row != self._item_row or heatmap is not self._heatmap)
        self._video = video
        self._playback_speed = playback_speed
        self._viewport = viewport
        self._flash = flash
        self._item_row, self._heatmap = row, heatmap
        model, changed = self._source.next(self._model)
        if changed:
            if model is not None:
                if self._renderer is None:
                    self._renderer = HudRenderer(model.funestra)
                    self._clicks = HudClicks(model.funestra)
                self._clicks.active_loop = model.active_loop
                self._clicks.active_filter = model.filter_query
            self._model = model
            redraw = True
        drive = self._motion()
        if drive is not None and self._visualizer is not None:
            self._visualizer.publish(drive, self._clock())
        elif drive != self._drive:
            self._drive = drive
            redraw = True
        if redraw or self._draw_owed:
            self._draw()
        if self._clicks is not None:
            command = self._clicks.due(now=self._clock())
            if command:
                self._post(command)

    def press(self, x: int, y: int) -> bool:
        if self._clicks is None or not self.covers(x, y):
            return False
        self._pointer_at = self._local(x, y)
        if self._row.press(*self._pointer_at, layout=self.targets.row,
                           duration_ms=self._track_duration()):
            return True
        if self._foot_covers(*self._pointer_at):
            self._foot_held = True
            self._post_on_the_foot(FOOT_PRESS)
            return True
        command = self._clicks.press(self.targets, *self._pointer_at, now=self._clock())
        if command:
            self._post(command)
            self._draw()
        return True

    def wheel(self, x: int, y: int, steps: int) -> bool:
        if self._clicks is None or not self.covers(x, y):
            return False
        self._pointer_at = self._local(x, y)
        if self._foot_covers(*self._pointer_at):
            self._post_on_the_foot(FOOT_WHEEL, steps)
        return True

    def _track_duration(self) -> float:
        return 0.0 if self._item_row is None else self._item_row.duration_ms

    @property
    def row(self) -> RowLayout | None:
        return self.targets.row

    @property
    def row_track(self) -> tuple[int, int, int] | None:
        return track_on_screen(
            self.targets.row, origin=self._origin,
            hud_height=0 if self._hud_size is None else self._hud_size[1])

    @property
    def holding(self) -> bool:
        return self._row.holding or self._foot_held or (
            self._clicks is not None and self._clicks.holding)

    def drag_to(self, x: int, y: int) -> str:
        self._pointer_at = self._local(x, y)
        if self._row.drag_to(*self._pointer_at, layout=self.targets.row,
                             duration_ms=self._track_duration()):
            return ""
        if self._foot_held:
            self._post_on_the_foot(FOOT_DRAG)
            return ""
        command = self._clicks.drag_to(*self._pointer_at) if self._clicks is not None else ""
        if command:
            self._post(command)
        return command

    def release(self) -> None:
        self._row.release()
        if self._foot_held:
            self._foot_held = False
            self._post_on_the_foot(FOOT_RELEASE)
        if self._clicks is not None:
            self._clicks.release()

    def motion(self, x: int, y: int) -> None:
        px, py = self._local(x, y)
        self._pointer_at = (px, py)
        loop = hit_test_targets(self.targets.loop, px, py)
        tip = button_tooltip(self.targets, px, py)
        button = button_under(self.targets, px, py)
        hover = _Hover(loop, tip, button, (px, py) if tip or button else None)
        if hover.is_on_the_same_control_as(self._hover.reading):
            return
        self._hover.take(hover)
        self._draw()

    def close(self) -> None:
        self._hud_size = None
        if self._shown:
            self._engine.remove_overlay(self.overlay_id)
            self._shown = False

    def covers(self, x: int, y: int) -> bool:
        if self._hud_size is None:
            return False
        left, top = self._origin
        width, height = self._hud_size
        return left <= x < left + width and top <= y < top + height

    def _foot_covers(self, px: int, py: int) -> bool:
        foot = self.targets.foot
        if foot is None:
            return False
        x, y, width, height = foot
        return x <= px < x + width and y <= py < y + height

    def _post_on_the_foot(self, verb: str, *values: int) -> None:
        x, y, _width, _height = self.targets.foot
        px, py = self._pointer_at
        if isinstance(self._model.foot, PaintedFoot):
            verb = f"{self._model.funestra}_{verb}"
        self._post("|".join(str(part) for part in (verb, *values, px - x, py - y)))

    def _local(self, x: int, y: int) -> tuple[int, int]:
        left, top = self._origin
        return x - left, y - top

    def _place(self, corner: HudCorner, size: tuple[int, int]) -> tuple[int, int]:
        if self._viewport is None:
            return MARGIN, MARGIN
        return replace(self.hud_place, corner=corner).origin(hud=size, viewport=self._viewport)

    def _motion(self) -> DriveHud | None:
        if self._drive_file is None or self._model is None or not self._model.osr2:
            return None
        self._published_drive = read_drive(self._drive_file) or self._published_drive
        if self._drive_gate is None:
            return self._published_drive
        return self._drive_gate.visualizer(
            self._published_drive, device_drives_itself=self._model.osr2 == Osr2State.AUTO)

    def _draw(self) -> None:
        hover = self._hover.on(self._model)
        if (self._model is None or self._renderer is None
                or (self._model.hud_minimized and not self._minus_on_the_hud)):
            self.targets = _EMPTY_TARGETS
            self.close()
            return
        corner = self._model.hud_corner if self._over_the_video else HudCorner.UPPER_LEFT
        drive = self._model.drive if self._drive_file is None else self._drive
        model = replace(self._model, playback_speed=self._playback_speed, drive=drive,
                        drive_composed=self._drive_gate is not None, hud_corner=corner)
        if self._visualizer is not None:
            model = replace(model, osr2="", drive=None)
        self._draw_owed = True
        rendered = self._renderer.render(
            model,
            video=self._video, hover_loop=hover.loop, hover_tip=hover.tip, hover_pos=hover.at,
            may_grow_on_hover=self._over_the_video,
            minus_on_the_hud=self._minus_on_the_hud,
            item_row=self._item_row, heatmap=self._heatmap, flash=self._flash,
        )
        height, width = rendered.bgra.shape[:2]
        origin = self._place(corner, (width, height))
        self._engine.overlay(self.overlay_id, *origin, rendered.bgra)
        self._draw_owed = False
        self.targets = rendered.targets
        self._hud_size = (width, height)
        self._origin = origin
        self._shown = True

    def _post(self, command: str) -> None:
        self._source.post(command)
