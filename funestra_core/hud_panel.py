"""The chrome the Funestras' in-video HUDs are drawn on.

Every Funestra in this family paints its HUD into the video as a BGRA bitmap mpv
composites, rather than into a window of its own: an mpv overlay has no z-order,
so it can neither fall beneath the video nor float above the desktop.

What the HUDs share is the look, not the contents: a rounded translucent slab,
the Segoe UI face sized the way Qt sized it, and the RGBA -> BGRA hand-off mpv
wants.  What each one *says* is its own business — the satellite draws a map of
clips, the Main Funestra's console a couple of mode lines — so this owns the chrome and stops there.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shared_ui.icons_pil import paste_glyph

# The palette is shared_ui's, read without Qt: shared_ui.palette imports
# nothing, and these HUDs are Pillow.  Every HUD painter reads it there too,
# so a Funestra reaching for its own blue has the family's to reach for.
from shared_ui.palette import (
    AMBER,
    BG_BUTTON,
    BG_BUTTON_ACTIVE,
    BG_PRIMARY,
    BLUE,
    BORDER_PANEL,
    GREEN,
    MAGENTA,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WHITE,
    hovered,
)
from shared_ui.spacing import BUTTON_MARK_INSET

from .hud_marks import APP_MARK, MINIMIZE_ICON, SHARED_MARK, app_mark_letter, shared_mark_name

__all__ = [
    "SYMBOL_FONT",
    "draw_button",
    "fit_text",
    "load_font",
    "text_width",
]

# Segoe UI Bold — every label on these HUDs is bold, because they are read at a
# glance over moving video.  A caller wanting another face passes its filename.
UI_FONT = "segoeuib.ttf"

# Segoe UI Symbol, for the marks these HUDs type rather than draw.  Segoe UI Bold
# carries none of them, and Pillow draws a ".notdef" tofu for a codepoint a face
# lacks, where Qt falls back silently — so anything typed names this face.
SYMBOL_FONT = "seguisym.ttf"

# Translucent enough to read the video through, opaque enough to read the text.
PANEL_ALPHA = 224
CORNER_RADIUS = 8

# The family's own hover step, re-exported under the name this package's
# painters already call it.
hovered_fill = hovered


def px(points: int) -> int:
    """A Qt point size as pixels, at the standard 96 dpi Windows reports.

    These HUDs were laid out in Qt, which sizes type in points; Pillow sizes it
    in pixels, so every point size crosses this on its way to a font.
    """
    return round(points * 4 / 3)


def load_font(points: int, family: str = UI_FONT) -> ImageFont.FreeTypeFont:
    """*family* at *points*, or Pillow's own face when the machine lacks it.

    The HUD is redrawn while the video plays, so a missing face has to degrade to
    an ugly panel rather than raise into the run loop.
    """
    try:
        return ImageFont.truetype(family, px(points))
    except OSError:
        return ImageFont.load_default(px(points))


def text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    """How wide *text* draws in *font* — what a panel sizes itself against."""
    return int(font.getlength(text))


ELLIPSIS = "…"


def fit_text(font: ImageFont.FreeTypeFont, text: str, max_width: int) -> str:
    """*text* if it draws inside *max_width*, else as much of its head as does
    with an ellipsis after it — "" when not even the ellipsis fits."""
    if text_width(font, text) <= max_width:
        return text
    fits, over = 0, len(text)  # the longest head known to fit; the shortest known not to
    while over - fits > 1:
        cut = (fits + over) // 2
        if text_width(font, text[:cut].rstrip() + ELLIPSIS) <= max_width:
            fits = cut
        else:
            over = cut
    head = text[:fits].rstrip() + ELLIPSIS
    return head if text_width(font, head) <= max_width else ""


# Where each glyph's ink sits relative to the origin ``draw.text`` draws from,
# measured once per face+size+glyph.  A HUD uses a dozen glyphs and repaints them
# for the life of the session, so the probe below runs a handful of times.
_INK_OFFSETS: dict[tuple[str, int, str], tuple[float, float] | None] = {}


def ink_center_offset(font: ImageFont.FreeTypeFont, glyph: str) -> tuple[float, float] | None:
    """The centre of *glyph*'s ink, offset from where ``draw.text`` starts it.

    Measured by drawing it, because nothing reported is the ink bounds:
    ``textbbox`` gives the layout bounds, whose lower edge is the face's descender line
    however short the glyph — a minus sign reports nine pixels of empty space
    under it.  None when the glyph leaves no ink at all.
    """
    key = (str(getattr(font, "path", "")), int(getattr(font, "size", 0)), glyph)
    if key not in _INK_OFFSETS:
        pad = 8
        bounds = font.getbbox(glyph)
        probe = Image.new("L", (int(bounds[2]) + 2 * pad, int(bounds[3]) + 2 * pad), 0)
        ImageDraw.Draw(probe).text((pad, pad), glyph, font=font, fill=255)
        ink = probe.getbbox()
        _INK_OFFSETS[key] = None if ink is None else (
            (ink[0] + ink[2] - 1) / 2 - pad, (ink[1] + ink[3] - 1) / 2 - pad,
        )
    return _INK_OFFSETS[key]


def draw_glyph(draw: ImageDraw.ImageDraw, cx: float, cy: float, glyph: str,
               font: ImageFont.FreeTypeFont, fill) -> None:
    """Draw *glyph* centered on its own ink at ``(cx, cy)``.

    Pillow's ``anchor="mm"`` centers the font's ascent/descent bounds, not the mark
    inside it — and on the symbol faces these HUDs use, the mark sits high in
    bounds that run down to the descender.  Every icon button was therefore drawing
    its glyph two to six pixels low.  Centering the ink puts it where the eye
    expects it, whatever the glyph.
    """
    offset = ink_center_offset(font, glyph)
    if offset is None:
        return
    draw.text((cx - offset[0], cy - offset[1]), glyph, font=font, fill=fill)


def draw_mark(image: Image.Image, name: str, rect: tuple[int, int, int, int],
              fill) -> None:
    """One of the family's marks, centered in *rect*.

    The same drawing the apps' Qt chrome paints -- shared_ui holds the geometry
    and each side renders it -- so a trash can on a HUD is the trash can on
    Origenerator's toolbar rather than whatever character a symbol font had.

    Takes the panel's IMAGE rather than its pen, the way the drive readout does:
    the mark is supersampled and composited back, which a pen cannot carry.
    """
    x, y, w, h = rect
    paste_glyph(image, name,
                (x + BUTTON_MARK_INSET, y + BUTTON_MARK_INSET, w - 2 * BUTTON_MARK_INSET,
                 h - 2 * BUTTON_MARK_INSET),
                fill)


# The dot at the head of every HUD's status line, saying whether a bare, unaddressed
# command lands on this Funestra.  Same size and same corner on all three, because a
# reader glancing across two screens is looking for one mark in one place.
ACTIVE_DOT = 10


def draw_active_dot(draw: ImageDraw.ImageDraw, x: int, y: int, active: bool) -> None:
    """The active-Funestra dot, its top-left at ``(x, y)``.

    White while a bare command would land on this Funestra, the palette's gray
    otherwise — and always drawn, never hidden.  An absent dot and an idle dot look
    the same, and then only the Funestra that *has* the floor says anything, which is
    half an answer to a question asked of the room.
    """
    draw.ellipse([x, y, x + ACTIVE_DOT, y + ACTIVE_DOT],
                 fill=(*(WHITE if active else TEXT_MUTED), 255))


# The app marks, cell by cell.  Every icon in this family is a magenta letter laid
# out on a five-by-five grid — the shape each app's own .ico carries — and a HUD
# that wants one draws it from the grid rather than loading the file: the .ico
# files live in the apps' own repos, and no app here may reach into another's.
# A letter set in the body face is not the same mark: it is a thin letterform
# where the icon is a chunky one, and it reads as a caption rather than a badge.
ICON_GRIDS = {
    "B": ("#####", "#...#", "#####", "#...#", "#####"),  # the OSR2 broker
    "F": ("#####", "#....", "#####", "#....", "#...."),  # F-mode
}


def draw_icon(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int],
              letter: str) -> None:
    """Draw the app mark for *letter*, centered in *rect* and sized to fill it.

    The grid's blank cells are left alone rather than painted, so whatever is
    beneath shows through the letter's counters — exactly as the .ico's own
    transparent cells let the panel under it through.
    """
    x, y, w, h = rect
    cell = max(1, min(w, h) // 7)
    left, top = x + (w - 5 * cell) / 2, y + (h - 5 * cell) / 2
    for row, line in enumerate(ICON_GRIDS[letter]):
        for column, painted in enumerate(line):
            if painted != "#":
                continue
            cx, cy = left + column * cell, top + row * cell
            draw.rectangle([cx, cy, cx + cell - 1, cy + cell - 1], fill=(*MAGENTA, 255))


TOOLTIP_PAD = 5
TOOLTIP_RADIUS = 4
TOOLTIP_ALPHA = 240
_TOOLTIP_EDGE = 2           # the gap it keeps from the panel's own edge
_TOOLTIP_OFFSET = (14, 16)  # right of and below the cursor, clear of the pointer


def _wrap(font: ImageFont.FreeTypeFont, text: str, available: int) -> list[str]:
    return [line for paragraph in text.split("\n")
            for line in _wrap_paragraph(font, paragraph, available)]


def _wrap_paragraph(font: ImageFont.FreeTypeFont, paragraph: str,
                    available: int) -> list[str]:
    """*paragraph* broken on spaces into lines of at most *available* px.

    A word wider than *available* keeps its own line and overhangs — breaking
    mid-word would read as two words, and nothing named on these HUDs has one
    that long.
    """
    lines: list[str] = []
    for word in paragraph.split():
        if lines and text_width(font, f"{lines[-1]} {word}") <= available:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def draw_tooltip(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str,
                 pos: tuple[int, int], bounds: tuple[int, int]) -> tuple[int, int, int, int]:
    """Name a control in a tooltip near *pos*, inside a panel *bounds* big, and
    return the rect it drew.

    These HUDs are painted into the video, so there is no native tooltip to fall
    back on and every glyph on them is cryptic on purpose — this tooltip *is* how a
    control says what it is.  Being part of the panel's own bitmap is also why it
    wraps rather than running on: whatever crosses the slab's edge is never drawn,
    so an over-wide tooltip loses its tail with nothing to say it had one.  It
    is then nudged back inside the slab, so a control near an edge names itself
    inward instead of off it.
    """
    room = max(1, bounds[0] - 2 * (_TOOLTIP_EDGE + TOOLTIP_PAD))
    lines = _wrap(font, text, room)
    if not lines:
        return (0, 0, 0, 0)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    w = max(text_width(font, line) for line in lines) + 2 * TOOLTIP_PAD
    h = line_h * len(lines) + 2 * TOOLTIP_PAD
    x = max(_TOOLTIP_EDGE, min(pos[0] + _TOOLTIP_OFFSET[0], bounds[0] - w - _TOOLTIP_EDGE))
    y = max(_TOOLTIP_EDGE, min(pos[1] + _TOOLTIP_OFFSET[1], bounds[1] - h - _TOOLTIP_EDGE))
    draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=TOOLTIP_RADIUS,
                           fill=(*BG_PRIMARY, TOOLTIP_ALPHA),
                           outline=(*BORDER_PANEL, 255), width=1)
    for index, line in enumerate(lines):
        draw.text((x + w / 2, y + TOOLTIP_PAD + index * line_h + ascent), line,
                  font=font, anchor="ms", fill=(*TEXT_PRIMARY, 255))
    return (x, y, w, h)


def to_bgra(image: Image.Image) -> np.ndarray:
    """An RGBA Pillow image as the contiguous BGRA array mpv's overlays take."""
    rgba = np.asarray(image, dtype=np.uint8)
    return np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]], dtype=np.uint8)


class HudPanel:
    """A rounded translucent slab to draw a HUD onto, and hand to mpv.

    Callers draw through :attr:`draw` and :attr:`image` — the panel is a surface,
    not a layout — and finish with :meth:`to_bgra`.

    *ground* is the grey the slab is made of.  It defaults to the canvas colour,
    which is right where the panel floats over a video: the picture beneath it is
    what it reads against, and a HUD the colour of a dark frame still reads as a
    panel over one.  A host that draws this on its own chrome instead has no
    picture beneath it, and on a window painted that very grey the slab vanishes
    and leaves its one-pixel border outlining nothing — so it says which grey it
    wants, and gets a panel that sits on that window the way the window's own
    panels do.
    """

    def __init__(self, width: int, height: int, *,
                 ground: tuple[int, int, int] = BG_PRIMARY) -> None:
        self.image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.draw.rounded_rectangle(
            [0, 0, width - 1, height - 1], radius=CORNER_RADIUS,
            fill=(*ground, PANEL_ALPHA), outline=(*BORDER_PANEL, 255), width=1,
        )

    def divide(self, y: int) -> None:
        self.draw.line([(0, y), (self.image.width - 1, y)], fill=(*BORDER_PANEL, 255))

    def to_bgra(self) -> np.ndarray:
        return to_bgra(self.image)


PILL_ALPHA = 200


def pill(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=height // 2,
                           fill=(*BG_PRIMARY, PILL_ALPHA), outline=(*BORDER_PANEL, 255), width=1)
    return image, draw


class KeptBitmap:
    """A painting kept until what it shows changes, handed out in both shapes the
    Funestras take: a BGRA array for mpv's overlays, RGBA bytes for a pygame blit."""

    def __init__(self) -> None:
        self._painted = None
        self._image: Image.Image | None = None
        self._bgra: np.ndarray | None = None

    def bgra(self, hud) -> np.ndarray:
        if self._ensure(hud) or self._bgra is None:
            self._bgra = to_bgra(self._image)
        return self._bgra

    def rgba(self, hud) -> tuple[bytes, tuple[int, int]]:
        self._ensure(hud)
        return self._image.tobytes(), self._image.size

    def _ensure(self, hud) -> bool:
        if hud == self._painted and self._image is not None:
            return False
        self._painted, self._image = hud, self._paint(hud)
        return True

    def _paint(self, hud) -> Image.Image:
        raise NotImplementedError


# The family's button: its ground, and its face drawn on it.
BUTTON_RADIUS = 3
# The minimize bar: as wide as the satellite HUD's filter funnel, so the two
# drawn marks are built to one size, and two pixels deep like a title bar's.
_MINIMIZE_W = 9
_MINIMIZE_H = 2


def button_ground(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], fill,
                  *, hovered: bool = False, dim: bool = False,
                  rest_ink=None) -> tuple[int, int, int, int]:
    """The square a HUD control sits on, filled *fill*, and the ink for its mark.

    The edge is the chrome's muted gray over either gray ground and the fill's
    own color over a colored one, chosen before the hover step lightens the
    fill so hovering never changes the outline.  A dim control is never
    lightened: it cannot be pressed, and lighting it would promise otherwise.

    A mark reverses out of a light fill only (white, amber); over either gray
    ground it keeps *rest_ink* or the chrome's own, muted while dim; over a
    colored ground it is white.
    """
    x, y, w, h = rect
    edge = TEXT_MUTED if (dim or fill in (BG_BUTTON, BG_BUTTON_ACTIVE)) else fill
    if hovered and not dim:
        fill = hovered_fill(fill)
    draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=BUTTON_RADIUS,
                           fill=(*fill, 255), outline=(*edge, 255), width=1)
    if fill in (WHITE, AMBER):
        return (*BG_PRIMARY, 255)
    if fill in (BG_BUTTON, BG_BUTTON_ACTIVE):
        return (*(TEXT_MUTED if dim else rest_ink or TEXT_PRIMARY), 255)
    return (*WHITE, 255)


def draw_minimize_bar(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int],
                      ink) -> None:
    """The bar a Windows title bar puts on its minimize button, two pixels deep
    across the middle: drawn, because the mark Windows uses is in a face these
    HUDs do not load and Pillow draws tofu for a codepoint a face lacks."""
    x, y, w, h = rect
    cx, top = x + w / 2, y + h / 2 - _MINIMIZE_H / 2
    draw.rectangle([cx - _MINIMIZE_W / 2, top, cx + _MINIMIZE_W / 2, top + _MINIMIZE_H - 1],
                   fill=ink)


def draw_button(image: Image.Image, draw: ImageDraw.ImageDraw,
                rect: tuple[int, int, int, int], button, *, hovered: bool,
                glyph_font: ImageFont.FreeTypeFont,
                word_font: ImageFont.FreeTypeFont,
                row_label: bool = False) -> None:
    """One declared control (:class:`funestra_core.hud_button.Button`), in the
    one shape every HUD here draws: on the family's button ground at rest,
    filled while lit -- green for a favorites control, amber for an enhanced
    one, the family's blue for the rest; red for a live recording, blue for the
    loop it leaves running, the active gray for a choice held but not applied
    -- with its face drawn on top: an app mark, one of the family's marks, the
    minimize bar, a typed glyph out of *glyph_font*, or a word in *word_font*.

    An item with nothing to post is a READ-OUT, not a control: bare text with no
    button under it, in the readout's own key/value colors -- a muted word names
    the value beside it, which is bright.  Drawn as a button it invites a press
    that does nothing, which is what "Clip seconds" looked like on the one panel
    a show wears.  *row_label* is a read-out at the panel's left edge, naming
    its row: left aligned on the family's tight button pad, so it lines up with
    the rows that open with a button whose mark is inset rather than sitting
    hard against the edge beside them.
    """
    x, y, w, h = rect
    if not button.command:
        ink = TEXT_MUTED if button.glyph.replace(" ", "").isalpha() else TEXT_PRIMARY
        if row_label:
            draw.text((x, y + h / 2), button.glyph, font=word_font, anchor="lm",
                      fill=(*ink, 255))
        else:
            draw.text((x + w / 2, y + h / 2), button.glyph, font=word_font,
                      anchor="mm", fill=(*ink, 255))
        return

    lit = GREEN if button.favorite else AMBER if button.enhanced else BLUE
    fill = (lit if button.lit else RED if button.warn else BLUE if button.hold
            else BG_BUTTON_ACTIVE if button.remembered else BG_BUTTON)
    ink = button_ground(draw, rect, fill, hovered=hovered, dim=button.dim,
                        rest_ink=RED if button.danger else AMBER if button.enhanced else None)
    glyph = button.glyph
    if glyph.startswith(APP_MARK):
        draw_icon(draw, rect, app_mark_letter(glyph))
    elif glyph.startswith(SHARED_MARK):
        draw_mark(image, shared_mark_name(glyph), rect, ink)
    elif glyph == MINIMIZE_ICON:
        draw_minimize_bar(draw, rect, ink)
    elif len(glyph) == 1 and not glyph.isalnum():
        draw_glyph(draw, x + w / 2, y + h / 2, glyph, glyph_font, ink)
    else:
        draw.text((x + w / 2, y + h / 2), glyph, font=word_font, anchor="mm", fill=ink)
