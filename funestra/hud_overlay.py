from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from app_support.written_file import WrittenFile

from .dashboard import already_done, ask
from .host_controls import HostControls, HostControlsHud, HostControlsPress
from .hud_button import Button
from .hud_controls import steps_of
from .hud_corners import HudPlace
from .hud_kinds import HudFacts, HudKind, main_title
from .hud_placement import HudCorner, HudEdge, PointerReading
from .hud_row import RowHud, RowLayout, RowPress, ScrubberRowDraw, track_on_screen
from .main_hud import ModeHud
from .modes import MainMode, Osr2State
from .name_copy import COPY_NAME, copy_while_the_funestra_plays_on
from .osr2_visualizer import DriveHud, DrivePublisher, published_here, read_drive
from .satellite_hud import (
    MARGIN,
    MINUS_INSET,
    HudModel,
    HudTargets,
    PaintedFoot,
    button_under,
    hit_test_targets,
    parse_hud,
)
from .satellite_hud_clicks import HudClicks, button_tooltip
from .satellite_hud_paint import DrawnWith, HudRenderer

HUD_OVERLAY_ID = 10

FOOT_PRESS = "foot_press"
FOOT_DRAG = "foot_drag"
FOOT_RELEASE = "foot_release"
FOOT_WHEEL = "foot_wheel"
FOOT_MENU = "foot_menu"

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


class PlayingFacts(NamedTuple):
    has_funscript: bool
    longer_than_a_step: bool
    image: bool


class _Hover(NamedTuple):
    loop: str
    tip: str
    button: Button | None
    at: tuple[int, int] | None

    def is_on_the_same_control_as(self, other: _Hover) -> bool:
        return (self.loop, self.tip, self.button) == (other.loop, other.tip, other.button)


_ON_NO_CONTROL = _Hover("", "", None, None)


class PublishedHud:
    def __init__(self, hud_file: Path, command_file: Path,
                 ask: Callable[[Path | None, str], None] = ask) -> None:
        self._hud_file = WrittenFile(hud_file)
        self._command_file = Path(command_file)
        self._ask = ask
        self._published = ""

    def next(self, shown: HudModel | None) -> tuple[HudModel | None, bool]:
        if not self._hud_file.may_have_been_written():
            return shown, False
        try:
            text = self._hud_file.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        except OSError:
            return shown, False
        self._hud_file.was_read()
        if text == self._published:
            return shown, False
        self._published = text
        return (parse_hud(text) if text else None), True

    def post(self, command: str) -> None:
        self._ask(self._command_file, command)


class ConsoleHud:
    def __init__(self, console: Path, command_file: Path, top_block: Callable[[], ModeHud],
                 ask: Callable[[Path | None, str], None] = ask) -> None:
        self._published = PublishedHud(console, command_file, ask)
        self._top_block = top_block
        self._console = _AT_REST
        self._built_from: tuple[HudModel, ModeHud] | None = None
        self._built: HudModel | None = None

    def next(self, shown: HudModel | None) -> tuple[HudModel | None, bool]:
        console, _changed = self._published.next(self._console)
        self._console = console or self._console
        block = self._top_block()
        if self._built_from is None or self._console is not self._built_from[0] or (
                block != self._built_from[1]):
            self._built_from = (self._console, block)
            self._built = replace(self._console, item_name=block.video,
                                  title=main_title(self._console.facts or HudFacts(), block))
        return self._built, self._built is not shown and self._built != shown

    def post(self, command: str) -> None:
        self._published.post(command)


LOCK_LIGHT_WAITS_S = 10.0

_AT_REST = HudModel(funestra="main", kind=HudKind.MAIN, facts=HudFacts(locked=True))


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
        source: PublishedHud | WindowsOwnHud | ConsoleHud,
        drawn_on: DrawnOn,
        drive: DriveFeed = NO_DRIVE,
        row: RowPress | None = None,
        host_controls: HostControls | None = None,
        clock=time.monotonic,
        clipboard: Callable[[str], None] = copy_while_the_funestra_plays_on,
        step_here: Callable[[str], None] | None = None,
    ) -> None:
        self._source = source
        self._step_here = step_here
        self._clipboard = clipboard
        self._drive_file = None if drive.file is None else WrittenFile(drive.file)
        self._drive_gate = drive.gate
        self._visualizer = drive.visualizer
        self._published_drive: DriveHud | None = None
        self._engine = drawn_on.engine
        self.overlay_id = drawn_on.overlay_id
        self._clock = clock
        self._over_the_video = drawn_on.over_the_video
        self._minus_on_the_hud = drawn_on.minus_on_the_hud
        self._width = drawn_on.width
        self._host_controls = HostControlsPress(host_controls)
        self._host_drawing: HostControlsHud | None = None
        self._renderer: HudRenderer | None = None
        self._clicks: HudClicks | None = None
        self._model: HudModel | None = None
        self._lock_light: tuple[bool, float] | None = None
        self._video = ""
        self._playing: PlayingFacts | None = None
        self._flash = ""
        self._playback_speed: float | None = None
        self._scrubber_row: RowHud | None = None
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
             scrubber_row: ScrubberRowDraw | None = None, flash: str = "",
             playing: PlayingFacts | None = None) -> None:
        row, heatmap = (None, None) if scrubber_row is None else scrubber_row
        the_row_moved = row != self._scrubber_row or heatmap is not self._heatmap
        redraw = (playing != self._playing or video != self._video or playback_speed != self._playback_speed
                  or viewport != self._viewport or flash != self._flash
                  or (the_row_moved and not self.minimized))
        self._video = video
        self._playing = playing
        self._playback_speed = playback_speed
        self._viewport = viewport
        self._flash = flash
        self._scrubber_row, self._heatmap = row, heatmap
        host_drawing = self._host_controls.drawing()
        if host_drawing != self._host_drawing:
            self._host_drawing = host_drawing
            redraw = True
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
        if self._lock_light is not None and self._host_caught_up_with_the_lock():
            self._lock_light = None
            redraw = True
        drive = self._motion()
        if drive is not None:
            self._visualizer.publish(drive, self._clock())
        if redraw or self._draw_owed:
            self._draw()

    def lock_pressed(self) -> None:
        if self._model is None or self._model.facts is None:
            return
        self._lock_light = (not self._lock_shown(), self._clock())
        self._draw()

    def _lock_shown(self) -> bool:
        return self._model.facts.locked if self._lock_light is None else self._lock_light[0]

    def _host_caught_up_with_the_lock(self) -> bool:
        light, since = self._lock_light
        facts = None if self._model is None else self._model.facts
        return (facts is None or facts.locked == light
                or self._clock() - since > LOCK_LIGHT_WAITS_S)

    def press(self, x: int, y: int) -> bool:
        if self._clicks is None or not self.covers(x, y):
            return False
        self._pointer_at = self._local(x, y)
        if self._host_controls.press(*self._pointer_at, layout=self.targets.host_controls):
            self._host_drawing = self._host_controls.drawing()
            self._draw()
            return True
        if self._row.press(*self._pointer_at, layout=self.targets.row,
                           duration_ms=self._track_duration()):
            return True
        if self._foot_covers(*self._pointer_at):
            self._foot_held = True
            self._post_on_the_foot(FOOT_PRESS)
            return True
        command = self._clicks.press(self.targets, *self._pointer_at, now=self._clock())
        if command == COPY_NAME:
            self._clipboard(self._name)
        elif command:
            self._post(command)
            self._draw()
        return True

    def wheel(self, x: int, y: int, steps: int) -> bool:
        return self._only_on_the_foot(x, y, FOOT_WHEEL, steps)

    def right_press(self, x: int, y: int) -> bool:
        return self._only_on_the_foot(x, y, FOOT_MENU)

    def _only_on_the_foot(self, x: int, y: int, verb: str, *values: int) -> bool:
        if self._clicks is None or not self.covers(x, y):
            return False
        self._pointer_at = self._local(x, y)
        if self._foot_covers(*self._pointer_at):
            self._post_on_the_foot(verb, *values)
        return True

    def _track_duration(self) -> float:
        return 0.0 if self._scrubber_row is None else self._scrubber_row.duration_ms

    @property
    def row(self) -> RowLayout | None:
        return self.targets.row

    @property
    def scrubber_row(self) -> RowHud | None:
        return self._scrubber_row

    @property
    def row_track(self) -> tuple[int, int, int] | None:
        return track_on_screen(
            self.targets.row, origin=self._origin,
            hud_height=0 if self._hud_size is None else self._hud_size[1])

    @property
    def holding(self) -> bool:
        return self._host_controls.holding or self._row.holding or self._foot_held or (
            self._clicks is not None and self._clicks.holding)

    def drag_to(self, x: int, y: int) -> str:
        self._pointer_at = self._local(x, y)
        if self._host_controls.drag_to(*self._pointer_at, layout=self.targets.host_controls):
            return ""
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
        self._host_controls.release()
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
        if (self._visualizer is None or self._drive_file is None or self._model is None
                or not self._model.osr2):
            return None
        self._read_the_drive_if_it_was_replaced()
        if self._drive_gate is None:
            return self._published_drive
        facts = self._model.facts
        return self._drive_gate.visualizer(
            self._published_drive, device_drives_itself=self._model.osr2 == Osr2State.AUTO,
            video_shows=facts is None or facts.main_mode is MainMode.KINO)

    def _read_the_drive_if_it_was_replaced(self) -> None:
        here = published_here(self._drive_file.path)
        if here is not None:
            self._published_drive = here
            return
        if not self._drive_file.may_have_been_written():
            return
        drive = read_drive(self._drive_file.path)
        if drive is not None:
            self._drive_file.was_read()
            self._published_drive = drive

    def _draw(self) -> None:
        hover = self._hover.on(self._model)
        if (self._model is None or self._renderer is None
                or (self._model.hud_minimized and not self._minus_on_the_hud)):
            self.targets = _EMPTY_TARGETS
            self.close()
            return
        corner = self._model.hud_corner if self._over_the_video else HudCorner.UPPER_LEFT
        model = replace(self._model, playback_speed=self._playback_speed, hud_corner=corner)
        if self._playing is not None and model.facts is not None:
            model = replace(model, facts=replace(model.facts, **self._playing._asdict()))
        if self._lock_light is not None and model.facts is not None:
            model = replace(model, facts=replace(model.facts, locked=self._lock_light[0]))
        self._draw_owed = True
        rendered = self._renderer.render(
            model, scrubber_row=self._scrubber_row, heatmap=self._heatmap,
            drawn_with=DrawnWith(
                video=self._name, hover_loop=hover.loop, hover_tip=hover.tip, hover_pos=hover.at,
                may_grow_on_hover=self._over_the_video,
                minus_on_the_hud=self._minus_on_the_hud, flash=self._flash,
                width=self._width),
            host_controls=self._host_drawing,
        )
        height, width = rendered.bgra.shape[:2]
        origin = self._place(corner, (width, height))
        self._engine.overlay(self.overlay_id, *origin, rendered.bgra)
        self._draw_owed = False
        self.targets = rendered.targets
        self._hud_size = (width, height)
        self._origin = origin
        self._shown = True

    @property
    def _name(self) -> str:
        return (self._model.item_name if self._model is not None else "") or self._video

    def _post(self, command: str) -> None:
        if self._model is not None and command == f"{self._model.funestra}_lock":
            self.lock_pressed()
        verb = steps_of(self._model.funestra).get(command) if self._model is not None else None
        if verb is None or self._step_here is None:
            self._source.post(command)
            return
        pressed_at = self._clock()
        self._step_here(f"{verb} {pressed_at:.3f}")
        self._source.post(already_done(command, pressed_at))
