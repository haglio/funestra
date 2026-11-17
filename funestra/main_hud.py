from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from app_support import osr2_hold
from shared_ui.spacing import BUTTON_GAP, BUTTON_GROUP_GAP, BUTTON_ROW_GAP
from shared_ui.toggle_geometry import TRACK_HUD

from .geometry import Rect, contains
from .hud_button import (
    BUTTON,
    FIT_THE_WORD,
    Button,
    buttons_from_raw,
    buttons_raw,
    rows_from_raw,
    rows_raw,
)
from .hud_icons import BROKER_ICON, TOGGLE_SWITCH, shared_icon
from .hud_placement import HudCorner, HudEdge
from .modes import LengthMode, MainMode, Osr2State, read_mode
from .robot_hand import WaveformShape

VALUE_W = 22
ROW_LABEL_W = 84
GAP = BUTTON_GAP
ROW_GAP = BUTTON_ROW_GAP
GROUP_GAP = BUTTON_GROUP_GAP

_SHAPE_LABELS = {"rounded_square": "Square"}


def shape_label(shape: str) -> str:
    if shape in _SHAPE_LABELS:
        return _SHAPE_LABELS[shape]
    return " ".join(word.capitalize() for word in shape.split("_"))


@dataclass(frozen=True)
class ModeHud:
    video: str = ""
    length_mode: LengthMode | None = None
    compilation: str = ""
    position: int = 0
    total: int = 0
    scripted_filter: bool = False


OSR2_PARKED = "parked"
OSR2_RETRACTED = "retracted"
OSR2_DRIVING = "driving"
OSR2_CONTROL_UNANSWERED = ""

OSR2_CONTROL_BUTTONS: dict[str, str] = {
    OSR2_PARKED: "robot_hand_park",
    OSR2_DRIVING: "robot_hand_release",
}
_SWITCH_SAYS = {
    OSR2_DRIVING: "OSR2 control on — the OSR2 follows whatever the motion is doing. "
                  "Press to switch control off: the OSR2 parks at home",
    OSR2_PARKED: "OSR2 control off — the OSR2 parked, held still at home. "
                 "Press to switch control on",
    OSR2_RETRACTED: "OSR2 control off — the OSR2 held still at the far end, away from you. "
                    "Press to switch control on",
}

HELD_HEIGHT = MappingProxyType({OSR2_PARKED: 0.0, OSR2_RETRACTED: 1.0})
HOLD_VERB = MappingProxyType({OSR2_PARKED: osr2_hold.PARK, OSR2_RETRACTED: osr2_hold.RETRACT})

_WAVEFORM_FACES = {
    WaveformShape.SINE.value: "wave",
    WaveformShape.TRIANGLE.value: "wave_triangle",
    WaveformShape.ROUNDED_SQUARE.value: "wave_square",
    WaveformShape.SAWTOOTH.value: "wave_sawtooth",
}


def aim_row(*, learned: bool, shape: str, control: str) -> tuple[Button, ...]:
    return (
        *_osr2_switch(control),
        Button("robot_hand_toggle_learned", shared_icon("human"),
               "Human inspired: motion drawn from real hand-made scripts, not a waveform",
               lit=learned, group_break=True),
        Button("robot_hand_cycle_shape", shared_icon(_WAVEFORM_FACES.get(shape, "wave")),
               f"Waveform: {shape_label(shape)}"),
    )


def _osr2_switch(control: str) -> tuple[Button, ...]:
    on = control == OSR2_DRIVING
    return (
        Button("", "OSR2 control", "", width=FIT_THE_WORD),
        Button("", "Off", "", lit=not on),
        Button(OSR2_CONTROL_BUTTONS[OSR2_PARKED if on else OSR2_DRIVING], TOGGLE_SWITCH,
               _SWITCH_SAYS.get(control, "OSR2 control off. Press to switch control on"),
               width=TRACK_HUD[0], lit=on),
        Button("", "On", "", lit=on),
    )


BROKER_PRESS = "broker_panel"


def osr2_controls(*, broker_running: bool) -> tuple[Button, ...]:
    return (
        Button(BROKER_PRESS, BROKER_ICON,
               "Broker is running — press to stop it" if broker_running
               else "Broker is not running — press to start it",
               lit=broker_running, warn=not broker_running),
    )


@dataclass(frozen=True)
class MainHudModel:
    main_mode: MainMode = MainMode.KINO
    funestra: str = "main"
    hud_corner: HudCorner = HudCorner.UPPER_LEFT
    hud_edge: HudEdge = HudEdge.LOWER
    hud_minimized: bool = False
    active: bool = False
    osr2: Osr2State = Osr2State.OFF
    osr2_control: str = OSR2_CONTROL_UNANSWERED
    paused: bool = False
    locked: bool = True
    latest: bool | None = None
    filters: tuple[str, ...] = ()
    playback_speed: float = 1.0
    advance_interval: int = 0
    rows: tuple[tuple[Button, ...], ...] = ()
    osr2_rows: tuple[tuple[Button, ...], ...] = ()
    osr2_controls: tuple[Button, ...] = ()
    has_osr2: bool = True
    max_intensity: int | None = None

    @property
    def device_drives_itself(self) -> bool:
        return self.osr2 == Osr2State.AUTO


def read_main_hud(path: Path) -> MainHudModel | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_main_hud(text)


def main_hud_text(model: MainHudModel) -> str:
    return json.dumps({
        "main_mode": model.main_mode,
        "funestra": model.funestra,
        "hud_corner": model.hud_corner,
        "hud_edge": model.hud_edge,
        "hud_minimized": model.hud_minimized,
        "active": model.active,
        "latest": model.latest,
        "filters": list(model.filters),
        "osr2": model.osr2,
        "osr2_control": model.osr2_control,
        "paused": model.paused,
        "locked": model.locked,
        "rows": rows_raw(model.rows),
        "osr2_rows": rows_raw(model.osr2_rows),
        "osr2_controls": buttons_raw(model.osr2_controls),
        "has_osr2": model.has_osr2,
        "max_intensity": model.max_intensity,
    })


def parse_main_hud(text: str) -> MainHudModel | None:
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or "main_mode" not in raw:
        return None
    return MainHudModel(
        main_mode=read_mode(MainMode, raw.get("main_mode"), MainMode.KINO),
        funestra=str(raw.get("funestra") or "main"),
        hud_corner=read_mode(HudCorner, raw.get("hud_corner"), HudCorner.UPPER_LEFT),
        hud_edge=read_mode(HudEdge, raw.get("hud_edge"), HudEdge.LOWER),
        hud_minimized=bool(raw.get("hud_minimized", False)),
        active=bool(raw.get("active", False)),
        latest=(None if raw.get("latest") is None else bool(raw.get("latest"))),
        filters=_filters_from_raw(raw.get("filters")),
        osr2=read_mode(Osr2State, raw.get("osr2"), Osr2State.OFF),
        osr2_control=str(raw.get("osr2_control", "") or OSR2_CONTROL_UNANSWERED),
        paused=bool(raw.get("paused", False)),
        locked=bool(raw.get("locked", True)),
        rows=rows_from_raw(raw.get("rows")),
        osr2_rows=rows_from_raw(raw.get("osr2_rows")),
        osr2_controls=buttons_from_raw(raw.get("osr2_controls")),
        has_osr2=bool(raw.get("has_osr2", True)),
        max_intensity=max_intensity_from_raw(raw.get("max_intensity")),
    )


def _filters_from_raw(raw) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(word) for word in raw if word)


def max_intensity_from_raw(raw) -> int | None:
    try:
        return None if raw is None else int(raw)
    except (TypeError, ValueError):
        return None


def kino_shows(main_mode: MainMode) -> bool:
    return main_mode == MainMode.KINO


def place_rows(rows: list[list[Button]], *, x: int, y: int,
               ends_at: int | None = None) -> list[tuple[Rect, Button]]:
    placed: list[tuple[Rect, Button]] = []
    row_y = y
    for row in rows:
        run_x = x if ends_at is None else max(x, ends_at - one_row_width(row))
        for index, button in enumerate(row):
            if index and button.group_break:
                run_x += GROUP_GAP - GAP
            placed.append(((run_x, row_y, button.width, BUTTON), button))
            run_x += button.width + GAP
        row_y += BUTTON + ROW_GAP
    return placed


def one_row_width(row: list[Button]) -> int:
    return max((rect[0] + rect[2] for rect, _b in place_rows([row], x=0, y=0)), default=0)


def _row_width(rows: list[list[Button]]) -> int:
    return max((one_row_width(row) for row in rows), default=0)


def rows_height(rows: list[list[Button]]) -> int:
    return max(0, len(rows) * (BUTTON + ROW_GAP) - ROW_GAP)


def hit_test(placed: list[tuple[Rect, Button]], px: int, py: int) -> str:
    for rect, button in placed:
        if button.dim or not button.command:
            continue
        if contains(rect, px, py):
            return button.command
    return ""


def tooltip_at(placed: list[tuple[Rect, Button]], px: int, py: int) -> str:
    for (bx, by, bw, bh), button in placed:
        if bx <= px < bx + bw and by <= py < by + bh:
            return button.tooltip_on_hover
    return ""
