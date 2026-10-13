"""The controls on the main console, and where they sit.

The Main Funestra draws it, whether Kino or Genau runs on it.  The console is the
same under both, so the mode switch and the drive
controls do not move as you flip between them; only the transport changes,
because prev/next step Kino's video in kino mode and Genau's flicks in genau.

Kept free of Pillow, as :mod:`funestra.satellite_hud` is, so the
geometry and the hit-testing are testable without a font.  :mod:`funestra.console_hud` paints them; the
drive readout's own arrows come from :mod:`funestra.drive_readout`.

The buttons are the source's own (:attr:`ConsoleModel.rows`), each posting its
command verbatim to the command file that source reads; this module places them
and says which one a press landed on.  The one row built here is the one every
source with the OSR2 draws alike, :func:`aim_row`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .geometry import Rect, contains
from .hud_button import BUTTON, Button, buttons_from_raw, buttons_raw, rows_from_raw, rows_raw
from .hud_marks import shared_mark
from .hud_placement import HudCorner, HudEdge
from .modes import LengthMode, MainMode, Osr2State, read_mode
from .renamed import answers_to_old_names
from .robot_hand import WaveformShape

__all__ = [
    "GAP",
    "GROUP_GAP",
    "OSR2_CONTROL_BUTTONS",
    "OSR2_CONTROL_OFF",
    "OSR2_CONTROL_UNANSWERED",
    "OSR2_DRIVING",
    "OSR2_PARKED",
    "OSR2_RETRACTED",
    "ROW_LABEL_W",
    "VALUE_W",
    "ConsoleModel",
    "aim_row",
    "console_text",
    "hit_test",
    "parse_console",
    "place_rows",
    "read_console",
    "tooltip_at",
]

VALUE_W = 22  # a value read-out between a pair of buttons (the playback rate)
# The cell a word naming its row takes: "Playback speed", the longer of the
# two names the family's consoles carry, measures 80 at the tiny face, plus the
# family's gap.  One width for every named row, so the pair beside the name
# sits in the same place whichever row is up; the painter widens a name that
# outgrows it rather than letting it run under the button beside it.
ROW_LABEL_W = 84
GAP = 4       # between buttons along a row
ROW_GAP = 5   # between rows
GROUP_GAP = 12  # between groups of buttons that mean different things

_SHAPE_LABELS = {"rounded_square": "Square"}


def shape_label(shape: str) -> str:
    """The waveform's name, for the control that cycles it to say what it is on.

    ``rounded_square`` is the one whose internal name reads badly spelled out;
    the rest title-case.
    """
    if shape in _SHAPE_LABELS:
        return _SHAPE_LABELS[shape]
    return " ".join(word.capitalize() for word in shape.split("_"))


@dataclass(frozen=True)
class ModeHud:
    """What runs on a Funestra says about what it is playing — what only it knows.

    *video* is the name of the clip on screen, drawn as the muted line beneath
    the status.  *length_mode* is the library's filter, empty when there is no
    library backing the playlist; *compilation* is the volume holding the
    playlist, with *position*/*total* placing the current video in it;
    *scripted_filter* is Fun Time's F-mode over whichever of those runs, keeping
    the videos that have a funscript.  All empty in genau mode, where there is
    no Kino playlist to describe.
    """

    video: str = ""
    # None where there is no library backing the playlist, so no length is
    # being asked for at all -- as against NONE, which asks for neither length.
    length_mode: LengthMode | None = None
    compilation: str = ""
    position: int = 0
    total: int = 0
    scripted_filter: bool = False


# Those four states themselves.  One word rather than a flag each, because they
# are exclusive: whatever this app is doing to the OSR2, it is doing exactly one
# of these, and the console lights exactly one button to say which.  Off is the
# app not driving the device at all — the device itself is untouched by it, which
# is why the word on the button and the pill is "control off" rather than "off".
OSR2_PARKED = "parked"
OSR2_RETRACTED = "retracted"
OSR2_DRIVING = "driving"
OSR2_CONTROL_OFF = "control_off"
# And a fifth answer that is not a state: this host has no such switch, so the
# console names none of the four.
OSR2_CONTROL_UNANSWERED = ""

# Which button stands for which state, in the order they sit, from off to on:
# nothing going out, the two holds, the motion running.  Data, so a consumer
# routing a press can read the state off the command rather than spelling this
# out a second time.
OSR2_CONTROL_BUTTONS: dict[str, str] = {
    OSR2_CONTROL_OFF: "osr2_control_off",
    OSR2_PARKED: "robot_hand_park",
    OSR2_RETRACTED: "robot_hand_retract",
    OSR2_DRIVING: "robot_hand_release",
}

HELD_HEIGHT = {OSR2_PARKED: 0.0, OSR2_RETRACTED: 1.0}

_WAVEFORM_FACES = {
    WaveformShape.SINE.value: "wave",
    WaveformShape.TRIANGLE.value: "wave_triangle",
    WaveformShape.ROUNDED_SQUARE.value: "wave_square",
    WaveformShape.SAWTOOTH.value: "wave_sawtooth",
}


def aim_row(*, learned: bool, shape: str, control: str,
            cruise: bool | None = None) -> tuple[Button, ...]:
    return (
        *(() if cruise is None else (
            Button("robot_hand_toggle_cruise", "cc",
                   "Cruise control: vary the motion hands-free", lit=cruise),)),
        Button("robot_hand_toggle_learned", "hi",
               "Human inspired: motion drawn from real hand-made scripts, not a waveform",
               lit=learned),
        Button("robot_hand_cycle_shape", shared_mark(_WAVEFORM_FACES.get(shape, "wave")),
               f"Waveform: {shape_label(shape)}"),
        Button("quarter_button", shared_mark("quarter_offset"), "Offset the motion a ¼ cycle"),
        *((
            Button(OSR2_CONTROL_BUTTONS[OSR2_CONTROL_OFF], shared_mark("control_off"),
                   "Control off — the OSR2 settles home and is left there; nothing "
                   "here moves it again until you park, retract or drive it.  The "
                   "device itself stays on: this is the app letting go of it, not "
                   "the OSR2 switching off",
                   warn=control == OSR2_CONTROL_OFF, group_break=True),
        ) if control != OSR2_CONTROL_UNANSWERED else ()),
        Button(OSR2_CONTROL_BUTTONS[OSR2_PARKED], shared_mark("park"),
               "Parked — the OSR2 held still, settled home",
               lit=control == OSR2_PARKED, group_break=control == OSR2_CONTROL_UNANSWERED),
        Button(OSR2_CONTROL_BUTTONS[OSR2_RETRACTED], shared_mark("retract"),
               "Retracted — the OSR2 held still at the far end, away from you",
               lit=control == OSR2_RETRACTED),
        Button(OSR2_CONTROL_BUTTONS[OSR2_DRIVING], shared_mark("release"),
               "Driving — the OSR2 back on whatever the motion was doing",
               lit=control == OSR2_DRIVING),
    )


@answers_to_old_names({"player": "funestra"})
@dataclass(frozen=True)
class ConsoleModel:
    """What Fun Time tells the Main Funestra about its slot, so the console can
    draw it — none of which the Funestra can see for itself.

    Everything here arrives published (``main_player_console.json``) except
    ``playback_speed``, which is Kino's own and folded in by whoever is drawing.
    """

    main_mode: MainMode = MainMode.KINO
    funestra: str = "main"
    hud_corner: HudCorner = HudCorner.UPPER_LEFT
    hud_edge: HudEdge = HudEdge.LOWER
    hud_minimized: bool = False
    # The dot: whether a bare command naming no Funestra ("next", "lock") lands
    # on the Main Funestra rather than on a satellite.
    active: bool = False
    # What is driving the OSR2 right now.
    osr2: Osr2State = Osr2State.OFF
    # And what this app is doing to it, which is a different question: one of
    # OSR2_CONTROL_BUTTONS' four states, or OSR2_CONTROL_UNANSWERED from a host
    # that has no such switch.  Published like the rest of this, because the
    # state is the orchestrator's and the Funestra drawing the console is not
    # always the one it is about.
    osr2_control: str = OSR2_CONTROL_UNANSWERED
    # Whether what runs on the Main Funestra is holding what is on screen rather
    # than letting it move on -- Kino's video in kino mode, Genau's flick in
    # genau.  On is where both open, so it is the default here
    # too: a console drawn before the first panel arrives must not show the lock
    # off when it is not.
    locked: bool = True
    # Which browse order the status line names: newest-first ("Latest") when
    # set, shuffled when clear, and nothing at all for a host with no browse
    # order to name -- Origenerator's motion panel, whose slides are a show's
    # own set.
    latest: bool | None = None
    # Kino's video playback rate, shown while Kino is on screen.  Not published —
    # Kino knows its own rate and folds it in; Genau leaves it at 1.
    playback_speed: float = 1.0
    # Seconds an unlocked Genau leaves each flick on screen.  Also not published —
    # Genau owns the pace and says it on the drive readout, which whoever draws
    # the console folds in here.
    advance_interval: int = 0
    # The buttons the source declares, row by row, and the controls it puts on
    # the OSR2 line: what each posts, its face, its tooltip and its state.  The
    # console draws nothing it was not handed.
    rows: tuple[tuple[Button, ...], ...] = ()
    osr2_rows: tuple[tuple[Button, ...], ...] = ()
    osr2_controls: tuple[Button, ...] = ()
    has_osr2: bool = True
    max_intensity: int | None = None

    @property
    def device_drives_itself(self) -> bool:
        """Whether the OSR2 is in auto mode, running its own firmware.

        Neither driver reaches it there: the broker stops forwarding the
        script's T-Code and Genau is not sending.  So the picture is the
        device's own motion rather than a handoff between the two, which is
        what every Funestra hanging this console over a video asks before it
        lets the gate fold a script in.
        """
        return self.osr2 == Osr2State.AUTO


def read_console(path: Path) -> ConsoleModel | None:
    """The console panel Fun Time published, or None when there is not a whole one.

    None means "keep the console you have": Fun Time replaces this file while the
    Funestra polls it, so a lost race must not empty the panel for a frame.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_console(text)


def console_text(model: ConsoleModel) -> str:
    """*model* as the text Fun Time publishes, and :func:`parse_console` reads back.

    Only what the room knows and the Funestra cannot see goes out; the rate and
    the pace, which the drawing host folds in for itself, come back at rest.
    """
    return json.dumps({
        "main_mode": model.main_mode,
        "funestra": model.funestra,
        # The same, under the key a reader from before the rename looks for.
        "player": model.funestra,
        "hud_corner": model.hud_corner,
        "hud_edge": model.hud_edge,
        "hud_minimized": model.hud_minimized,
        "active": model.active,
        "latest": model.latest,
        "osr2": model.osr2,
        "osr2_control": model.osr2_control,
        "locked": model.locked,
        "rows": rows_raw(model.rows),
        "osr2_rows": rows_raw(model.osr2_rows),
        "osr2_controls": buttons_raw(model.osr2_controls),
        "has_osr2": model.has_osr2,
        "max_intensity": model.max_intensity,
    })


def parse_console(text: str) -> ConsoleModel | None:
    """The panel *text* carries, or None when it is not a whole one."""
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or "main_mode" not in raw:
        return None
    return ConsoleModel(
        main_mode=read_mode(MainMode, raw.get("main_mode"), MainMode.KINO),
        funestra=str(raw.get("funestra") or raw.get("player") or "main"),
        hud_corner=read_mode(HudCorner, raw.get("hud_corner"), HudCorner.UPPER_LEFT),
        hud_edge=read_mode(HudEdge, raw.get("hud_edge"), HudEdge.LOWER),
        hud_minimized=bool(raw.get("hud_minimized", False)),
        active=bool(raw.get("active", False)),
        # Absent is None -- no browse order to name -- rather than "shuffled".
        latest=(None if raw.get("latest") is None else bool(raw.get("latest"))),
        osr2=read_mode(Osr2State, raw.get("osr2"), Osr2State.OFF),
        osr2_control=str(raw.get("osr2_control", "") or OSR2_CONTROL_UNANSWERED),
        locked=bool(raw.get("locked", True)),
        rows=rows_from_raw(raw.get("rows")),
        osr2_rows=rows_from_raw(raw.get("osr2_rows")),
        osr2_controls=buttons_from_raw(raw.get("osr2_controls")),
        has_osr2=bool(raw.get("has_osr2", True)),
        max_intensity=max_intensity_from_raw(raw.get("max_intensity")),
    )


def max_intensity_from_raw(raw) -> int | None:
    try:
        return None if raw is None else int(raw)
    except (TypeError, ValueError):
        return None


def kino_shows(main_mode: MainMode) -> bool:
    """Whether Kino is what the Main Funestra shows."""
    return main_mode == MainMode.KINO


def place_rows(rows: list[list[Button]], *, x: int, y: int,
               ends_at: int | None = None) -> list[tuple[Rect, Button]]:
    """Each button's rect, rows stacked down from ``(x, y)``, or ending at
    *ends_at* with each row's own order kept.

    One placement feeds both the painting and the hit-testing, so what is drawn
    and what is clickable cannot drift apart.
    """
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
    """How wide the widest row runs — what the panel has to be to hold them."""
    return max((one_row_width(row) for row in rows), default=0)


def rows_height(rows: list[list[Button]]) -> int:
    """How tall the stack runs, with no trailing row gap."""
    return max(0, len(rows) * (BUTTON + ROW_GAP) - ROW_GAP)


def hit_test(placed: list[tuple[Rect, Button]], px: int, py: int) -> str:
    """The command for a press at ``(px, py)``, or "" over none of the buttons.

    A dimmed control is skipped: it is at its limit or has nothing to act on, so
    the press it would post is one Fun Time would ignore.
    """
    for rect, button in placed:
        if button.dim or not button.command:
            continue
        if contains(rect, px, py):
            return button.command
    return ""


def tooltip_at(placed: list[tuple[Rect, Button]], px: int, py: int) -> str:
    """What the button under ``(px, py)`` is — every glyph here is cryptic on
    purpose, so each one names itself on hover.  A dimmed control still answers:
    knowing why it cannot be pressed is the point."""
    for (bx, by, bw, bh), button in placed:
        if bx <= px < bx + bw and by <= py < by + bh:
            return button.tooltip_on_hover
    return ""
