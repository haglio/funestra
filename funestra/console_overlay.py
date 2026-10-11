"""The console kept on the picture: the panel the room publishes for the main slot,
read every frame, composited, pressed.

The room's two files -- the console, and the motion whoever drives the OSR2
publishes -- are replaced while this polls them, so a torn read keeps what was
there: blanking either for a frame is a visible flicker on a panel redrawn at
60fps.  The motion is read through the gate before the panel believes it, or
the pill and the drawn line describe the frame before this one.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .console import ConsoleModel, ModeHud, read_console
from .console_hud import ConsoleHud, ConsolePainter, with_playback_speed
from .dashboard import ask
from .drive_readout import DriveHud, read_drive
from .geometry import Rect
from .hud_corners import HudPlace
from .hud_overlay import HUD_OVERLAY_ID
from .hud_placement import HudEdge, PointerReading
from .hud_row import RowHud, RowLayout, RowPress, track_on_screen

__all__ = []


class HostBlock(Protocol):
    holding: bool

    def drawing(self): ...

    def press(self, px: int, py: int, *, rect: Rect | None) -> bool: ...

    def drag_to(self, px: int, py: int, *, rect: Rect | None) -> bool: ...

    def release(self) -> None: ...


class _NoBlock:
    holding = False

    def drawing(self) -> None:
        return None

    def press(self, _px: int, _py: int, *, rect: Rect | None) -> bool:
        return False

    def drag_to(self, _px: int, _py: int, *, rect: Rect | None) -> bool:
        return False

    def release(self) -> None:
        pass


class ConsoleOverlay:
    def __init__(
        self,
        *,
        console_file: Path,
        drive_file: Path | None,
        command_file: Path | None,
        engine,
        drive_gate,
        top_block: Callable[[], ModeHud],
        overlay_id: int = HUD_OVERLAY_ID,
        width: int | None = None,
        minus_on_the_panel: bool = True,
        seek=None,
        seek_loop=None,
        set_volume=None,
        toggle_mute=None,
        host_block: HostBlock | None = None,
    ) -> None:
        self._console_file = Path(console_file)
        self._drive_file = None if drive_file is None else Path(drive_file)
        self._command_file = command_file
        self._engine = engine
        self._drive_gate = drive_gate
        self._top_block = top_block
        self.overlay_id = overlay_id
        self._painter = ConsolePainter(width=width, minus_on_the_panel=minus_on_the_panel)
        self._minus_on_the_panel = minus_on_the_panel
        self._console = ConsoleModel()
        self._drive: DriveHud | None = None
        self._hover: PointerReading[tuple[int, int] | None] = PointerReading(None)
        self._shown = False
        self._origin = (0, 0)
        self._panel_height = 0
        self._clip_row: RowHud | None = None
        # The console draws the clip's row, so it places a press on it too.
        self._row = RowPress(seek=seek, seek_loop=seek_loop, set_volume=set_volume,
                             toggle_mute=toggle_mute)
        self._host_block = host_block or _NoBlock()

    @property
    def console(self) -> ConsoleModel:
        return self._console

    @property
    def edge(self) -> HudEdge:
        return self._console.hud_edge

    @property
    def minimized(self) -> bool:
        return self._console.hud_minimized

    @property
    def hud_place(self) -> HudPlace | None:
        return self._painter.hud_place

    def tick(self, *, playback_speed: float, window: tuple[int, int],
             clip_row: RowHud | None = None, heatmap=None) -> None:
        self._console = read_console(self._console_file) or self._console
        if self._drive_file is not None:
            self._drive = read_drive(self._drive_file) or self._drive
        drive = self._drive_gate.readout(
            self._drive, device_drives_itself=self._console.device_drives_itself)
        self._clip_row = clip_row
        if self.minimized and not self._minus_on_the_panel:
            self.close()
            return
        bgra = self._painter.bgra(ConsoleHud(
            modes=self._top_block(),
            console=with_playback_speed(self._console, playback_speed),
            drive=drive,
        ), hover=self._hover.on(self._console), clip_row=clip_row, heatmap=heatmap,
           host_block=self._host_block.drawing())
        self._origin = self._painter.place(window=window)
        self._panel_height = bgra.shape[0]
        self._engine.overlay(self.overlay_id, *self._origin, bgra)
        self._shown = True

    @property
    def row(self) -> RowLayout | None:
        """Where the row landed in this panel and how it is laid out,
        for a host measuring the track it is to fill."""
        return self._painter.row

    @property
    def row_track(self) -> tuple[int, int, int] | None:
        """The row's track in the window's coordinates, for a host hanging the
        loop's frames under it."""
        return track_on_screen(self._painter.row, origin=self._origin,
                               panel_height=self._panel_height)

    def covers(self, x: int, y: int) -> bool:
        return self._painter.covers(x, y)

    def press(self, x: int, y: int) -> bool:
        px, py = self._local(x, y)
        if self._host_block.press(px, py, rect=self._painter.host_block_rect):
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
        return self._host_block.holding or self._row.holding or self._painter.holding

    def drag_to(self, x: int, y: int) -> str:
        px, py = self._local(x, y)
        if self._host_block.drag_to(px, py, rect=self._painter.host_block_rect):
            return ""
        if self._row.drag_to(px, py, layout=self._painter.row,
                             duration_ms=self._track_duration()):
            return ""
        dragged = self._painter.drag_to(x, y)
        if dragged:
            ask(self._command_file, dragged)
        return dragged

    def release(self) -> None:
        self._host_block.release()
        self._row.release()
        self._painter.release()

    def _local(self, x: int, y: int) -> tuple[int, int]:
        return x - self._origin[0], y - self._origin[1]

    def _track_duration(self) -> float:
        """How long the track spans -- the clip, or the window a loop being
        recorded has zoomed it to, which is what the row was drawn from."""
        return 0.0 if self._clip_row is None else self._clip_row.duration_ms

    def motion(self, x: int, y: int) -> None:
        self._hover.take(self._painter.hover_at(x, y))

    def close(self) -> None:
        if self._shown:
            self._engine.remove_overlay(self.overlay_id)
            self._shown = False
