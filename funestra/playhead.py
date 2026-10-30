"""The readout at the left end of every Funestra's timeline row: where the video is, and how long it runs."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw
from shared_ui.palette import TEXT_PRIMARY
from shared_ui.type_scale import SIZE_TINY

from .hud import KeptBitmap, ink_center_offset, load_font, text_width
from .hud_title import SEPARATOR
from .volume import CHIP_H

FIGURE_SPACE = "\u2007"


@dataclass(frozen=True)
class PlayheadHud:
    text: str
    widest: str


def _clock(ms: float, length_ms: float) -> str:
    length_s = int(length_ms // 1000)
    minutes, seconds = divmod(int(ms // 1000), 60)
    if length_s < 3600:
        return f"{minutes:0{len(str(length_s // 60))}d}:{seconds:02d}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours:0{len(str(length_s // 3600))}d}:{minutes:02d}:{seconds:02d}"


def _time(position_ms: float, duration_ms: float) -> str:
    return f"{_clock(position_ms, duration_ms)} / {_clock(duration_ms, duration_ms)}"


def _frame_of(frame: int, total: int) -> str:
    return f"frame {str(frame).rjust(len(str(total)), FIGURE_SPACE)} / {total}"


def _framed(frame: int, total: int, position_ms: float, duration_ms: float) -> str:
    return f"{_frame_of(frame, total)}{SEPARATOR}{_time(position_ms, duration_ms)}"


def framed_playhead(frame: int, total: int, position_ms: float,
                    duration_ms: float) -> PlayheadHud:
    """A frame of how many, then the time, which a video's row and a flick's
    both read."""
    return PlayheadHud(text=_framed(frame, total, position_ms, duration_ms),
                       widest=_framed(total, total, duration_ms, duration_ms))


def time_playhead(position_ms: float, duration_ms: float) -> PlayheadHud | None:
    if duration_ms <= 0:
        return None
    return PlayheadHud(text=_time(position_ms, duration_ms),
                       widest=_time(duration_ms, duration_ms))


def video_playhead(position_ms: float, duration_ms: float, frame_rate: float) -> PlayheadHud | None:
    if duration_ms <= 0 or frame_rate <= 0:
        return time_playhead(position_ms, duration_ms)
    return framed_playhead(round(position_ms / 1000 * frame_rate),
                           round(duration_ms / 1000 * frame_rate), position_ms, duration_ms)


def flick_playhead(frame: int, frame_count: int) -> PlayheadHud | None:
    if frame_count <= 0:
        return None
    return PlayheadHud(text=_frame_of(frame, frame_count),
                       widest=_frame_of(frame_count, frame_count))


@cache
def _font():
    return load_font(SIZE_TINY)


def readout_width(hud: PlayheadHud) -> int:
    """The room the readout takes on the row: its widest words' worth."""
    return text_width(_font(), hud.widest)


class PlayheadHudPainter(KeptBitmap):
    """The words alone, as tall as the chip and centered on the digits' ink."""

    def __init__(self) -> None:
        super().__init__()
        self._top = (CHIP_H - 1) / 2 - ink_center_offset(_font(), "0")[1]

    def _paint(self, hud: PlayheadHud) -> Image.Image:
        image = Image.new("RGBA", (readout_width(hud), CHIP_H), (0, 0, 0, 0))
        ImageDraw.Draw(image).text((0, self._top), hud.text, font=_font(),
                                   fill=(*TEXT_PRIMARY, 255))
        return image
