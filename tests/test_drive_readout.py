"""The Robot Hand's drive readout: what it says, and the controls it carries."""
from __future__ import annotations

import numpy as np
import pytest
from shared_ui.palette import BLUE, BORDER_DEFAULT, GREEN, MAGENTA, TEXT_MUTED, TEXT_PRIMARY

from funestra.drive_layout import (
    AMPLITUDE,
    CENTER,
    SECTION_H,
    SECTION_W,
    SPEED,
)
from funestra.drive_readout import (
    DISABLED_INK,
    DRIVEN_BY_AUTO,
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NEUTRAL,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    DriveHud,
    DriveSection,
    TrackGrip,
    controls,
    label_pair_x,
    publish_drive,
    read_drive,
    readout_targets,
    track_command,
    track_value,
    tracks,
)
from funestra.hud_panel import (
    HudPanel,
    load_font,
    text_width,
)
from funestra.robot_hand import amplitude_ceiling, speed_ceiling

PAD = 10


def _hud(**overrides) -> DriveHud:
    base = dict(speed=50, amplitude=80, center=50, shape="sine", position=5000,
                waveform=tuple(0.5 + 0.4 * np.sin(i / 6) for i in range(80)))
    base.update(overrides)
    return DriveHud(**base)


def _rendered(hud: DriveHud) -> np.ndarray:
    panel = HudPanel(SECTION_W + 2 * PAD, SECTION_H + 2 * PAD)
    DriveSection().draw(panel.image, PAD, PAD, hud)
    return np.asarray(panel.image)


class TestControls:
    """Each axis is one object: its controls, its bar and its number together."""

    def test_it_offers_every_axis_a_way_up_and_down(self):
        actions = {control.command for control in controls(0, 0, _hud())}

        assert actions == {
            "robot_hand_speed_down", "robot_hand_speed_up",
            "robot_hand_amplitude_up", "robot_hand_amplitude_down",
            "robot_hand_center_up", "robot_hand_center_down",
        }

    def test_every_axis_is_moved_by_the_same_pair_of_marks(self):
        """Triangles on two axes and −/+ on the third read as two kinds of
        control for three things that are the same kind."""
        by_command = {c.command: c.mark for c in controls(0, 0, _hud())}

        assert {by_command[a] for a in
                ("robot_hand_speed_up", "robot_hand_amplitude_up", "robot_hand_center_up")} == {"plus"}
        assert {by_command[a] for a in
                ("robot_hand_speed_down", "robot_hand_amplitude_down", "robot_hand_center_down")} == {"minus"}

    def test_the_speed_controls_sit_below_the_trace(self):
        """Speed is out from between center and amplitude, under the trace, so the
        three axes do not crowd one band."""
        by_command = {c.command: c.rect for c in controls(0, 0, _hud())}
        _x, trace_y, _w, trace_h = next(t.rect for t in tracks(0, 0, _hud()) if t.axis == CENTER)
        wave_lower = trace_y + trace_h

        assert by_command["robot_hand_speed_down"][1] >= wave_lower
        assert by_command["robot_hand_speed_up"][1] >= wave_lower

    def test_a_mark_at_its_limit_is_dimmed(self):
        """The flag on the readout says the axis has run out of range, so the mark
        that would do nothing is grayed — the console then drops it from the hit
        targets, the same as any dimmed control."""
        by_command = {c.command: c for c in controls(0, 0, _hud(spd_at_max=True, amp_at_min=True))}

        assert by_command["robot_hand_speed_up"].dim is True
        assert by_command["robot_hand_speed_down"].dim is False
        assert by_command["robot_hand_amplitude_down"].dim is True

    def test_the_center_marks_follow_the_line(self):
        """They sit beside the center's dotted line, so they move up the panel as
        the center rises."""
        low = {c.command: c.rect for c in controls(0, 0, _hud(center=20))}
        high = {c.command: c.rect for c in controls(0, 0, _hud(center=80))}

        assert high["robot_hand_center_up"][1] < low["robot_hand_center_up"][1]

    def test_the_marks_it_offers_all_fall_on_the_block_it_draws(self):
        """Drawing and hit-testing place the marks from one geometry, so a press
        lands on what is on screen — at either end of the center's travel."""
        for center in (0, 50, 100):
            for x, y, w, h in (c.rect for c in controls(PAD, PAD, _hud(center=center))):
                assert x >= PAD and x + w <= PAD + SECTION_W
                assert y >= PAD and y + h <= PAD + SECTION_H

    def test_each_plus_and_minus_sits_in_the_middle_of_its_mark(self):
        hud = _hud()
        rgb = _rendered(hud).astype(float)[..., :3]

        for control in controls(PAD, PAD, hud):
            x, y, w, h = control.rect
            inside = rgb[y + 1:y + h - 1, x + 1:x + w - 1].max(axis=2)
            ink = np.clip(inside - 60, 0, None)
            rows, columns = np.indices(ink.shape)
            middle_row, middle_column = (h - 3) / 2, (w - 3) / 2

            assert abs((ink * rows).sum() / ink.sum() - middle_row) <= 0.25, control.command
            assert abs((ink * columns).sum() / ink.sum() - middle_column) <= 0.25, control.command


class TestTheCenterLabel:
    @staticmethod
    def _ink_rows_left_of_the_center_marks(hud: DriveHud) -> tuple[list[int], tuple]:
        marks = {c.command: c.rect for c in controls(PAD, PAD, hud)}
        up, down = marks["robot_hand_center_up"], marks["robot_hand_center_down"]
        column = _rendered(hud).astype(int)[PAD:PAD + SECTION_H, PAD:up[0], :3]
        rows = np.flatnonzero((column.max(axis=2) > 90).any(axis=1))
        return [PAD + int(row) for row in rows], (up[1], down[1] + down[3])

    @pytest.mark.parametrize("center", [0, 20, 50, 80, 100])
    def test_the_word_and_its_number_ride_beside_the_center_marks(self, center):
        rows, (marks_top, marks_bottom) = self._ink_rows_left_of_the_center_marks(
            _hud(center=center))

        assert rows
        assert marks_top <= rows[0] and rows[-1] < marks_bottom

    @staticmethod
    def _on_the_word(hud: DriveHud) -> tuple[int, int]:
        x, y, _w, h = next(c.rect for c in controls(PAD, PAD, hud)
                           if c.command == "robot_hand_center_up")
        return x - 10, y + h // 2

    def test_a_press_on_the_word_takes_hold_of_the_center_without_moving_it(self):
        hud = _hud(center=50)
        grip = TrackGrip()

        _buttons, grabbable = readout_targets(PAD, PAD, hud)

        assert grip.grab(grabbable, *self._on_the_word(hud)) == ""
        assert grip.holding

    def test_dragging_the_word_moves_the_center_as_far_as_the_pointer_travels(self):
        hud = _hud(center=50)
        grip = TrackGrip()
        px, py = self._on_the_word(hud)
        grip.grab(readout_targets(PAD, PAD, hud)[1], px, py)
        trace_h = next(t.rect for t in tracks(PAD, PAD, hud) if t.axis == CENTER)[3]
        rows_per_ten = (trace_h - 1) / 10

        assert grip.drag_to(px, py) == ""
        assert grip.drag_to(px, py - round(2 * rows_per_ten)) == "robot_hand_center_70"
        assert grip.drag_to(px, py + round(4 * rows_per_ten)) == "robot_hand_center_10"


class TestTracks:
    """The bands themselves take a level from where you press in them, so a bar
    is set outright instead of walked to with the marks beside it."""

    @staticmethod
    def _band(hud: DriveHud, axis: str):
        return next(t for t in tracks(PAD, PAD, hud) if t.axis == axis)

    def test_it_offers_a_band_for_each_of_the_three_axes(self):
        assert {t.axis for t in tracks(0, 0, _hud())} == {AMPLITUDE, CENTER, SPEED}

    def test_each_band_covers_the_bar_the_axis_is_drawn_as(self):
        """The trace's band is the trace; the speed band sits between its two
        marks, and the amplitude band between its own."""
        hud = _hud()
        marks = {c.command: c.rect for c in controls(PAD, PAD, hud)}
        speed = self._band(hud, SPEED).rect
        amp = self._band(hud, AMPLITUDE).rect
        down_x, down_y, down_w, _h = marks["robot_hand_speed_down"]

        assert speed[0] >= down_x + down_w
        assert speed[0] + speed[2] <= marks["robot_hand_speed_up"][0]
        assert speed[1] >= down_y - 1
        assert amp[1] >= marks["robot_hand_amplitude_up"][1] + marks["robot_hand_amplitude_up"][3]
        assert amp[1] + amp[3] <= marks["robot_hand_amplitude_down"][1]

    def test_a_press_along_the_speed_bar_asks_for_how_far_along_it_sits(self):
        band = self._band(_hud(), SPEED)
        x, y, w, h = band.rect

        assert track_value(band, x, y + h // 2) == 0
        assert abs(track_value(band, x + (w - 1) // 2, y + h // 2) - 50) <= 1
        assert track_value(band, x + w - 1, y + h // 2) == 100

    def test_a_press_in_the_trace_asks_for_the_height_it_sits_at(self):
        """The center's dotted line is drawn at its own height across the trace,
        so pressing there is asking for the line to come to the pointer.

        Within a pixel in the middle of the band: the trace is fewer rows tall
        than the hundred values it spans, so a row lands between two of them.
        """
        band = self._band(_hud(), CENTER)
        x, y, w, h = band.rect

        assert track_value(band, x + w // 2, y) == 100
        assert track_value(band, x + w // 2, y + h - 1) == 0
        assert abs(track_value(band, x + w // 2, y + (h - 1) // 2) - 50) <= 1

    def test_a_press_up_the_amplitude_bar_asks_for_a_motion_that_reaches_it(self):
        """The bar is drawn out from the center both ways, so its ends are the
        handles: pressing where one is asks for the amplitude already set, and
        pressing past it asks for a longer motion.  Pressing at the center itself
        asks for no motion at all."""
        band = self._band(_hud(amplitude=50, center=50), AMPLITUDE)
        x, y, w, h = band.rect
        top_of_bar = y + round(0.25 * (h - 1))

        assert abs(track_value(band, x + w // 2, top_of_bar) - 50) <= 1
        assert track_value(band, x + w // 2, y) == 100
        assert track_value(band, x + w // 2, y + h - 1) == 100
        assert abs(track_value(band, x + w // 2, y + (h - 1) // 2)) <= 2

    def test_the_amplitude_bar_mirrors_about_wherever_the_center_is(self):
        """A motion centered low reaches the top of the bar only by growing to the
        full range and back, so the same press means different amplitudes."""
        low = self._band(_hud(center=25), AMPLITUDE)
        x, y, w, _h = low.rect

        assert track_value(low, x + w // 2, y) == 100

    def test_a_press_beyond_a_band_reads_as_its_nearer_end(self):
        """A drag that wanders off the bar goes on setting it rather than stopping
        dead at the edge, the way every slider behaves."""
        band = self._band(_hud(), SPEED)
        x, y, w, h = band.rect

        assert track_value(band, x - 400, y + h // 2) == 0
        assert track_value(band, x + w + 400, y + h // 2) == 100

    def test_a_press_past_the_speed_the_max_intensity_leaves_asks_for_no_more_than_that(self):
        band = self._band(_hud(speed=30, amplitude=20, max_intensity=5), SPEED)
        x, y, w, h = band.rect

        assert track_value(band, x + w - 1, y + h // 2) == speed_ceiling(5, 20)

    def test_a_press_past_the_amplitude_the_max_intensity_leaves_asks_for_no_more_than_that(self):
        band = self._band(_hud(speed=50, amplitude=20, center=50, max_intensity=5), AMPLITUDE)
        x, y, w, _h = band.rect

        assert track_value(band, x + w // 2, y) == amplitude_ceiling(5, 50)

    def test_a_press_posts_the_set_command_fun_time_already_routes(self):
        band = self._band(_hud(), SPEED)
        x, y, _w, h = band.rect

        assert track_command(band, x, y + h // 2) == "robot_hand_speed_0"

    def test_every_band_is_dimmed_while_a_funscript_has_the_device(self):
        """A motion Genau is not sending cannot be dragged, for the same reason
        its marks cannot be pressed."""
        assert all(t.dim for t in tracks(0, 0, _hud(driven=DRIVEN_BY_FUNSCRIPT)))
        assert not any(t.dim for t in tracks(0, 0, _hud()))

    def test_the_bands_it_offers_all_fall_on_the_block_it_draws(self):
        for center in (0, 50, 100):
            for x, y, w, h in (t.rect for t in tracks(PAD, PAD, _hud(center=center))):
                assert x >= PAD and x + w <= PAD + SECTION_W
                assert y >= PAD and y + h <= PAD + SECTION_H


class TestReadout:
    @pytest.mark.parametrize("center", [0, 100])
    def test_it_draws_nothing_outside_the_block_it_declares(self, center):
        size = (SECTION_W + 2 * PAD, SECTION_H + 4 * PAD)
        drawn = HudPanel(*size)
        DriveSection().draw(drawn.image, PAD, PAD, _hud(center=center))
        changed = (np.asarray(drawn.image) != np.asarray(HudPanel(*size).image)).any(axis=2)
        rows, columns = np.nonzero(changed)

        assert rows.min() >= PAD and rows.max() < PAD + SECTION_H
        assert columns.min() >= PAD and columns.max() < PAD + SECTION_W

    def test_it_fills_the_block_it_declares(self):
        rgb = _rendered(_hud(speed=62, center=45, amplitude=80))

        assert rgb.shape == (SECTION_H + 2 * PAD, SECTION_W + 2 * PAD, 4)
        assert (rgb[:, :, 3] > 0).mean() > 0.5

    def test_a_bigger_motion_draws_a_bigger_bar(self):
        def blue(hud):
            rgb = _rendered(hud).astype(int)[:, :, :3]
            return int(((rgb[:, :, 2] > 150) & (rgb[:, :, 0] < 120)).sum())

        assert blue(_hud(amplitude=90, waveform=())) > blue(_hud(amplitude=20, waveform=()))

    def test_the_speed_bar_runs_in_the_motion_s_own_blue(self):
        """The trace, the amplitude bar and this are all one thing — the motion
        Genau is sending — so they are one color.  It was green, which across
        these HUDs means the favorites and the funscripts."""
        hud = _hud(speed=100, waveform=())
        rgb = _rendered(hud).astype(int)[:, :, :3]
        rects = {c.command: c.rect for c in controls(PAD, PAD, hud)}
        down_x, down_y, down_w, down_h = rects["robot_hand_speed_down"]
        up_x = rects["robot_hand_speed_up"][0]
        bar = rgb[down_y + down_h // 2, down_x + down_w + 4:up_x - 4]

        assert ((bar[:, 2] > 150) & (bar[:, 0] < 120)).all()


class TestTheAmplitudeBarBesideTheTrace:
    @staticmethod
    def _blue_rows(rgb: np.ndarray, rect) -> list[int]:
        x, y, w, h = rect
        inside = rgb[y:y + h, x:x + w, :3]
        blue = (inside[..., 2] > 150) & (inside[..., 0] < 120)
        return [y + int(row) for row in np.flatnonzero(blue.any(axis=1))]

    def test_its_blue_reaches_as_high_and_as_low_as_the_trace_s_line(self):
        hud = _hud(amplitude=60, center=40,
                   waveform=tuple(0.4 + 0.3 * np.sin(i / 6) for i in range(80)))
        rgb = _rendered(hud).astype(int)
        bands = {t.axis: t.rect for t in tracks(PAD, PAD, hud)}

        line = self._blue_rows(rgb, bands[CENTER])
        bar = self._blue_rows(rgb, bands[AMPLITUDE])

        assert abs(line[0] - bar[0]) <= 1
        assert abs(line[-1] - bar[-1]) <= 1


class TestTheStretchesTheMaxIntensityRulesOut:
    @staticmethod
    def _red(pixels: np.ndarray) -> np.ndarray:
        return (pixels[..., 0] > 180) & (pixels[..., 1] < 120) & (pixels[..., 2] < 120)

    def test_the_speed_bar_is_etched_red_past_the_fastest_the_max_intensity_leaves(self):
        hud = _hud(speed=30, amplitude=20, max_intensity=5, waveform=())
        rgb = _rendered(hud).astype(int)
        x, y, w, h = next(t for t in tracks(PAD, PAD, hud) if t.axis == SPEED).rect
        edge = x + round(speed_ceiling(5, 20) / 100 * w)

        assert self._red(rgb[y:y + h, edge + 2:x + w]).any()
        assert not self._red(rgb[y:y + h, x:edge - 1]).any()

    def test_the_amplitude_bar_is_etched_red_beyond_the_widest_the_max_intensity_leaves(self):
        hud = _hud(speed=50, amplitude=20, center=50, max_intensity=5, waveform=())
        rgb = _rendered(hud).astype(int)
        x, y, w, h = next(t for t in tracks(PAD, PAD, hud) if t.axis == AMPLITUDE).rect
        reach = amplitude_ceiling(5, 50) / 100 * h / 2
        upper, lower = round(y + h / 2 - reach), round(y + h / 2 + reach)

        assert self._red(rgb[y:upper - 1, x:x + w]).any()
        assert self._red(rgb[lower + 1:y + h, x:x + w]).any()
        assert not self._red(rgb[upper + 1:lower - 1, x:x + w]).any()

    def test_a_center_off_the_middle_etches_nothing_that_growing_the_amplitude_reaches(self):
        hud = _hud(speed=50, amplitude=40, center=30, max_intensity=100, waveform=())
        rgb = _rendered(hud).astype(int)
        x, y, w, h = next(t for t in tracks(PAD, PAD, hud) if t.axis == AMPLITUDE).rect

        assert not self._red(rgb[y:y + h, x:x + w]).any()

    def test_below_full_the_etching_starts_where_the_widest_reach_carries_the_blue(self):
        hud = _hud(speed=50, amplitude=20, center=10, max_intensity=10, waveform=())
        rgb = _rendered(hud).astype(int)
        x, y, w, h = next(t for t in tracks(PAD, PAD, hud) if t.axis == AMPLITUDE).rect
        edge = y + round((1 - amplitude_ceiling(10, 50) / 100) * h)

        assert self._red(rgb[y:edge - 2, x:x + w]).any()
        assert not self._red(rgb[edge + 2:y + h, x:x + w]).any()


class TestPublishing:
    """In kino mode the readout is drawn by the Main Funestra, so Genau says it instead of drawing it."""

    def test_a_published_readout_reads_back_whole_including_its_limits(self, tmp_path):
        hud = _hud(shape="sawtooth", advance_interval=7,
                   spd_at_max=True, ctr_at_min=True)
        path = tmp_path / "genau_drive.txt"

        assert publish_drive(path, hud) is True
        read = read_drive(path)

        assert (read.speed, read.amplitude, read.center) == (hud.speed, hud.amplitude, hud.center)
        assert (read.shape, read.advance_interval) == ("sawtooth", 7)
        assert (read.spd_at_max, read.ctr_at_min) == (True, True)
        assert np.allclose(read.waveform, hud.waveform, atol=5e-4)

    def test_the_max_intensity_the_wave_is_held_to_goes_over_the_wire(self, tmp_path):
        path = tmp_path / "genau_drive.txt"
        publish_drive(path, _hud(max_intensity=35))

        assert read_drive(path).max_intensity == 35

    def test_a_file_from_before_the_max_intensity_was_published_holds_nothing_down(self, tmp_path):
        path = tmp_path / "genau_drive.txt"
        publish_drive(path, _hud(max_intensity=35))
        text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                         if not line.startswith("max_intensity="))
        path.write_text(text + "\n", encoding="utf-8")

        assert read_drive(path).max_intensity == DriveHud.max_intensity

    def test_the_knot_slide_and_the_edge_go_over_the_wire_too(self, tmp_path):
        """A trace read on knots (the learned motion's) is published with how
        far the line is shifted and the knot past the border, so the Funestra
        drawing it slides the same stable drawing Genau does."""
        path = tmp_path / "genau_drive.txt"
        publish_drive(path, _hud(slide=0.4, edge=0.75))

        read = read_drive(path)

        assert read.slide == pytest.approx(0.4)
        assert read.edge == pytest.approx(0.75)

    def test_a_file_from_before_the_slide_was_published_shifts_nothing(self, tmp_path):
        path = tmp_path / "genau_drive.txt"
        publish_drive(path, _hud())
        text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                         if not line.startswith(("slide=", "edge=")))
        path.write_text(text + "\n", encoding="utf-8")

        read = read_drive(path)

        assert (read.slide, read.edge) == (0.0, None)

    def test_who_drives_each_stretch_of_the_line_goes_over_the_wire(self, tmp_path):
        path = tmp_path / "portrait_osr2_readout.txt"
        stretches = ((0, DRIVEN_BY_FUNSCRIPT), (40, DRIVEN_BY_ROBOT_HAND))
        publish_drive(path, _hud(driven=DRIVEN_BY_FUNSCRIPT, segments=stretches))

        read = read_drive(path)

        assert (read.driven, read.segments) == (DRIVEN_BY_FUNSCRIPT, stretches)

    def test_a_readout_that_has_been_over_the_wire_survives_going_again(self, tmp_path):
        path = tmp_path / "genau_drive.txt"
        publish_drive(path, _hud())
        once = read_drive(path)

        publish_drive(path, once)

        assert read_drive(path) == once

    def test_a_missing_or_torn_read_keeps_what_the_reader_has(self, tmp_path):
        path = tmp_path / "genau_drive.txt"

        assert read_drive(path) is None

        path.write_text("speed=40\namplit", encoding="utf-8")
        assert read_drive(path) is None


class TestLabelPair:
    def test_a_pair_is_placed_as_one_unit(self):
        font = load_font(8)

        key_x, value_x = label_pair_x(font, "Speed", left=10)

        assert key_x == 10
        assert value_x >= key_x + text_width(font, "Speed")


class TestWhoseMotion:
    """The trace is a drawing of what the device is being sent, so it is drawn in
    the color of whoever is sending it — and drawn still when nobody is."""

    @staticmethod
    def _line_colors(hud: DriveHud) -> set[tuple[int, int, int]]:
        """Every color the trace's own line is drawn in, panel and ruler aside."""
        rgb = _rendered(hud).astype(int)[:, :, :3]
        return {tuple(pixel) for row in rgb for pixel in row} - {(0, 0, 0)}

    def test_the_robot_hand_s_motion_is_blue(self):
        assert BLUE in self._line_colors(_hud(driven=DRIVEN_BY_ROBOT_HAND))

    def test_a_funscript_s_motion_is_green(self):
        """Green is what the funscripts own everywhere else on these HUDs."""
        assert GREEN in self._line_colors(_hud(driven=DRIVEN_BY_FUNSCRIPT))

    def test_the_device_s_own_swing_is_neither_driver_s_color(self):
        """In auto mode the OSR2 runs itself: neither the hand nor a funscript is
        sending, so the line wears the third color the word beside it already
        wears rather than borrowing either of theirs."""
        colors = self._line_colors(_hud(driven=DRIVEN_BY_AUTO))

        assert MAGENTA in colors
        assert BLUE not in colors
        assert GREEN not in colors

    def test_a_motion_nobody_is_sending_is_the_muted_gray_of_a_dead_control(self):
        """The readout is switched off whole rather than a live trace sitting in
        the middle of dead furniture."""
        assert TEXT_MUTED in self._line_colors(_hud(driven=DRIVEN_BY_NOTHING))

    def test_only_the_robot_hand_s_motion_carries_the_center_ruler(self):
        """The dotted line says "the motion swings about here", which is the
        Robot Hand's own idea — a claim about a motion a funscript is not making."""
        hand = _rendered(_hud(driven=DRIVEN_BY_ROBOT_HAND, waveform=()))
        script = _rendered(_hud(driven=DRIVEN_BY_FUNSCRIPT, waveform=()))

        assert not np.array_equal(hand, script)

    def test_only_the_robot_hand_s_motion_leaves_its_controls_live(self):
        for driven in (DRIVEN_BY_FUNSCRIPT, DRIVEN_BY_NOTHING, DRIVEN_BY_AUTO):
            assert all(c.dim for c in controls(0, 0, _hud(driven=driven)))
        assert not all(c.dim for c in controls(0, 0, _hud(driven=DRIVEN_BY_ROBOT_HAND)))


class TestSwitchedOff:
    """With the OSR2 off nothing here is being sent, so no part of the readout may
    look live: not the trace, not the bars, not the numbers, and not the marker
    that was still bobbing after the trace had stopped."""

    @staticmethod
    def _colors(hud: DriveHud) -> set[tuple[int, int, int]]:
        rgb = _rendered(hud).astype(int)[:, :, :3]
        return {tuple(pixel) for row in rgb for pixel in row} - {(0, 0, 0)}

    def test_no_part_of_it_is_left_in_the_motion_s_blue(self):
        assert BLUE not in self._colors(_hud(driven=DRIVEN_BY_NOTHING))
        assert BLUE in self._colors(_hud(driven=DRIVEN_BY_ROBOT_HAND))

    def test_the_bars_go_gray_with_everything_else(self):
        """A live blue level beside a dead control says the level is doing
        something."""
        off = _rendered(_hud(driven=DRIVEN_BY_NOTHING, waveform=()))
        bar = {c.command: c.rect for c in controls(PAD, PAD, _hud())}["robot_hand_speed_up"]
        row = off.astype(int)[bar[1] + bar[3] // 2, PAD:PAD + SECTION_W, :3]

        assert not ((row[:, 2] > 150) & (row[:, 0] < 120)).any()

    def test_the_numbers_go_gray_too(self):
        """They read as the live value of a motion otherwise.

        Read off the number's own pixels — the ones that move when the number does,
        under the bar that moves with it as well — rather than off the section's set
        of colors.  At this size the digits are all edge: no pixel of them lands on
        the ink exactly, so a set of colors never saw them at all.
        """
        _x, bar_y, _w, bar_h = next(track.rect for track in tracks(PAD, PAD, _hud())
                                    if track.axis == SPEED)
        muted = max(TEXT_MUTED)

        def brightest_digit(driven: str) -> int:
            fifty = _rendered(_hud(driven=driven, speed=50, waveform=()))
            fifty_one = _rendered(_hud(driven=driven, speed=51, waveform=()))
            digits = (fifty != fifty_one).any(axis=2)
            digits[:bar_y + bar_h] = False
            return int(fifty[digits][:, :3].max())

        assert brightest_digit(DRIVEN_BY_ROBOT_HAND) > muted  # brighter than its own key
        assert brightest_digit(DRIVEN_BY_NOTHING) < muted  # and now darker than it

    def test_the_position_marker_is_not_left_white(self):
        """It bobbed on: Genau keeps publishing a position it cannot know is going
        nowhere, and a dot still moving is the last thing on a stopped readout
        claiming to be live."""
        off = _rendered(_hud(driven=DRIVEN_BY_NOTHING, waveform=()))
        trace_x = next(t.rect for t in tracks(PAD, PAD, _hud()) if t.axis == CENTER)[0]
        edge = off.astype(int)[:, trace_x - 3:trace_x - 1, :3]

        assert not (edge > 200).all(axis=2).any()


class TestDimmedForTheScript:
    """A funscript's turn leaves the controls in place — removing them resized
    the panel and shifted the trace at every handoff — but nothing on them may
    look live: levels, numbers and marks all drop to the faint disabled gray."""

    @staticmethod
    def _colors(hud: DriveHud) -> set[tuple[int, int, int]]:
        rgb = _rendered(hud).astype(int)[:, :, :3]
        return {tuple(pixel) for row in rgb for pixel in row} - {(0, 0, 0)}

    def test_no_level_is_left_in_the_motion_s_blue(self):
        """The bars stayed bright blue through the script's stretch, which is
        what made the dimmed marks beside them read as merely decorative."""
        assert BLUE not in self._colors(_hud(driven=DRIVEN_BY_FUNSCRIPT))
        assert BLUE in self._colors(_hud(driven=DRIVEN_BY_ROBOT_HAND))

    def test_the_dimmed_marks_are_dark_not_translucent(self):
        """"Very dimmed" is the ask, and the first try got it backwards: muted
        ink at part alpha let the video beneath shine through, so the "disabled"
        controls glowed bright white.  Disabled ink is a dark gray laid down
        opaque — darker than the muted gray a live readout's key labels wear —
        so it reads as switched off over any video."""
        dimmed = _rendered(_hud(driven=DRIVEN_BY_FUNSCRIPT))
        live = _rendered(_hud(driven=DRIVEN_BY_ROBOT_HAND))
        x, y, w, _h = controls(PAD, PAD, _hud(driven=DRIVEN_BY_FUNSCRIPT))[0].rect
        top_middle = (y, x + w // 2)

        assert dimmed[top_middle][3] == 255              # opaque: nothing shines through
        assert tuple(dimmed[top_middle][:3]) == DISABLED_INK[:3]
        assert max(DISABLED_INK[:3]) < min(TEXT_MUTED)      # darker than muted ink
        assert tuple(live[top_middle][:3]) == TEXT_PRIMARY


class TestSmoothTrace:
    """Pillow's line has no antialiasing of its own: drawn at panel size the
    wave was a hard-edged pixel staircase, and at low amplitude it scrolled as
    chunks.  Supersampled and scaled back down, the edges come back as
    intensity ramps and the motion as quarter-pixel steps."""

    def test_the_line_s_edges_ramp_instead_of_stepping(self):
        rgb = _rendered(_hud(driven=DRIVEN_BY_ROBOT_HAND)).astype(int)[:, :, :3]
        blue_family = {
            tuple(pixel) for row in rgb for pixel in row
            if pixel[2] > pixel[0] + 20 and pixel[2] > pixel[1] + 20
        }

        # A hard-edged line produced exactly one blue; the ramps produce many.
        assert len(blue_family) > 5

    def test_the_knot_shift_slides_the_scripts_line(self):
        """The script's drawing is fixed; the fraction of a knot the playhead
        sits past its grid point translates the drawn line."""
        still = _rendered(_hud(driven=DRIVEN_BY_FUNSCRIPT, slide=0.0, edge=0.5))
        slid = _rendered(_hud(driven=DRIVEN_BY_FUNSCRIPT, slide=0.5, edge=0.5))

        assert not np.array_equal(still, slid)

    def test_the_live_motion_slides_on_the_same_shift_as_everything_else(self):
        """One convention for every run.  The composed trace reads the live
        motion at fixed sample TIMES now — the values compensate the publish's
        own advance — so the painter's one shift is what slides the whole line,
        blue included.  The old per-run exemption, kept after the reads
        changed, made the blue and its neighbors disagree by the slide at
        every seam between them."""
        still = _rendered(_hud(driven=DRIVEN_BY_ROBOT_HAND, slide=0.0, edge=0.5))
        slid = _rendered(_hud(driven=DRIVEN_BY_ROBOT_HAND, slide=0.5, edge=0.5))

        assert not np.array_equal(still, slid)


class TestBorder:
    def test_the_trace_s_edge_is_opaque_so_it_reads_the_same_over_anything(self):
        """At part strength the video showed through it, so one quiet gray line
        read as a bright thick one over the drawing and a thin dark one over the
        letterbox — the same border looking like two."""
        hud = _hud()
        x, y, w, _h = next(t.rect for t in tracks(PAD, PAD, hud) if t.axis == CENTER)
        alpha = _rendered(hud)[..., 3]

        assert (alpha[y, x:x + w] == 255).all()


class TestRuns:
    """One line, two drivers: the span runs forward, so a handoff that has not
    happened yet is inside it."""

    def test_with_no_marks_the_whole_line_belongs_to_whoever_has_it(self):
        hud = _hud(driven=DRIVEN_BY_FUNSCRIPT)

        assert hud.runs == ((0, len(hud.waveform) - 1, DRIVEN_BY_FUNSCRIPT),)

    def test_consecutive_runs_share_a_point_so_the_line_does_not_break(self):
        hud = _hud(segments=((0, DRIVEN_BY_FUNSCRIPT), (40, DRIVEN_BY_ROBOT_HAND)))
        first, second = hud.runs

        assert (first[1], second[0]) == (40, 40)

    def test_each_run_is_drawn_in_its_own_driver_s_color(self):
        hud = _hud(segments=((0, DRIVEN_BY_FUNSCRIPT), (40, DRIVEN_BY_ROBOT_HAND)))
        rgb = _rendered(hud).astype(int)[:, :, :3]
        colors = {tuple(pixel) for row in rgb for pixel in row}

        assert {GREEN, BLUE} <= colors

    def test_the_neutral_buffer_wears_the_family_s_light_gray(self):
        """The stretch belonging to neither driver is neither green nor blue —
        a light gray between the script's turn and the motion's."""
        hud = _hud(segments=((0, DRIVEN_BY_FUNSCRIPT), (30, DRIVEN_BY_NEUTRAL),
                             (50, DRIVEN_BY_ROBOT_HAND)))
        x, y, w, h = next(t.rect for t in tracks(PAD, PAD, hud) if t.axis == CENTER)
        pitch = (w - 1) / (len(hud.waveform) - 1)
        neutral = _rendered(hud).astype(int)[y:y + h, x + round(32 * pitch):x + round(48 * pitch), :3]

        assert (np.abs(neutral - BORDER_DEFAULT).max(axis=2) <= 20).any()


class TestPublishedSpan:
    def test_the_trace_s_span_travels_with_it(self, tmp_path):
        """The Main Funestra samples a funscript over the same stretch Genau's motion covers,
        and has nowhere else to learn what that is — two spans would make a
        handoff look like a jump."""
        path = tmp_path / "genau_drive.txt"
        publish_drive(path, _hud(trace_seconds=7.5))

        assert read_drive(path).trace_seconds == 7.5

    def test_a_file_from_before_it_was_published_keeps_the_default(self, tmp_path):
        path = tmp_path / "genau_drive.txt"
        publish_drive(path, _hud())
        text = path.read_text(encoding="utf-8")
        path.write_text(
            "\n".join(line for line in text.splitlines()
                      if not line.startswith("trace_seconds")),
            encoding="utf-8")

        assert read_drive(path).trace_seconds == DriveHud.trace_seconds
