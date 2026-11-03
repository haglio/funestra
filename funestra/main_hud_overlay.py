from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from .dashboard import ask
from .host_controls import HostControls, HostControlsPress
from .hud_corners import HudPlace
from .hud_overlay import NO_DRIVE, DrawnOn, DriveFeed
from .hud_placement import HudEdge
from .hud_row import ItemRowDraw, RowHud, RowLayout, RowPress, track_on_screen
from .main_hud import MainHudModel, ModeHud, kino_shows, read_main_hud
from .main_hud_painter import MainHud, MainHudPainter, with_playback_speed
from .osr2_visualizer import DriveHud, read_drive


class MainHudFiles(NamedTuple):
    main_hud: Path
    command: Path | None


@dataclass(frozen=True)
class MainHudHost:
    top_block: Callable[[], ModeHud]
    row: RowPress
    host_controls: HostControls | None = None


class MainHudOverlay:
    def __init__(
        self,
        *,
        files: MainHudFiles,
        drawn_on: DrawnOn,
        host: MainHudHost,
        drive: DriveFeed = NO_DRIVE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._main_hud_file = Path(files.main_hud)
        self._drive_file = None if drive.file is None else Path(drive.file)
        self._command_file = files.command
        self._engine = drawn_on.engine
        self._drive_gate = drive.gate
        self._visualizer = drive.visualizer
        self._clock = clock
        self._top_block = host.top_block
        self.overlay_id = drawn_on.overlay_id
        self._painter = MainHudPainter(width=drawn_on.width,
                                       minus_on_the_hud=drawn_on.minus_on_the_hud)
        self._minus_on_the_hud = drawn_on.minus_on_the_hud
        self._main_hud = MainHudModel()
        self._drive: DriveHud | None = None
        self._shown = False
        self._origin = (0, 0)
        self._hud_height = 0
        self._item_row: RowHud | None = None
        self._row = host.row
        self._host_controls = HostControlsPress(host.host_controls)

    @property
    def main_hud_model(self) -> MainHudModel:
        return self._main_hud

    @property
    def edge(self) -> HudEdge:
        return self._main_hud.hud_edge

    @property
    def minimized(self) -> bool:
        return self._main_hud.hud_minimized

    @property
    def hud_place(self) -> HudPlace | None:
        return self._painter.hud_place

    def tick(self, *, playback_speed: float, viewport: tuple[int, int],
             item_row: ItemRowDraw | None = None, flash: str = "") -> None:
        row, heatmap = (None, None) if item_row is None else item_row
        self._main_hud = read_main_hud(self._main_hud_file) or self._main_hud
        if self._drive_file is not None:
            self._drive = read_drive(self._drive_file) or self._drive
        drive = self._drive_gate.visualizer(
            self._drive, device_drives_itself=self._main_hud.device_drives_itself,
            video_shows=kino_shows(self._main_hud.main_mode))
        if self._visualizer is not None and self._main_hud.has_osr2:
            self._visualizer.publish(drive, self._clock())
        self._item_row = row
        if self.minimized and not self._minus_on_the_hud:
            self.close()
            return
        main_hud_model = with_playback_speed(self._main_hud, playback_speed)
        if self._visualizer is not None:
            main_hud_model = replace(main_hud_model, has_osr2=False)
        bgra = self._painter.bgra(MainHud(
            modes=self._top_block(),
            main_hud_model=main_hud_model,
            drive=drive,
            flash=flash,
        ), item_row=row, heatmap=heatmap, host_controls=self._host_controls.drawing())
        self._origin = self._painter.place(viewport=viewport)
        self._hud_height = bgra.shape[0]
        self._engine.overlay(self.overlay_id, *self._origin, bgra)
        self._shown = True

    @property
    def row(self) -> RowLayout | None:
        return self._painter.row

    @property
    def row_track(self) -> tuple[int, int, int] | None:
        return track_on_screen(self._painter.row, origin=self._origin,
                               hud_height=self._hud_height)

    def covers(self, x: int, y: int) -> bool:
        return self._painter.covers(x, y)

    def press(self, x: int, y: int) -> bool:
        px, py = self._local(x, y)
        if self._host_controls.press(px, py, layout=self._painter.host_controls_layout):
            return True
        if self._row.press(px, py, layout=self._painter.row,
                           duration_ms=self._track_duration()):
            return True
        asked = self._painter.press_at(x, y)
        if asked:
            ask(self._command_file, asked)
            return True
        return self._painter.covers(x, y)

    @property
    def holding(self) -> bool:
        return self._host_controls.holding or self._row.holding or self._painter.holding

    def drag_to(self, x: int, y: int) -> str:
        px, py = self._local(x, y)
        if self._host_controls.drag_to(px, py, layout=self._painter.host_controls_layout):
            return ""
        if self._row.drag_to(px, py, layout=self._painter.row,
                             duration_ms=self._track_duration()):
            return ""
        dragged = self._painter.drag_to(x, y)
        if dragged:
            ask(self._command_file, dragged)
        return dragged

    def release(self) -> None:
        self._host_controls.release()
        self._row.release()
        self._painter.release()

    def _local(self, x: int, y: int) -> tuple[int, int]:
        return x - self._origin[0], y - self._origin[1]

    def _track_duration(self) -> float:
        return 0.0 if self._item_row is None else self._item_row.duration_ms

    def motion(self, x: int, y: int) -> None:
        self._painter.motion(x, y)

    def close(self) -> None:
        if self._shown:
            self._engine.remove_overlay(self.overlay_id)
            self._shown = False
