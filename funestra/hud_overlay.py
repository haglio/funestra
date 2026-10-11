"""The panel kept on the picture: taken from its source, rendered when it changes, composited, pressed.

Two sources.  A session in another process publishes the panel to a file and
takes its presses back on the dashboard's command file; a window's own
program -- a standalone Origenerator building its Slideshow's panel -- hands
the model over in-process and takes the presses itself.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import NamedTuple

from .dashboard import ask
from .drive_readout import DriveHud, read_drive
from .hud_corners import HudPlace
from .hud_placement import HudCorner, HudEdge, PointerReading
from .hud_row import RowHud, RowLayout, RowPress, track_on_screen
from .modes import Osr2State
from .renamed import answers_to_old_names
from .satellite_hud import (
    MARGIN,
    MINUS_INSET,
    HudClicks,
    HudModel,
    HudTargets,
    button_tooltip,
    hit_test_targets,
    parse_hud,
)
from .satellite_hud_paint import HudRenderer

__all__ = [
    "FOOT_DRAG",
    "FOOT_PRESS",
    "FOOT_RELEASE",
    "FOOT_WHEEL",
    "HUD_OVERLAY_ID",
]

HUD_OVERLAY_ID = 10

# What the panel posts about the block its source paints at its foot: the
# source placed it and knows what is drawn where, so a press, a drag, the
# button coming up and the wheel go back to it with where they landed, in the
# block's own pixels.
FOOT_PRESS = "foot_press"
FOOT_DRAG = "foot_drag"
FOOT_RELEASE = "foot_release"
FOOT_WHEEL = "foot_wheel"

_EMPTY_TARGETS = HudTargets(click=[], loop=[], filter=[], expand=None)


class _Hover(NamedTuple):
    loop: str
    tip: str
    at: tuple[int, int]

    def is_on_the_same_control_as(self, other: _Hover) -> bool:
        return (self.loop, self.tip) == (other.loop, other.tip)


_ON_NO_CONTROL = _Hover("", "", (0, 0))


class _PublishedPanel:
    """The panel a session publishes to a file, and the file its presses go back on."""

    def __init__(self, hud_file: Path, command_file: Path) -> None:
        self._hud_file = Path(hud_file)
        self._command_file = Path(command_file)
        self._published = ""

    def next(self, shown: HudModel | None) -> tuple[HudModel | None, bool]:
        """The panel to show and whether it changed -- unchanged for a frame
        that lost the race with the source replacing the file."""
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


class _WindowsOwnPanel:
    """The panel the window's own program hands over, and where its presses go."""

    def __init__(self, panel: Callable[[], HudModel | None],
                 post: Callable[[str], None]) -> None:
        self._panel = panel
        self.post = post

    def next(self, shown: HudModel | None) -> tuple[HudModel | None, bool]:
        model = self._panel()
        return model, model != shown


@answers_to_old_names({"player": "engine"})
class HudOverlay:
    def __init__(
        self,
        *,
        engine,
        hud_file: Path | None = None,
        command_file: Path | None = None,
        panel: Callable[[], HudModel | None] | None = None,
        post: Callable[[str], None] | None = None,
        overlay_id: int = HUD_OVERLAY_ID,
        clock=time.monotonic,
        drive_file: Path | None = None,
        drive_gate=None,
        over_the_video: bool = True,
        minus_on_the_panel: bool = True,
        seek=None,
        seek_loop=None,
        set_volume=None,
        toggle_mute=None,
    ) -> None:
        self._source = (_WindowsOwnPanel(panel, post) if panel is not None
                        else _PublishedPanel(hud_file, command_file))
        self._drive_file = None if drive_file is None else Path(drive_file)
        self._drive_gate = drive_gate
        self._published_drive: DriveHud | None = None
        self._drive: DriveHud | None = None
        self._engine = engine
        self.overlay_id = overlay_id
        self._clock = clock
        self._over_the_video = over_the_video
        self._minus_on_the_panel = minus_on_the_panel
        self._renderer: HudRenderer | None = None
        self._clicks: HudClicks | None = None
        self._model: HudModel | None = None
        self._video = ""
        self._playback_speed: float | None = None
        self._clip_row: RowHud | None = None
        self._heatmap = None
        # The panel draws the clip's row, so it places a press on it too.
        self._row = RowPress(seek=seek, seek_loop=seek_loop, set_volume=set_volume,
                             toggle_mute=toggle_mute)
        self._hover: PointerReading[_Hover] = PointerReading(_ON_NO_CONTROL)
        self._pointer_at = (0, 0)
        self._foot_held = False
        self._shown = False
        self._window: tuple[int, int] | None = None
        self._origin = (MARGIN, MARGIN)
        self._panel_size: tuple[int, int] | None = None
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

    def tick(self, video: str = "", playback_speed: float | None = None,
             window: tuple[int, int] | None = None,
             clip_row: RowHud | None = None, heatmap=None) -> None:
        redraw = (video != self._video or playback_speed != self._playback_speed
                  or window != self._window
                  or clip_row != self._clip_row or heatmap is not self._heatmap)
        self._video = video
        self._playback_speed = playback_speed
        self._window = window
        self._clip_row, self._heatmap = clip_row, heatmap
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
        if drive != self._drive:
            self._drive = drive
            redraw = True
        if redraw:
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
        """The wheel turned *steps* notches over the panel: the block at the
        foot takes it, and the rest of the panel is a surface with nothing to
        turn, which is still the panel's and not the picture's."""
        if self._clicks is None or not self.covers(x, y):
            return False
        self._pointer_at = self._local(x, y)
        if self._foot_covers(*self._pointer_at):
            self._post_on_the_foot(FOOT_WHEEL, steps)
        return True

    def _track_duration(self) -> float:
        """How long the track spans -- the clip, or the window a loop being
        recorded has zoomed it to, which is what the row was drawn from."""
        return 0.0 if self._clip_row is None else self._clip_row.duration_ms

    # Only the headset's old copies of the row, in checkouts from before
    # haglio/fun_time#391, read row_rect; it answers until none of them is open.
    @property
    def row_rect(self) -> tuple[int, int, int, int] | None:
        return None if self.targets.row is None else self.targets.row.rect

    @property
    def row(self) -> RowLayout | None:
        """Where the row landed in this panel and how it is laid out,
        for a host measuring the track it is to fill."""
        return self.targets.row

    @property
    def row_track(self) -> tuple[int, int, int] | None:
        """The row's track in the window's coordinates, for a host hanging the
        loop's frames under it."""
        return track_on_screen(
            self.targets.row, origin=self._origin,
            panel_height=0 if self._panel_size is None else self._panel_size[1])

    @property
    def holding(self) -> bool:
        return self._row.holding or self._foot_held or (
            self._clicks is not None and self._clicks.holding)

    def drag_to(self, x: int, y: int) -> str:
        """The pointer held down and moving: the row goes on being set, and past
        the row, whatever the panel itself took hold of."""
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
        """Let go of whichever part of the row, of the foot, or of the panel a press took."""
        self._row.release()
        if self._foot_held:
            self._foot_held = False
            self._post_on_the_foot(FOOT_RELEASE)
        if self._clicks is not None:
            self._clicks.release()

    def motion(self, x: int, y: int) -> None:
        px, py = self._local(x, y)
        self._pointer_at = (px, py)
        hover = _Hover(hit_test_targets(self.targets.loop, px, py),
                       button_tooltip(self.targets, px, py), (px, py))
        if hover.is_on_the_same_control_as(self._hover.reading):
            return
        self._hover.take(hover)
        self._draw()

    def close(self) -> None:
        self._panel_size = None
        if self._shown:
            self._engine.remove_overlay(self.overlay_id)
            self._shown = False

    def covers(self, x: int, y: int) -> bool:
        if self._panel_size is None:
            return False
        left, top = self._origin
        width, height = self._panel_size
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
        self._post("|".join(str(part) for part in (verb, *values, px - x, py - y)))

    def _local(self, x: int, y: int) -> tuple[int, int]:
        left, top = self._origin
        return x - left, y - top

    def _place(self, corner: HudCorner, size: tuple[int, int]) -> tuple[int, int]:
        if self._window is None:
            return MARGIN, MARGIN
        return replace(self.hud_place, corner=corner).origin(panel=size, window=self._window)

    def _motion(self) -> DriveHud | None:
        if self._drive_file is None or self._model is None or not self._model.osr2:
            return None
        self._published_drive = read_drive(self._drive_file) or self._published_drive
        if self._drive_gate is None:
            return self._published_drive
        return self._drive_gate.readout(
            self._published_drive, device_drives_itself=self._model.osr2 == Osr2State.AUTO)

    def _draw(self) -> None:
        hover = self._hover.on(self._model)
        if (self._model is None or self._renderer is None
                or (self._model.hud_minimized and not self._minus_on_the_panel)):
            self.targets = _EMPTY_TARGETS
            self.close()
            return
        corner = self._model.hud_corner if self._over_the_video else HudCorner.UPPER_LEFT
        drive = self._model.drive if self._drive_file is None else self._drive
        rendered = self._renderer.render(
            replace(self._model, playback_speed=self._playback_speed, drive=drive,
                    drive_composed=self._drive_gate is not None, hud_corner=corner),
            video=self._video, hover_loop=hover.loop, hover_tip=hover.tip, hover_pos=hover.at,
            may_grow_on_hover=self._over_the_video,
            minus_on_the_panel=self._minus_on_the_panel,
            clip_row=self._clip_row, heatmap=self._heatmap,
        )
        self.targets = rendered.targets
        height, width = rendered.bgra.shape[:2]
        self._panel_size = (width, height)
        self._origin = self._place(corner, self._panel_size)
        self._engine.overlay(self.overlay_id, *self._origin, rendered.bgra)
        self._shown = True

    def _post(self, command: str) -> None:
        self._source.post(command)
