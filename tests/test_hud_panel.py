"""The chrome the Funestras' in-video HUDs are drawn on."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from shared_ui import palette
from shared_ui.icons_pil import paste_glyph
from shared_ui.palette import BG_PRIMARY, MAGENTA, TEXT_MUTED, WHITE
from shared_ui.type_scale import SIZE_BODY, SIZE_SMALL

from funestra import hud_panel
from funestra.hud_button import Button
from funestra.hud_marks import app_mark
from funestra.hud_panel import (
    ACTIVE_DOT,
    PANEL_ALPHA,
    TOOLTIP_PAD,
    HudPanel,
    draw_active_dot,
    draw_button,
    draw_glyph,
    draw_tooltip,
    load_font,
    text_width,
)


def test_the_palette_is_shared_uis_own_read_without_qt():
    """The HUDs color with the family's palette itself, not a copy of it: the
    numbers used to be typed out twice, here and in shared_ui, and only a test
    kept them from drifting apart.
    """

    assert hud_panel.WHITE is palette.WHITE
    assert hud_panel.BG_PRIMARY is palette.BG_PRIMARY
    assert hud_panel.BLUE is palette.BLUE


def test_panel_is_a_translucent_rounded_slab_of_the_asked_size():
    panel = HudPanel(60, 40)

    bgra = panel.to_bgra()

    assert bgra.shape == (40, 60, 4)
    middle = bgra[20, 30]
    assert tuple(middle) == (BG_PRIMARY[2], BG_PRIMARY[1], BG_PRIMARY[0], PANEL_ALPHA)
    assert bgra[0, 0, 3] == 0  # the rounded corner leaves the very corner clear
    assert np.asarray(bgra).dtype == np.uint8


def test_a_divider_is_one_line_across_the_slab_in_the_gray_of_its_edge():
    panel = HudPanel(60, 40)

    panel.divide(20)

    rgba = np.asarray(panel.image)
    assert (rgba[20] == (*palette.BORDER_PANEL, 255)).all()
    assert not (rgba[[19, 21], 1:-1] == (*palette.BORDER_PANEL, 255)).all(axis=-1).any()


def test_a_point_size_loads_its_face_at_its_pixels_on_a_96_dpi_screen():
    """Qt sized these HUDs' fonts in points and Pillow sizes in pixels, so the
    panels keep their old proportions only if the conversion does."""
    assert (load_font(SIZE_SMALL).size, load_font(SIZE_BODY).size) == (12, 15)


def test_a_missing_face_falls_back_instead_of_raising():
    """A font the machine does not have must not take the Funestra down mid-render:
    the HUD is drawn every frame, so an OSError here is a crash, not a blank."""
    assert load_font(11, "no-such-face.ttf") is not None


def test_text_width_measures_the_drawn_string():
    font = load_font(11)

    assert text_width(font, "") == 0
    assert text_width(font, "Volume 6") > text_width(font, "Vol")


def test_the_active_dot_is_lit_or_gray_but_never_absent():
    """An absent dot cannot be told from an idle one, so only the Funestra holding the
    floor would say anything — and a reader would have to check every screen to
    learn what one mark should tell them."""
    def dot(active: bool) -> tuple[int, ...]:
        panel = HudPanel(40, 40)
        draw_active_dot(panel.image, 10, 10, active)
        return tuple(np.asarray(panel.image)[15, 15][:3])

    assert dot(True) == WHITE
    assert dot(False) == TEXT_MUTED


def test_the_active_dot_is_the_familys_disc():
    def drawn(paint) -> np.ndarray:
        image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        paint(image)
        return np.asarray(image)

    assert np.array_equal(
        drawn(lambda image: draw_active_dot(image, 10, 10, True)),
        drawn(lambda image: paste_glyph(image, "disc", (10, 10, ACTIVE_DOT + 2, ACTIVE_DOT + 2), WHITE)))


def test_a_tooltip_wider_than_the_panel_wraps_rather_than_running_off_it():
    """A tooltip is drawn into the panel's own bitmap, so whatever crosses the edge
    is simply never drawn — the sentence loses its tail with nothing to say it had
    one.  It wraps to the room there is instead, and the tooltip stays on the slab."""
    panel = HudPanel(150, 120)
    font = load_font(8)

    rect = draw_tooltip(panel.draw, font, "Unfavorite it or mark weird when it is "
                        "not a favorite", (20, 20), panel.image.size)

    x, y, w, h = rect
    assert (x, y) >= (0, 0) and (x + w, y + h) <= (150, 120)
    assert h > sum(font.getmetrics()) + 2 * TOOLTIP_PAD  # more than one line


def test_a_tooltip_that_fits_stays_on_one_line_beside_the_cursor():
    """Wrapping is what a tooltip does when it must, not what it does — one that
    fits keeps its single line and sits down and to the right of the pointer,
    clear of the arrow itself."""
    panel = HudPanel(300, 200)
    font = load_font(8)

    x, y, _w, h = draw_tooltip(panel.draw, font, "Next clip", (40, 60),
                               panel.image.size)

    assert h == sum(font.getmetrics()) + 2 * TOOLTIP_PAD
    assert (x, y) > (40, 60)


def test_a_tooltip_starts_a_new_line_wherever_its_text_does():
    panel = HudPanel(300, 200)
    font = load_font(8)

    _x, _y, _w, h = draw_tooltip(panel.draw, font, "Next clip\nThen the one after it",
                                 (40, 60), panel.image.size)

    assert h == 2 * sum(font.getmetrics()) + 2 * TOOLTIP_PAD


def test_a_tooltip_keeps_the_spaces_it_was_written_with():
    """It wraps with the family's one wrapper, which keeps a text's own spaces
    as the desktop's log does."""
    panel = HudPanel(300, 200)
    font = load_font(8)

    _x, _y, single, _h = draw_tooltip(panel.draw, font, "Next clip", (40, 60), panel.image.size)
    _x, _y, spaced, _h = draw_tooltip(panel.draw, font, "Next    clip", (40, 60),
                                      panel.image.size)

    assert spaced > single


def _ink_center(size: int, paint) -> tuple[float, float]:
    """Where the ink *paint* leaves on a blank square actually sits."""

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    paint(ImageDraw.Draw(image))
    ys, xs = np.nonzero(np.asarray(image)[:, :, 3])
    return (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2


def test_a_glyph_is_centered_on_its_ink_not_on_the_fonts_bounds():
    """``anchor="mm"`` centers the font's bounds, whose lower edge is the descender line
    however short the glyph — which is why every icon button drew its mark low.
    Centering the ink puts it in the middle of the button, for the transport
    arrows, the padlock and the bare minus sign alike."""
    font = load_font(20, "seguisym.ttf")

    for glyph in ("⏮", "\U0001F512", "−", "∿"):
        centered = _ink_center(60, lambda d, g=glyph: draw_glyph(
            d, 30, 30, g, font, (255, 255, 255, 255)))
        by_metrics = _ink_center(60, lambda d, g=glyph: d.text(
            (30, 30), g, font=font, anchor="mm", fill=(255, 255, 255, 255)))

        assert abs(centered[1] - 30) <= 0.5, glyph
        assert by_metrics[1] > centered[1], glyph  # the old way sat lower


def test_an_app_mark_fits_inside_the_button_it_is_centered_in():
    """It has to sit in the same 18px square every other control on these HUDs
    uses, with room left around it rather than running to the button's border."""

    image = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    draw_button(image, ImageDraw.Draw(image), (0, 0, 18, 18), Button("fmode", app_mark("F"), ""),
                hovered=False, glyph_font=load_font(11), word_font=load_font(11))
    ys, xs = np.nonzero((np.asarray(image)[:, :, :3] == MAGENTA).all(axis=2))

    assert xs.min() >= 2 and xs.max() <= 15
    assert ys.min() >= 2 and ys.max() <= 15


def test_a_glyph_with_no_ink_draws_nothing_rather_than_raising():
    """A space has no ink to center on; the HUD repaints every frame, so this must
    be a no-op and not an exception out of the run loop."""

    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw_glyph(ImageDraw.Draw(image), 5, 5, " ", load_font(11), (255, 255, 255, 255))

    assert np.asarray(image)[:, :, 3].max() == 0


