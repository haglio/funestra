from __future__ import annotations

import inspect

import numpy as np
from PIL import Image, ImageDraw
from shared_ui import palette
from shared_ui.icons_pil import paste_icon
from shared_ui.palette import BG_PRIMARY, MAGENTA, TEXT_MUTED, WHITE
from shared_ui.type_scale import SIZE_BODY, SIZE_SMALL

from funestra import hud
from funestra.hud import (
    ACTIVE_DOT,
    HUD_ALPHA,
    TOOLTIP_PAD,
    ButtonLook,
    Hud,
    draw_active_dot,
    draw_button,
    draw_character,
    draw_tooltip,
    load_font,
    text_width,
)
from funestra.hud_button import Button
from funestra.hud_icons import app_icon


def test_the_palette_is_shared_uis_own_read_without_qt():
    assert hud.WHITE is palette.WHITE
    assert hud.BG_PRIMARY is palette.BG_PRIMARY
    assert hud.BLUE is palette.BLUE


def test_hud_is_a_translucent_rounded_slab_of_the_asked_size_see_through_enough_for_the_video_and_solid_enough_for_its_text():
    hud = Hud(60, 40)

    bgra = hud.to_bgra()

    assert bgra.shape == (40, 60, 4)
    middle = bgra[20, 30]
    assert tuple(middle) == (BG_PRIMARY[2], BG_PRIMARY[1], BG_PRIMARY[0], HUD_ALPHA)
    assert bgra[0, 0, 3] == 0
    assert np.asarray(bgra).dtype == np.uint8


def test_a_divider_is_one_line_across_the_slab_in_the_gray_of_its_edge():
    hud = Hud(60, 40)

    hud.divide(20)

    rgba = np.asarray(hud.image)
    assert (rgba[20] == (*palette.BORDER_PANEL, 255)).all()
    assert not (rgba[[19, 21], 1:-1] == (*palette.BORDER_PANEL, 255)).all(axis=-1).any()


def test_a_point_size_loads_its_face_at_its_pixels_on_a_96_dpi_screen():
    assert (load_font(SIZE_SMALL).size, load_font(SIZE_BODY).size) == (12, 15)


def test_a_missing_face_falls_back_instead_of_raising():
    assert load_font(11, "no-such-face.ttf") is not None


def test_text_width_measures_the_drawn_string():
    font = load_font(11)

    assert text_width(font, "") == 0
    assert text_width(font, "Volume 6") > text_width(font, "Vol")


def test_the_active_dot_is_lit_or_gray_but_never_absent():
    def dot(active: bool) -> tuple[int, ...]:
        hud = Hud(40, 40)
        draw_active_dot(hud.image, 10, 10, active)
        return tuple(np.asarray(hud.image)[15, 15][:3])

    assert dot(True) == WHITE
    assert dot(False) == TEXT_MUTED


def test_the_active_dot_is_the_familys_disc_the_same_mark_in_the_same_corner_on_every_hud_for_a_reader_glancing_across_screens():
    def drawn(paint) -> np.ndarray:
        image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        paint(image)
        return np.asarray(image)

    assert np.array_equal(
        drawn(lambda image: draw_active_dot(image, 10, 10, True)),
        drawn(lambda image: paste_icon(image, "disc", (10, 10, ACTIVE_DOT + 2, ACTIVE_DOT + 2), WHITE)))


def test_a_tooltip_wider_than_the_hud_wraps_rather_than_running_off_it():
    hud = Hud(150, 120)
    font = load_font(8)

    rect = draw_tooltip(hud.draw, font, "Unfavorite it or send to Trash when it is "
                        "not a favorite", (20, 20), hud.image.size)

    x, y, w, h = rect
    assert (x, y) >= (0, 0)
    assert (x + w, y + h) <= (150, 120)
    assert h > sum(font.getmetrics()) + 2 * TOOLTIP_PAD


def test_a_tooltip_that_fits_stays_on_one_line_beside_the_cursor():
    hud = Hud(300, 200)
    font = load_font(8)

    x, y, _w, h = draw_tooltip(hud.draw, font, "Next clip", (40, 60),
                               hud.image.size)

    assert h == sum(font.getmetrics()) + 2 * TOOLTIP_PAD
    assert (x, y) > (40, 60)


def test_a_tooltip_starts_a_new_line_wherever_its_text_does():
    hud = Hud(300, 200)
    font = load_font(8)

    _x, _y, _w, h = draw_tooltip(hud.draw, font, "Next clip\nThen the one after it",
                                 (40, 60), hud.image.size)

    assert h == 2 * sum(font.getmetrics()) + 2 * TOOLTIP_PAD


def test_a_tooltip_keeps_the_spaces_it_was_written_with():
    hud = Hud(300, 200)
    font = load_font(8)

    _x, _y, single, _h = draw_tooltip(hud.draw, font, "Next clip", (40, 60), hud.image.size)
    _x, _y, spaced, _h = draw_tooltip(hud.draw, font, "Next    clip", (40, 60),
                                      hud.image.size)

    assert spaced > single


def _ink_center(size: int, paint) -> tuple[float, float]:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    paint(ImageDraw.Draw(image))
    ys, xs = np.nonzero(np.asarray(image)[:, :, 3])
    return (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2


def test_a_icon_is_centered_on_its_ink_not_on_the_fonts_bounds():
    font = load_font(20, "seguisym.ttf")

    for icon in ("⏮", "\U0001F512", "\u2212", "∿"):
        centered = _ink_center(60, lambda d, g=icon: draw_character(
            d, (30, 30), g, font, (255, 255, 255, 255)))
        by_metrics = _ink_center(60, lambda d, g=icon: d.text(
            (30, 30), g, font=font, anchor="mm", fill=(255, 255, 255, 255)))

        assert abs(centered[1] - 30) <= 0.5, icon
        assert by_metrics[1] > centered[1], icon


def test_an_app_mark_fits_inside_the_button_it_is_centered_in():
    image = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    draw_button(image, ImageDraw.Draw(image), (0, 0, 18, 18), Button("fmode", app_icon("F"), ""),
        ButtonLook(
            hovered=False,
            icon_font=load_font(11),
            word_font=load_font(11)))
    ys, xs = np.nonzero((np.asarray(image)[:, :, :3] == MAGENTA).all(axis=2))

    assert xs.min() >= 2
    assert xs.max() <= 15
    assert ys.min() >= 2
    assert ys.max() <= 15


def test_a_icon_with_no_ink_draws_nothing_rather_than_raising():
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw_character(ImageDraw.Draw(image), (5, 5), " ", load_font(11), (255, 255, 255, 255))

    assert np.asarray(image)[:, :, 3].max() == 0


def _button_pixels(button: Button, *, hovered: bool) -> np.ndarray:
    image = Image.new("RGBA", (40, 24), (0, 0, 0, 0))
    draw_button(image, ImageDraw.Draw(image), (2, 2, 36, 20), button,
        ButtonLook(
            hovered=hovered,
            icon_font=load_font(11),
            word_font=load_font(11)))
    return np.asarray(image).copy()


def test_a_dim_button_is_not_lightened_by_the_pointer():
    dim = Button("next", "Go", "", dim=True)

    assert (_button_pixels(dim, hovered=True) == _button_pixels(dim, hovered=False)).all()


def test_hovering_a_button_lightens_its_fill_but_not_its_outline():
    button = Button("next", "Go", "")
    rest = _button_pixels(button, hovered=False)
    over = _button_pixels(button, hovered=True)

    assert tuple(over[2, 12]) == tuple(rest[2, 12])
    assert tuple(over[8, 6]) != tuple(rest[8, 6])


def test_a_button_with_no_command_draws_no_ground_under_its_word():
    readout = _button_pixels(Button("", "1x", ""), hovered=False)

    assert readout[3, 3, 3] == 0
    assert readout[:, :, 3].max() > 0


def test_a_tooltip_near_the_far_corner_is_nudged_back_inside_the_hud():
    hud = Hud(150, 120)

    x, y, w, h = draw_tooltip(hud.draw, load_font(8), "Next clip", (148, 118),
                              hud.image.size)

    assert (x, y) >= (0, 0)
    assert (x + w, y + h) <= (150, 120)


def test_every_label_is_bold_unless_asked_otherwise_since_it_is_read_at_a_glance_over_moving_video():
    assert inspect.signature(hud.load_font).parameters["family"].default == hud.BOLD_FACE
