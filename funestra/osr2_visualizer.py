"""The OSR2 visualizer itself — the motion being sent, drawn.

Each axis is one object: its controls, its bar and its number together.  Center
sits down the left — its number, then a −/+ pair beside the dotted line it moves.
Amplitude sits down the right — a −/+ pair at the ends of its bar, then its
number.  Speed sits under the trace, out of the way of the other two.

Origenerator floats this over its slideshows: the painter is shared and the
toolkit is not — a caller with no Pillow surface of its own renders this into
one (:class:`funestra.hud.Hud`) and blits the result, so a second
app shows this drawing instead of its own idea of it.

It is a block, not a HUD: it hosts inside whatever slab is showing it rather
than carrying one of its own, so a Main Funestra's HUD is one HUD and not two stacked.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw
from shared_ui.palette import (
    BG_BUTTON,
    BLUE,
    BORDER_DEFAULT,
    BORDER_SUBTLE,
    GREEN,
    MAGENTA,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WHITE,
)
from shared_ui.spacing import BUTTON_RADIUS_HUD, GAP_MEDIUM
from shared_ui.type_scale import SIZE_TINY

from . import drive_layout
from .drive_layout import (
    MAX_INTENSITY,
    TRACE_SAMPLES,  # noqa: F401 — re-exported: genau reads it from here
    DriveControl,
    DriveTrack,
    section_size,  # noqa: F401 — re-exported: the Main Funestra's HUD painter reads it here
    track_value,
)
from .drive_layout import fraction as _fraction
from .file_channel import publish_whole
from .geometry import Rect, contains
from .hud import (
    draw_icon,
    load_font,
    text_width,
)
from .hud_button import Button
from .robot_hand import FULL_INTENSITY, POSITION_MAX, amplitude_ceiling, speed_ceiling

DRIVEN_BY_ROBOT_HAND = "robot_hand"
DRIVEN_BY_FUNSCRIPT = "funscript"
DRIVEN_BY_AUTO = "auto"
DRIVEN_BY_NEUTRAL = "neutral"
DRIVEN_BY_NOTHING = "nothing"

_TRACE_INK = {
    DRIVEN_BY_ROBOT_HAND: BLUE,
    DRIVEN_BY_FUNSCRIPT: GREEN,
    DRIVEN_BY_AUTO: MAGENTA,
    DRIVEN_BY_NEUTRAL: BORDER_DEFAULT,
    DRIVEN_BY_NOTHING: TEXT_MUTED,
}


_TRACK = BG_BUTTON

_LABEL_H = drive_layout.LABEL_H
_CTRL = drive_layout.CONTROL_SIZE
_GAP = drive_layout.GAP
_KEY_GAP = GAP_MEDIUM
_ETCH_PITCH = 4

DISABLED_INK = (*BORDER_SUBTLE, 255)

# The trace is drawn this many times larger and scaled back down, which is what
# smooths it: Pillow's line has no antialiasing of its own, so drawn at HUD
# size every segment was a hard-edged pixel staircase, and a wave at low
# amplitude — a few pixel rows tall — scrolled as chunks.  Supersampled, the
# edges come back as intensity ramps and positions land on quarter-pixels, so
# the line reads as a curve and slides instead of stepping.  The block is 120×96;
# sixteen times the pixels is still far under a millisecond a repaint.
_SUPERSAMPLE = 4


def trace_ink(driven: str):
    return _TRACE_INK[driven]


def label_pair_x(font, key: str, *, left: int) -> tuple[int, int]:
    return left, left + text_width(font, key) + _KEY_GAP


@dataclass(frozen=True)
class DriveHud:
    speed: int = 0
    amplitude: int = 0
    center: int = 0
    shape: str = "sine"
    position: int = 0
    advance_interval: int = 0
    driven: str = DRIVEN_BY_ROBOT_HAND
    trace_seconds: float = 12.0
    spd_at_max: bool = False
    spd_at_min: bool = False
    amp_at_max: bool = False
    amp_at_min: bool = False
    ctr_at_max: bool = False
    ctr_at_min: bool = False
    waveform: tuple[float, ...] = ()
    segments: tuple[tuple[int, str], ...] = ()
    slide: float = 0.0
    edge: float | None = None
    let_go: float | None = None
    max_intensity: int = FULL_INTENSITY

    @property
    def driving(self) -> bool:
        return self.driven == DRIVEN_BY_ROBOT_HAND

    @property
    def live(self) -> bool:
        return self.driven != DRIVEN_BY_NOTHING

    @property
    def runs(self) -> tuple[tuple[int, int, str], ...]:
        marks = self.segments or ((0, self.driven),)
        ends = [start for start, _who in marks[1:]] + [len(self.waveform) - 1]
        return tuple((start, end, who) for (start, who), end in zip(marks, ends, strict=True))


def controls(x: int, y: int, hud: DriveHud) -> list[DriveControl]:
    return drive_layout.controls(
        x, y, hud.center,
        drive_layout.Limits(
            spd_at_min=hud.spd_at_min, spd_at_max=hud.spd_at_max,
            amp_at_min=hud.amp_at_min, amp_at_max=hud.amp_at_max,
            ctr_at_min=hud.ctr_at_min, ctr_at_max=hud.ctr_at_max,
        ),
        dim=not hud.driving)


def tracks(x: int, y: int, hud: DriveHud) -> list[DriveTrack]:
    return drive_layout.tracks(
        x, y, hud.center, dim=not hud.driving,
        amplitude_ceiling=amplitude_ceiling(hud.max_intensity, hud.speed),
        speed_ceiling=speed_ceiling(hud.max_intensity, hud.amplitude))


def track_command(track: DriveTrack, px: int, py: float) -> str:
    owner = "" if track.axis == MAX_INTENSITY else "robot_hand_"
    return f"{owner}{track.axis}_{track_value(track, px, py)}"


CONTROL_TIPS = {
    "robot_hand_speed_down": "Motion slower", "robot_hand_speed_up": "Motion faster",
    "robot_hand_amplitude_up": "Amplitude up", "robot_hand_amplitude_down": "Amplitude down",
    "robot_hand_center_up": "Center up", "robot_hand_center_down": "Center down",
}


def visualizer_targets(x: int, y: int, hud: DriveHud,
                    ) -> tuple[list[tuple[Rect, Button]], list[DriveTrack]]:
    grabbable = [*tracks(x, y, hud),
                 drive_layout.center_handle(x, y, hud.center, dim=not hud.driving)]
    targets = [
        (control.rect,
         Button(control.command, "", CONTROL_TIPS.get(control.command, ""),
                dim=control.dim))
        for control in controls(x, y, hud)
    ]
    targets += [(part.rect, Button("", "", part.tooltip)) for part in grabbable]
    return targets, grabbable


class TrackGrip:
    def __init__(self) -> None:
        self._held: DriveTrack | None = None
        self._offset = 0.0
        self._asked = ""

    @property
    def holding(self) -> bool:
        return self._held is not None

    def grab(self, bars: list[DriveTrack], px: int, py: int) -> str:
        for track in bars:
            if not track.dim and contains(track.rect, px, py):
                self._held, self._offset = drive_layout.held_bar(track, py)
                self._asked = self._command_at(px, py)
                return "" if track.handle_of else self._asked
        return ""

    def drag_to(self, px: int, py: int) -> str:
        if self._held is None:
            return ""
        command = self._command_at(px, py)
        if command == self._asked:
            return ""
        self._asked = command
        return command

    def release(self) -> None:
        self._held, self._offset, self._asked = None, 0.0, ""

    def _command_at(self, px: int, py: int) -> str:
        return track_command(self._held, px, py - self._offset)


def draw_level_bar(draw, rect: Rect, *, fill: float, color) -> None:
    x, y, w, h = rect
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=(*_TRACK, 255))
    filled = max(1, round(fill * w))
    draw.rectangle([x, y, x + filled - 1, y + h - 1], fill=color)


class DriveSection:
    def __init__(self) -> None:
        self._tiny = load_font(SIZE_TINY)

    def draw(self, image: Image.Image, x: int, y: int, hud: DriveHud) -> None:
        draw = ImageDraw.Draw(image)
        g = drive_layout.geometry(x, y, _fraction(hud.center))
        level_ink = (*BLUE, 255) if hud.driving else DISABLED_INK
        value_ink = (*TEXT_PRIMARY, 255) if hud.driving else DISABLED_INK

        self._wave(image, g.wave, hud)
        self._amp_bar(draw, g.amp_bar, hud, color=level_ink)
        draw_level_bar(draw, g.speed_bar, fill=_fraction(hud.speed), color=level_ink)
        self._etch_what_the_max_intensity_rules_out(draw, g, hud)
        for control in controls(x, y, hud):
            self._draw_control(image, draw, control)

        self._stacked(draw, g.center_label, "Center", str(hud.center),
                      anchor="rm", ink=value_ink)
        self._stacked(draw, g.amp_label, "Amp", str(hud.amplitude),
                      anchor="lm", ink=value_ink)
        self._value(draw, g.speed_label_y, "Speed", str(hud.speed),
                    center=g.speed_label_x, ink=value_ink)

    @staticmethod
    def _draw_control(image: Image.Image, draw, control: DriveControl) -> None:
        x, y, w, h = control.rect
        ink = DISABLED_INK if control.dim else (*TEXT_PRIMARY, 255)
        draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=BUTTON_RADIUS_HUD,
                               outline=ink, width=1)
        draw_icon(image, control.mark, control.rect, ink)

    def _stacked(self, draw, rect: Rect, key: str, value: str, *, anchor: str, ink) -> None:
        x, y, w, h = rect
        text_x = x + w if anchor.startswith("r") else x
        for text, middle, fill in ((key, y + _CTRL / 2, (*TEXT_MUTED, 255)),
                                   (value, y + h - _CTRL / 2, ink)):
            draw.text((text_x, middle), text, font=self._tiny, anchor=anchor, fill=fill)

    def _value(self, draw, y: int, key: str, value: str, *,
               center: int, ink=(*TEXT_PRIMARY, 255)) -> None:
        span = text_width(self._tiny, key) + _KEY_GAP + text_width(self._tiny, value)
        key_x, value_x = label_pair_x(self._tiny, key, left=center - span // 2)
        draw.text((key_x, y + _LABEL_H / 2), key, font=self._tiny, anchor="lm",
                  fill=(*TEXT_MUTED, 255))
        draw.text((value_x, y + _LABEL_H / 2), value, font=self._tiny, anchor="lm",
                  fill=ink)

    def _etch_what_the_max_intensity_rules_out(self, draw, g: drive_layout.Geometry,
                                               hud: DriveHud) -> None:
        ink = (*RED, 255) if hud.driving else DISABLED_INK
        sx, sy, sw, sh = g.speed_bar
        fastest = _fraction(speed_ceiling(hud.max_intensity, hud.amplitude))
        self._etch(draw, (sx + round(fastest * sw), sy, sx + sw, sy + sh), ink)
        ax, ay, aw, ah = g.amp_bar
        widest = amplitude_ceiling(hud.max_intensity, hud.speed)
        center_at_the_widest = max(widest / 2, min(100 - widest / 2, hud.center))
        reach = round(_fraction(widest) * ah)
        top = ay + round((1 - _fraction(center_at_the_widest)) * ah - reach / 2)
        self._etch(draw, (ax, ay, ax + aw, max(ay, top)), ink)
        self._etch(draw, (ax, min(ay + ah, top + reach), ax + aw, ay + ah), ink)

    @staticmethod
    def _etch(draw, box: tuple[int, int, int, int], ink) -> None:
        x0, y0, x1, y1 = box
        width, height = x1 - x0, y1 - y0
        for k in range(0, width + height - 1, _ETCH_PITCH):
            first, last = max(0, k - (width - 1)), min(height - 1, k)
            if first <= last:
                draw.line([(x0 + k - first, y0 + first), (x0 + k - last, y0 + last)],
                          fill=ink, width=1)

    def _wave(self, image: Image.Image, rect: Rect, hud: DriveHud) -> None:
        x, y, w, h = rect
        s = _SUPERSAMPLE
        block = Image.new("RGBA", (w * s, h * s))
        draw = ImageDraw.Draw(block)
        draw.rectangle([0, 0, w * s - 1, h * s - 1], fill=(*_TRACK, 255),
                       outline=(*TEXT_MUTED, 255), width=s)
        if hud.driving:
            center_y = round((1 - _fraction(hud.center)) * (h * s - 1))
            for dash in range(0, w * s, 6 * s):
                draw.line([(dash, center_y), (min(dash + 3 * s, w * s - 1), center_y)],
                          fill=(*WHITE, 150), width=s)
        points = hud.waveform
        if len(points) > 1:
            pitch = (w * s - 1) / (len(points) - 1)

            def at(index: float, value: float, shift: float) -> tuple[int, int]:
                # Shifted left by the leftover knot fraction: the values never
                # change between knots, so this shift is what slides the stable
                # shape (PIL clips what leaves the block).
                return (round((index - shift) * pitch),
                        round((1 - value) * (h * s - 1)))

            runs = hud.runs
            for run_no, (start, end, driven) in enumerate(runs):
                pts = [at(i, points[i], hud.slide) for i in range(start, end + 1)]
                if run_no == len(runs) - 1 and hud.edge is not None:
                    pts.append(at(len(points), hud.edge, hud.slide))
                if len(pts) > 1:
                    draw.line(pts, fill=(*trace_ink(driven), 255), width=2 * s,
                              joint="curve")
        image.alpha_composite(block.resize((w, h), Image.LANCZOS), (x, y))
        dot_y = y + round((1 - hud.position / POSITION_MAX) * (h - 1))
        dot_ink = TEXT_PRIMARY if hud.live else TEXT_MUTED
        dot = Image.new("RGBA", (7 * s, 7 * s))
        ImageDraw.Draw(dot).ellipse([0, 0, 7 * s - 1, 7 * s - 1], fill=(*dot_ink, 255))
        image.alpha_composite(dot.resize((7, 7), Image.LANCZOS), (x - 3, dot_y - 3))

    @staticmethod
    def _amp_bar(draw, rect: Rect, hud: DriveHud, *, color=(*BLUE, 255)) -> None:
        x, y, w, h = rect
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=(*_TRACK, 255))
        bar_h = max(2, round(_fraction(hud.amplitude) * h))
        top = y + round((1 - _fraction(hud.center)) * h - bar_h / 2)
        top = max(y, min(y + h - bar_h, top))
        draw.rectangle([x, top, x + w - 1, top + bar_h - 1], fill=color)


_SCALARS = ("speed", "amplitude", "center", "position", "advance_interval")
_FLAGS = ("spd_at_max", "spd_at_min", "amp_at_max", "amp_at_min",
          "ctr_at_max", "ctr_at_min")


def drive_text(hud: DriveHud) -> str:
    lines = [f"{name}={getattr(hud, name)}" for name in _SCALARS]
    lines += [f"{name}={'1' if getattr(hud, name) else '0'}" for name in _FLAGS]
    lines.append(f"shape={hud.shape}")
    lines.append(f"trace_seconds={hud.trace_seconds:.3f}")
    if hud.let_go is not None:
        lines.append(f"let_go={hud.let_go:.3f}")
    lines.append(f"slide={hud.slide:.3f}")
    if hud.edge is not None:
        lines.append(f"edge={hud.edge:.3f}")
    lines.append(f"max_intensity={hud.max_intensity}")
    lines.append(f"driven={hud.driven}")
    lines.append("segments=" + ",".join(f"{start}:{who}" for start, who in hud.segments))
    lines.append("waveform=" + ",".join(f"{value:.3f}" for value in hud.waveform))
    return "\n".join(lines) + "\n"


def publish_drive(path: Path, hud: DriveHud) -> bool:
    return publish_whole(path, drive_text(hud))


PUBLISH_INTERVAL_S = 0.04


class DrivePublisher:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._last: float | None = None

    def publish(self, hud: DriveHud, now: float) -> None:
        if self._last is not None and now - self._last < PUBLISH_INTERVAL_S:
            return
        self._last = now
        publish_drive(self._path, hud)


def read_drive(path: Path) -> DriveHud | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    if not values.keys() >= {*_SCALARS, *_FLAGS, "shape"}:
        return None
    try:
        scalars = {name: int(values[name]) for name in _SCALARS}
    except ValueError:
        return None
    return DriveHud(
        **scalars,
        **{name: values[name].strip() == "1" for name in _FLAGS},
        shape=values["shape"].strip(),
        trace_seconds=_seconds(values.get("trace_seconds", "")),
        waveform=_waveform(values.get("waveform", "")),
        let_go=_let_go(values.get("let_go")),
        slide=_let_go(values.get("slide")) or 0.0,
        edge=_let_go(values.get("edge")),
        max_intensity=_max_intensity(values.get("max_intensity", "")),
        driven=values.get("driven", DriveHud.driven).strip(),
        segments=_segments(values.get("segments", "")),
    )


def _let_go(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _seconds(raw: str) -> float:
    try:
        return float(raw)
    except ValueError:
        return DriveHud.trace_seconds


def _max_intensity(raw: str) -> int:
    return int(raw) if raw.strip().isdigit() else DriveHud.max_intensity


def _waveform(raw: str) -> tuple[float, ...]:
    try:
        return tuple(float(value) for value in raw.split(",") if value)
    except ValueError:
        return ()


def _segments(raw: str) -> tuple[tuple[int, str], ...]:
    try:
        return tuple((int(start), who) for start, who in
                     (stretch.split(":", 1) for stretch in raw.strip().split(",") if stretch))
    except ValueError:
        return ()
