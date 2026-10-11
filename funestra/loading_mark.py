"""What a Funestra shows where its video will be, while the video is opening."""
from __future__ import annotations

from PIL import Image
from shared_ui.palette import TEXT_PRIMARY

from .hud_panel import KeptBitmap, load_font, pill, px, text_width

__all__: list[str] = []

WORD = "Loading…"
_TEXT_PT = 11
_PAD_X = 16
_PAD_Y = 9


def loading_mark(duration_ms: float) -> str:
    """The word to show over a Funestra with no video up yet, or "" once it has one.

    mpv has the length the moment the file is open, and nothing before that, so
    a length is the first thing that says the wait is over.
    """
    return "" if duration_ms > 0 else WORD


class LoadingMarkPainter(KeptBitmap):
    def _paint(self, word: str) -> Image.Image:
        font = load_font(_TEXT_PT)
        width = text_width(font, word) + 2 * _PAD_X
        height = px(_TEXT_PT) + 2 * _PAD_Y
        image, draw = pill(width, height)
        draw.text((width / 2, height / 2), word, font=font,
                  fill=(*TEXT_PRIMARY, 255), anchor="mm")
        return image


def loading_xy(mark_w: int, mark_h: int, *, win_w: int, win_h: int) -> tuple[int, int]:
    return (win_w - mark_w) // 2, (win_h - mark_h) // 2
