"""A list and a bar a host hands a Funestra for its console: drawn here, pressed here, and
what was picked or set handed back."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from host_controls_fakes import BAR, CHOICES, AHost, a_hud, middle_of
from PIL import Image
from shared_ui.dropdown_pil import ARROW_PX
from shared_ui.palette import BG_PRIMARY, BLUE, TEXT_PRIMARY
from shared_ui.spacing import BUTTON_GAP

from funestra.host_controls import HostControlsPress, HostControlsSection

RECT = (10, 300, 360, HostControlsSection.height)
_X, _Y, _W, _H = RECT


def _painted(hud) -> tuple[np.ndarray, object]:
    image = Image.new("RGBA", (_X + _W + 10, _Y + _H + 10), (*BG_PRIMARY, 224))
    layout = HostControlsSection().draw(image, RECT, hud)
    return np.asarray(image), layout


def _region(painted: np.ndarray, rect) -> np.ndarray:
    x, y, width, height = rect
    return painted[y:y + height, x:x + width, :3]


def _pressing(host: AHost | None = None):
    host = host or AHost()
    press = HostControlsPress(host)
    layout = HostControlsSection().layout(press.drawing(), RECT)
    return press, host, layout


def _off_the_closed_controls() -> tuple[int, int]:
    return _X + _W - 2, _Y - 2


class TestTheField:
    def test_a_press_on_it_opens_the_list(self):
        press, host, layout = _pressing()

        assert press.press(*middle_of(layout.field), layout=layout)
        assert press.drawing().list_open
        assert host.picked == []

    def test_picking_a_row_off_the_list_hands_the_host_that_row_and_closes_the_list(self):
        press, host, layout = _pressing()
        press.press(*middle_of(layout.field), layout=layout)

        assert press.press(*middle_of(layout.rows[2]), layout=layout)
        assert host.picked == [2]
        assert not press.drawing().list_open

    def test_a_press_anywhere_else_closes_the_open_list_and_goes_no_further(self):
        press, host, layout = _pressing()
        press.press(*middle_of(layout.field), layout=layout)

        assert press.press(*_off_the_closed_controls(), layout=layout)
        assert not press.drawing().list_open
        assert host.picked == []

    def test_the_open_list_stays_open_while_what_the_host_shows_changes_under_it(self):
        press, host, layout = _pressing()
        press.press(*middle_of(layout.field), layout=layout)

        host.shows = a_hud("Round", bar=replace(BAR, value=150.0))

        assert press.drawing().list_open

    def test_a_press_off_the_closed_controls_is_left_for_the_console(self):
        press, _host, layout = _pressing()

        assert not press.press(*_off_the_closed_controls(), layout=layout)


class TestTheBar:
    def test_a_press_along_it_sets_the_value_at_that_point(self):
        press, host, layout = _pressing()

        assert press.press(*middle_of(layout.bar), layout=layout)
        assert host.set_to == [pytest.approx(110.0, abs=1.0)]

    def test_a_drag_from_it_goes_on_setting_and_stops_at_either_end(self):
        press, host, layout = _pressing()
        x, y, width, _height = layout.bar
        press.press(x + width // 2, y + 1, layout=layout)

        assert press.holding
        assert press.drag_to(x - 50, y + 40, layout=layout)
        assert press.drag_to(x + width + 50, y - 40, layout=layout)
        assert host.set_to[1:] == [40.0, 180.0]

    def test_a_drag_after_letting_go_sets_nothing(self):
        press, host, layout = _pressing()
        x, y, width, _height = layout.bar
        press.press(x + 2, y + 1, layout=layout)
        press.release()

        assert not press.holding
        assert not press.drag_to(x + width // 2, y + 1, layout=layout)
        assert len(host.set_to) == 1

    def test_controls_without_a_bar_have_none_to_press(self):
        press, host, layout = _pressing(AHost(a_hud(bar=None)))
        _with_a_bar, _host, placed_with_a_bar = _pressing()

        assert layout.bar is None
        assert not press.press(*middle_of(placed_with_a_bar.bar), layout=layout)
        assert host.set_to == []

    def test_a_bar_that_goes_while_it_is_held_lets_go(self):
        press, host, layout = _pressing()
        x, y, width, _height = layout.bar
        press.press(x + 2, y + 1, layout=layout)

        host.shows = a_hud(bar=None)
        press.drawing()

        assert not press.drag_to(x + width // 2, y + 1, layout=layout)
        assert not press.holding
        assert len(host.set_to) == 1


class TestBeforeTheConsoleHasPlacedThem:
    def test_they_take_no_press(self):
        press, host, layout = _pressing()

        assert not press.press(*middle_of(layout.field), layout=None)
        assert not press.drawing().list_open
        assert host.picked == []


class TestWhileTheHostHasNothingToShow:
    def test_nothing_is_drawn(self):
        press, host, _layout = _pressing()

        host.shows = None

        assert press.drawing() is None

    def test_they_take_no_press(self):
        press, host, layout = _pressing()
        press.press(*middle_of(layout.field), layout=layout)

        host.shows = None
        press.drawing()

        assert not press.press(*middle_of(layout.rows[2]), layout=layout)
        assert not press.press(*middle_of(layout.bar), layout=layout)
        assert host.picked == host.set_to == []

    def test_the_list_they_come_back_with_is_closed(self):
        press, host, layout = _pressing()
        press.press(*middle_of(layout.field), layout=layout)

        host.shows = None
        press.drawing()
        host.shows = a_hud()

        assert not press.drawing().list_open

    def test_a_funestra_with_no_host_draws_none_and_takes_no_press(self):
        press = HostControlsPress(None)
        layout = HostControlsSection().layout(a_hud(), RECT)

        assert press.drawing() is None
        assert not press.press(*middle_of(layout.field), layout=layout)


class TestWhatItDraws:
    @pytest.mark.parametrize("name", CHOICES)
    def test_each_name_ends_short_of_the_fields_arrow(self, name):
        painted, layout = _painted(a_hud(name))
        x, y, width, height = layout.field
        arrow_starts = width - ARROW_PX - BUTTON_GAP
        written = painted[y:y + height, x:x + arrow_starts, :3]
        inked = np.flatnonzero((np.abs(written.astype(int) - TEXT_PRIMARY).sum(axis=2) < 90)
                               .any(axis=0))

        assert inked.max() < arrow_starts - 1

    def test_the_field_names_what_is_chosen(self):
        curved, layout = _painted(a_hud("Curved"))
        round_, _layout = _painted(a_hud("Round"))

        assert not np.array_equal(_region(curved, layout.field), _region(round_, layout.field))

    def test_the_open_list_hangs_over_what_is_above_the_field(self):
        closed, layout = _painted(a_hud())
        opened, _layout = _painted(replace(a_hud(), list_open=True))

        assert not np.array_equal(_region(closed, layout.rows[0]), _region(opened, layout.rows[0]))

    def test_the_open_list_marks_what_is_chosen_in_blue(self):
        opened, layout = _painted(replace(a_hud("Round"), list_open=True))

        def blue_across(row) -> bool:
            x, y, width, height = row
            band = opened[y + height // 2, x + 2:x + width - 2, :3]
            return bool((band == np.asarray(BLUE, dtype=band.dtype)).all(axis=1).any())

        assert blue_across(layout.rows[CHOICES.index("Round")])
        assert not blue_across(layout.rows[CHOICES.index("Plain")])

    def test_the_bar_fills_further_the_higher_its_value(self):
        def filled(value: float) -> tuple[int, int]:
            painted, layout = _painted(a_hud(bar=replace(BAR, value=value)))
            x, y, width, height = layout.bar
            middle = painted[y + height // 2, x:x + width, :3]
            return (int((middle == np.asarray(TEXT_PRIMARY, dtype=middle.dtype)).all(axis=1).sum()),
                    width)

        (least, width), (some, _), (most, _) = filled(40.0), filled(110.0), filled(180.0)

        assert least < some < most
        assert most >= width - 2

    def test_its_value_is_written_beside_its_bar(self):
        narrow, layout = _painted(a_hud(bar=replace(BAR, value=120.0)))
        wide, _layout = _painted(a_hud(bar=replace(BAR, value=160.0)))

        assert not np.array_equal(_region(narrow, _between_field_and_bar(layout)),
                                  _region(wide, _between_field_and_bar(layout)))

    def test_the_bar_is_named_by_its_label(self):
        spread, layout = _painted(a_hud())
        reach, _layout = _painted(a_hud(bar=replace(BAR, label="Reach")))

        assert not np.array_equal(_region(spread, _between_field_and_bar(layout)),
                                  _region(reach, _between_field_and_bar(layout)))

    def test_the_bar_holds_still_whatever_its_value(self):
        _low, at_the_low_end = _painted(a_hud(bar=replace(BAR, value=40.0)))
        _high, at_the_high_end = _painted(a_hud(bar=replace(BAR, value=180.0)))

        assert at_the_low_end.bar == at_the_high_end.bar

    def test_controls_without_a_bar_draw_nothing_after_their_field(self):
        painted, layout = _painted(a_hud(bar=None))
        x, _y, width, _height = layout.field
        rest = (x + width, _Y, _X + _W - x - width, _H)

        region = _region(painted, rest)

        assert (region == np.asarray(BG_PRIMARY, dtype=region.dtype)).all()

    def test_the_field_is_as_wide_as_its_widest_name_needs(self):
        section = HostControlsSection()
        short = replace(a_hud(bar=None), choices=("Plain", "Round"))

        assert section.least_width(a_hud(bar=None)) > section.least_width(short)
        assert section.layout(a_hud(bar=None), RECT).field[2] == section.least_width(
            a_hud(bar=None))

    def test_a_bar_asks_for_room_beyond_the_field(self):
        section = HostControlsSection()

        assert section.least_width(a_hud()) > section.least_width(a_hud(bar=None))


def _between_field_and_bar(layout) -> tuple[int, int, int, int]:
    field_x, _y, field_width, _height = layout.field
    bar_x = layout.bar[0]
    return field_x + field_width, _Y, bar_x - field_x - field_width, _H
