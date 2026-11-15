from __future__ import annotations

import numpy as np
import pytest
from main_hud_rows import RowLights, main_hud_rows, motion_rows
from shared_ui import colors
from shared_ui.app_icon import LETTERS
from shared_ui.palette import (
    BG_PRIMARY,
    BLUE,
    GREEN,
    MAGENTA,
    TEXT_MUTED,
)
from shared_ui.spacing import GAP_SMALL
from shared_ui.type_scale import SIZE_TINY

from funestra.drive_layout import AMPLITUDE, CENTER, MAX_INTENSITY, SPEED
from funestra.geometry import Rect
from funestra.hud import (
    TOOLTIP_PAD,
    load_font,
    text_width,
)
from funestra.hud_button import Button
from funestra.hud_corners import HudPlace
from funestra.hud_icons import BROKER_ICON, shared_icon
from funestra.hud_minimize import minimize_command
from funestra.hud_osr2 import COLORS as _OSR2_COLORS
from funestra.hud_osr2 import LABELS as _OSR2_LABELS
from funestra.hud_placement import HudCorner
from funestra.hud_title import PLAYBACK_SPEED_LABEL
from funestra.main_hud import (
    BUTTON,
    OSR2_DRIVING,
    OSR2_PARKED,
    OSR2_RETRACTED,
    ROW_LABEL_W,
    MainHudModel,
    aim_row,
    osr2_controls,
)
from funestra.main_hud_painter import (
    _PAD,
    MARGIN,
    MainHud,
    hud_xy,
    osr2_line_on,
)
from funestra.main_hud_painter import _PAD as PAD
from funestra.modes import LengthMode, MainMode, Osr2State
from funestra.osr2_part_painter import Osr2PartPainter
from funestra.osr2_visualizer import (
    CONTROL_TIPS,
    DRIVEN_BY_NEUTRAL,
    DriveHud,
    trace_ink,
)
from funestra.robot_hand import POSITION_MAX

MIXED, FULL, CLIPS = LengthMode.MIXED, LengthMode.FULL, LengthMode.CLIPS


def _drive(offset: float = 0.0, **over) -> DriveHud:
    return DriveHud(speed=50, amplitude=80, center=50, shape="sine",
                    waveform=tuple(0.5 + 0.4 * np.sin(i / 6 + offset) for i in range(80)),
                    **over)


def _pill(painter: Osr2PartPainter) -> str:
    return osr2_line_on(painter._painted[0]).state


def _rect_of(painter: Osr2PartPainter, command: str) -> Rect:
    return next(rect for rect, button in painter.buttons if button.command == command)


def _over(painter: Osr2PartPainter, command: str) -> tuple[int, int]:
    bx, by, bw, bh = _rect_of(painter, command)
    left, top = hud_xy()
    return left + bx + bw // 2, top + by + bh // 2


class TestPainter:


    def test_a_tooltip_longer_than_the_hud_is_wide_stays_on_the_hud(self):
        painter = Osr2PartPainter()
        hud = MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, locked=False,
                                              osr2_rows=main_hud_rows()))
        plain = _rgb(painter.bgra(hud))
        tiny = load_font(8)
        (x, y, w, h), _button = max(
            ((rect, button) for rect, button in painter.buttons if button.tooltip),
            key=lambda pair: text_width(tiny, pair[1].tooltip))
        tipped = _rgb(Osr2PartPainter().bgra(hud, hover=(x + w // 2, y + h // 2)))

        rows, cols = np.nonzero((tipped != plain).any(axis=2))
        one_line_height = sum(tiny.getmetrics()) + 2 * TOOLTIP_PAD

        assert len(cols)
        assert cols.max() < plain.shape[1] - 1
        assert rows.max() - rows.min() + 1 > one_line_height

    def test_the_visualizer_grows_the_hud(self):
        painter = Osr2PartPainter()
        plain = painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO))).shape[0]
        driving = Osr2PartPainter().bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO), drive=_drive())).shape[0]

        assert driving > plain

    def test_the_dot_does_not_shift_the_words_around(self):
        painter = Osr2PartPainter()

        lit = painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, active=True)))
        idle = Osr2PartPainter().bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, active=False)))

        assert lit.shape == idle.shape

    def test_an_unchanged_hud_is_not_repainted(self):
        painter = Osr2PartPainter()
        hud = MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO))

        assert painter.bgra(hud) is painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO)))

    def test_the_visualizers_arrows_are_hit_targets_even_though_it_draws_them(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO), drive=_drive()))

        actions = {b.command for _rect, b in painter.buttons}
        for action in ("robot_hand_amplitude_up", "robot_hand_center_down", "robot_hand_speed_up"):
            assert action in actions

    def test_the_osr2_state_is_shown(self):
        painter = Osr2PartPainter()
        bgra = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.FUNSCRIPT)))
        rgb = _rgb(bgra)
        green = (rgb[:, :, 1] > 130) & (rgb[:, :, 0] < 110) & (rgb[:, :, 2] < 110)
        assert green.any()

    def _busiest_shade(self, command: str, model: MainHudModel):
        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(MainHud(main_hud_model=model)))
        bx, by, bw, bh = _rect_of(painter, command)
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)
        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)
        return tuple(shades[counts.argmax()]), pixels

    def test_the_mode_you_are_in_lights_the_familys_blue_since_a_lighter_ground_could_not_be_found_at_a_glance(self):
        shade, pixels = self._busiest_shade(
            "main_kino_activate",
            MainHudModel(main_mode=MainMode.KINO, osr2_rows=main_hud_rows("kino")))

        assert shade == BLUE
        green = (pixels[:, :, 1] > 130) & (pixels[:, :, 0] < 110) & (pixels[:, :, 2] < 110)
        assert not green.any()

    def test_an_ordinary_toggle_that_is_on_fills_the_familys_blue_since_the_active_gray_could_not_be_told_from_off(self):
        blue = BLUE
        shade, _pixels = self._busiest_shade(
            "robot_hand_toggle_learned",
            MainHudModel(main_mode=MainMode.GENAU,
                         osr2_rows=motion_rows(learned=True)))

        assert shade == blue

    def test_a_choice_the_funestra_is_holding_but_not_applying_fills_the_gray_as_a_compilation_sets_the_browse_order_and_length_aside_and_restores_them(self):
        gray = (colors.BG_BUTTON_ACTIVE.red(), colors.BG_BUTTON_ACTIVE.green(),
                colors.BG_BUTTON_ACTIVE.blue())
        shade, _pixels = self._busiest_shade(
            "main_shuffle",
            MainHudModel(main_mode=MainMode.KINO, latest=False,
                         osr2_rows=main_hud_rows(lights=RowLights(remembered=True))))

        assert shade == gray

    def test_a_control_at_rest_still_carries_the_familys_thin_edge(self):
        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2_rows=main_hud_rows()))))
        (bx, by, bw, bh), _b = next(
            (rect, b) for rect, b in painter.buttons
            if b.command and b.command != "main_kino_activate")
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)
        muted = TEXT_MUTED

        edge = pixels[0, 4:bw - 4]
        assert (abs(edge - np.array(muted)).max(axis=1) <= 2).any()

    def test_the_broker_wears_the_face_it_had_on_the_dashboard_since_it_acts_on_the_app_s_service_and_not_on_a_funestra(self):
        for broker, fill in ((True, (48, 128, 224)), (False, (255, 60, 60))):
            pixels = self._broker_pixels(broker)

            assert tuple(pixels[pixels.shape[0] // 2, 2]) == fill
            assert (pixels == np.array((200, 80, 160), dtype=pixels.dtype)).all(axis=2).any()

    def test_a_control_that_stands_for_an_app_wears_that_apps_mark(self):
        for action, grid in (("broker_panel", LETTERS["B"]),):
            pixels = self._button_pixels(action, MainHudModel(
                main_mode=MainMode.KINO, osr2_rows=main_hud_rows(lights=RowLights(favorites=True)),
                osr2_controls=osr2_controls(broker_running=True)))
            magenta = (pixels == np.array((200, 80, 160), dtype=pixels.dtype)).all(axis=2)
            ys, xs = np.nonzero(magenta)
            cell = (xs.max() - xs.min() + 1) / 5
            drawn = [
                "".join("#" if magenta[int(ys.min() + (r + 0.5) * cell),
                                       int(xs.min() + (c + 0.5) * cell)] else "."
                        for c in range(5))
                for r in range(5)
            ]

            assert drawn == list(grid), action

    def test_minimize_draws_the_familys_minus_rather_than_leaving_it_to_a_font_counting_only_ink_inside_the_border_and_brighter_than_the_ground(self):
        pixels = self._button_pixels(
            "main_minimize", MainHudModel(main_mode=MainMode.KINO, osr2_rows=main_hud_rows()))
        inside = pixels[2:-2, 2:-2]
        ys, xs = np.nonzero((inside > 150).all(axis=2))

        assert len(ys), "the minimize button drew no mark at all"
        assert xs.max() - xs.min() > ys.max() - ys.min()

    @staticmethod
    def _button_pixels(command: str, model: MainHudModel) -> np.ndarray:
        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(MainHud(main_hud_model=model)))
        bx, by, bw, bh = _rect_of(painter, command)
        return rgb[by:by + bh, bx:bx + bw]

    def _broker_pixels(self, broker: bool) -> np.ndarray:
        return self._button_pixels("broker_panel", MainHudModel(
            main_mode=MainMode.KINO, osr2_controls=osr2_controls(broker_running=broker)))

    def test_favorites_is_the_one_lit_control_that_stays_green_since_green_here_belongs_to_the_favorites_and_the_funscripts(self):
        pixels = self._button_pixels(
            "main_favorites",
            MainHudModel(main_mode=MainMode.KINO,
                         osr2_rows=main_hud_rows(lights=RowLights(favorites=True)))).astype(int)

        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)
        assert tuple(shades[counts.argmax()]) == (48, 160, 48)

    def test_only_the_lock_and_f_mode_light_green_since_green_here_belongs_to_the_favorites_and_the_funscripts(self):
        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(MainHud(main_hud_model=MainHudModel(
            main_mode=MainMode.KINO,
            osr2_rows=main_hud_rows(lights=RowLights(locked=True, favorites=True, remembered=True, recording=True),
                               enhanced=True)))))

        def dominant(rect) -> tuple[int, ...]:
            bx, by, bw, bh = rect
            shades, counts = np.unique(rgb[by:by + bh, bx:bx + bw].reshape(-1, 3), axis=0, return_counts=True)
            return tuple(int(v) for v in shades[counts.argmax()])

        lit = {button.command for rect, button in painter.buttons if button.lit}
        green = {button.command for rect, button in painter.buttons if dominant(rect) == GREEN}
        assert lit > {"main_lock", "main_favorites", "main_kino_activate"}
        assert green == {"main_lock", "main_favorites"}

    def test_the_enhanced_filter_wears_yellow_off_and_on_the_yellow_of_the_plus_origenerator_marks_an_enhanced_image_with(self):
        yellow = (255, 200, 120)
        off = self._button_pixels("genau_filter_enhanced", MainHudModel(
            main_mode=MainMode.GENAU, osr2_rows=main_hud_rows("genau", enhanced=False)))
        on = self._button_pixels("genau_filter_enhanced", MainHudModel(
            main_mode=MainMode.GENAU, osr2_rows=main_hud_rows("genau", enhanced=True)))

        assert (np.abs(off.astype(int) - yellow).sum(axis=2) < 30).any()
        shades, counts = np.unique(on.astype(int).reshape(-1, 3), axis=0,
                                   return_counts=True)
        assert tuple(shades[counts.argmax()]) == yellow

    def test_the_slab_is_the_canvas_gray_unless_a_host_asks_for_another(self):
        default = _rgb(Osr2PartPainter().bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU))))
        asked = _rgb(Osr2PartPainter().bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU), ground=(40, 40, 40))))

        assert tuple(default[3, 3]) == BG_PRIMARY
        assert tuple(asked[3, 3]) != BG_PRIMARY
        assert asked[3, 3].min() > default[3, 3].min()

    def test_the_ground_is_part_of_what_the_repaint_cache_compares(self):
        painter = Osr2PartPainter()
        first = _rgb(painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU))))[3, 3]
        second = _rgb(painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU),
                                              ground=(40, 40, 40))))[3, 3]

        assert tuple(first) != tuple(second)

    def test_a_lit_marks_ink_stays_white_over_a_colored_fill_since_a_mark_that_changed_color_read_as_a_different_button(self):
        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO,
                                            osr2_rows=main_hud_rows(lights=RowLights(recording=True))))))
        bx, by, bw, bh = _rect_of(painter, "main_player_record_tap")
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)

        assert tuple(pixels[bh // 2, 2]) == (255, 60, 60)
        assert (pixels > 240).all(axis=2).any()


class TestPresses:
    @staticmethod
    def _painted(mode: MainMode = MainMode.KINO) -> Osr2PartPainter:
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=mode,
                                                    osr2_rows=main_hud_rows(mode))))
        return painter

    def test_a_press_on_a_button_carries_that_buttons_command(self):
        painter = self._painted()

        assert painter.press_at(*_over(painter, "main_next")) == "main_next"

    def test_a_press_that_missed_every_button_carries_nothing(self):
        assert self._painted().press_at(2000, 2000) == ""

    def test_a_dimmed_button_posts_nothing_but_the_press_is_still_on_the_hud(self):
        painter = self._painted()
        over = _over(painter, "main_player_cycle_version")

        assert painter.press_at(*over) == ""
        assert painter.covers(*over)

    def test_the_hud_under_a_press_ends_where_its_painting_does(self):
        painter = Osr2PartPainter()
        height, width = painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO))).shape[:2]
        left, top = hud_xy()

        assert painter.covers(left, top)
        assert painter.covers(left + width - 1, top + height - 1)
        assert not painter.covers(left + width, top)
        assert not painter.covers(left, top + height)
        assert not painter.covers(left - 1, top - 1)

    def test_nothing_is_under_a_press_before_the_hud_is_first_painted(self):
        left, top = hud_xy()

        assert not Osr2PartPainter().covers(left, top)

    def test_the_huds_own_corner_is_not_read_as_the_windows(self):
        painter = self._painted()
        bx, by, _bw, _bh = _rect_of(painter, "main_prev")

        assert painter.press_at(bx, by) == ""

    def test_a_visualizers_arrow_press_reaches_genau(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND), drive=_drive()))

        assert painter.press_at(*_over(painter, "robot_hand_amplitude_up")) == "robot_hand_amplitude_up"

    @pytest.mark.parametrize("who_has_it", [Osr2State.FUNSCRIPT, Osr2State.AUTO, Osr2State.OFF])
    def test_the_visualizers_controls_are_dead_while_anything_but_the_robot_hand_has_the_device_since_a_press_there_once_woke_genau_against_the_funscript(self, who_has_it):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=who_has_it), drive=_drive()))

        over = _over(painter, "robot_hand_amplitude_up")
        the_visualizers = [b for _rect, b in painter.buttons if b.command.startswith("robot_hand_")]
        assert painter.press_at(*over) == ""
        assert the_visualizers
        assert all(b.dim for b in the_visualizers)

    def test_the_cursor_over_a_button_is_reported_in_hud_coordinates(self):
        painter = self._painted()
        mx, my = _over(painter, "main_next")
        left, top = hud_xy()

        assert painter.hover_at(mx, my) == (mx - left, my - top)

    def test_a_button_with_no_tooltip_still_answers_the_pointer(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(osr2_rows=((Button("go_kino", "Kino", ""),),))))
        mx, my = _over(painter, "go_kino")
        left, top = hud_xy()

        assert painter.hover_at(mx, my) == (mx - left, my - top)


class TestThePointer:
    @staticmethod
    def _hud(corner: HudCorner = HudCorner.UPPER_LEFT) -> MainHud:
        return MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, hud_corner=corner,
                                               osr2_rows=main_hud_rows(MainMode.KINO)))

    @staticmethod
    def _ground(rgb: np.ndarray, painter: Osr2PartPainter, command: str) -> int:
        x, y, _w, h = _rect_of(painter, command)
        return int(rgb[y + h // 2, x + 2].sum())

    def test_the_button_under_the_pointer_draws_lighter(self):
        painter = Osr2PartPainter()
        at_rest = _rgb(painter.bgra(self._hud()))

        painter.motion(*_over(painter, "main_next"))
        under_the_pointer = _rgb(painter.bgra(self._hud()))

        assert (self._ground(under_the_pointer, painter, "main_next")
                > self._ground(at_rest, painter, "main_next"))

    def test_the_pointer_moving_off_the_hud_puts_the_button_back(self):
        painter = Osr2PartPainter()
        at_rest = _rgb(painter.bgra(self._hud()))
        painter.motion(*_over(painter, "main_next"))
        painter.bgra(self._hud())

        painter.motion(-1, -1)

        assert (_rgb(painter.bgra(self._hud())) == at_rest).all()

    def test_the_pointer_leaving_the_window_puts_the_button_back(self):
        painter = Osr2PartPainter()
        at_rest = _rgb(painter.bgra(self._hud()))
        painter.motion(*_over(painter, "main_next"))
        painter.bgra(self._hud())

        painter.leave()

        assert (_rgb(painter.bgra(self._hud())) == at_rest).all()

    def test_a_hud_sent_to_another_corner_forgets_where_the_pointer_was(self):
        painter = Osr2PartPainter()
        painter.bgra(self._hud())
        painter.motion(*_over(painter, "main_next"))

        moved = _rgb(painter.bgra(self._hud(HudCorner.UPPER_RIGHT)))

        assert (moved == _rgb(Osr2PartPainter().bgra(self._hud(HudCorner.UPPER_RIGHT)))).all()


class TestDrags:
    @staticmethod
    def _painted(osr2: Osr2State = Osr2State.ROBOT_HAND) -> Osr2PartPainter:
        painter = Osr2PartPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=osr2,
                                 osr2_rows=main_hud_rows()),
            drive=_drive()))
        return painter

    @staticmethod
    def _bar(painter: Osr2PartPainter, axis: str):
        return next(track for track in painter.tracks if track.axis == axis)

    @staticmethod
    def _at(track, along: float) -> tuple[int, int]:
        x, y, w, h = track.rect
        left, top = hud_xy()
        if track.axis in (SPEED, MAX_INTENSITY):
            return left + x + round(along * (w - 1)), top + y + h // 2
        return left + x + w // 2, top + y + round((1 - along) * (h - 1))

    def test_a_press_along_the_speed_bar_sets_the_speed(self):
        painter = self._painted()

        point = self._at(self._bar(painter, SPEED), 1.0)
        assert painter.press_at(*point) == "robot_hand_speed_100"

    def test_a_press_in_the_trace_moves_the_motion_s_center(self):
        painter = self._painted()

        point = self._at(self._bar(painter, CENTER), 1.0)
        assert painter.press_at(*point) == "robot_hand_center_100"

    def test_a_press_up_the_amplitude_bar_sets_how_far_the_motion_reaches(self):
        painter = self._painted()

        point = self._at(self._bar(painter, AMPLITUDE), 1.0)
        assert painter.press_at(*point) == "robot_hand_amp_100"

    def test_the_bar_a_press_took_hold_of_keeps_the_drag(self):
        painter = self._painted()
        speed = self._bar(painter, SPEED)
        painter.press_at(*self._at(speed, 1.0))

        assert painter.holding is True
        left, _top = hud_xy()
        assert painter.drag_to(left + speed.rect[0] - 500, 0) == "robot_hand_speed_0"
        assert painter.drag_to(*self._at(speed, 1.0)) == "robot_hand_speed_100"

    def test_a_drag_says_nothing_while_the_level_under_it_has_not_moved(self):
        painter = self._painted()
        speed = self._bar(painter, SPEED)
        painter.press_at(*self._at(speed, 1.0))

        assert painter.drag_to(*self._at(speed, 1.0)) == ""

    def test_letting_go_ends_the_drag(self):
        painter = self._painted()
        painter.press_at(*self._at(self._bar(painter, SPEED), 0.0))

        painter.release()

        assert painter.holding is False
        assert painter.drag_to(*self._at(self._bar(painter, SPEED), 1.0)) == ""

    def test_a_press_on_a_button_leaves_no_bar_still_latched(self):
        painter = self._painted()
        painter.press_at(*self._at(self._bar(painter, SPEED), 0.0))

        painter.press_at(*_over(painter, "main_next"))

        assert painter.holding is False

    def test_the_bars_are_dead_while_a_funscript_has_the_device(self):
        painter = self._painted(osr2=Osr2State.FUNSCRIPT)

        point = self._at(self._bar(painter, SPEED), 1.0)
        assert painter.press_at(*point) == ""
        assert painter.holding is False

    def test_a_press_along_the_max_intensity_sets_it_and_the_drag_goes_on_setting_it(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND,
                                 max_intensity=50),
            drive=_drive()))
        max_intensity = self._bar(painter, MAX_INTENSITY)

        assert painter.press_at(*self._at(max_intensity, 1.0)) == "max_intensity_100"
        assert painter.drag_to(*self._at(max_intensity, 0.0)) == "max_intensity_0"

    def test_there_are_no_bars_at_all_where_nothing_is_driving(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO)))

        assert painter.tracks == []

    def test_each_bar_names_what_it_sets_on_hover(self):
        painter = self._painted()
        left, top = hud_xy()

        for axis in (SPEED, CENTER, AMPLITUDE):
            x, y, w, h = self._bar(painter, axis).rect
            assert painter.hover_at(left + x + w // 2, top + y + h // 2) is not None


class TestDeclaredRows:
    def test_the_rows_a_source_declares_are_what_is_drawn(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(
            osr2_rows=((Button("go_on", "⏭", "On to the next"),),
                  (Button("", "Pace", "", width=40),
                   Button("slower", shared_icon("minus"), "Slower", group_break=True))),
            osr2_controls=(Button("wake_broker", BROKER_ICON, "Wake it", warn=True),),
        )))

        assert [button.command for _rect, button in _declared(painter)] == [
            "go_on", "", "slower", "wake_broker"]

    def test_a_hud_that_declares_no_buttons_draws_none(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO)))

        assert _declared(painter) == []

    def test_with_no_controls_on_its_line_the_osr2_label_starts_the_line(self):
        rgb = _rgb(Osr2PartPainter().bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU))))
        height = rgb.shape[0]
        line = rgb[height - PAD - BUTTON:height - PAD, 3:].astype(int)
        inked = (np.abs(line - np.array(BG_PRIMARY)).max(axis=2) > 40).any(axis=0)

        assert 3 + np.nonzero(inked)[0].min() <= PAD + 2


class TestAConsoleAnotherFunestraTookTheOsr2From:
    @staticmethod
    def _painted(*, has_osr2: bool) -> tuple[Osr2PartPainter, np.ndarray]:
        painter = Osr2PartPainter()
        bgra = painter.bgra(MainHud(
            main_hud_model=MainHudModel(
                main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND,
                osr2_rows=((Button("main_take_osr2", "OSR2", "Take the OSR2"),),),
                osr2_controls=(Button("broker_panel", BROKER_ICON, "Broker"),),
                has_osr2=has_osr2),
            drive=_drive()))
        return painter, bgra

    def test_draws_the_rows_it_was_handed_and_neither_the_osr2_line_nor_the_visualizer(self):
        painter, _bgra = self._painted(has_osr2=False)

        assert [button.command for _rect, button in _declared(painter)] == ["main_take_osr2"]
        assert painter.tracks == []

    def test_is_shorter_by_the_line_and_the_visualizer(self):
        _with, holding = self._painted(has_osr2=True)
        _without, taken = self._painted(has_osr2=False)

        assert taken.shape[0] < holding.shape[0]


class TestPlaybackSpeed:
    def test_the_painter_writes_the_hosts_numbers_into_the_read_outs_that_name_them(self):
        def visualizers(hud: MainHud) -> list[str]:
            painter = Osr2PartPainter()
            painter.bgra(hud)
            return [button.icon for _rect, button in painter.buttons if button.host_value]

        assert visualizers(MainHud(main_hud_model=MainHudModel(
            main_mode=MainMode.KINO, osr2_rows=main_hud_rows("kino"), playback_speed=1.75))) == ["1.75\u00d7"]
        assert visualizers(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2_rows=main_hud_rows("genau")),
            drive=_drive(advance_interval=7))) == ["7s"]


class TestPlacement:
    def test_the_hud_sits_in_the_top_left_corner(self):
        assert hud_xy() == (8, 8)


def _rgb(bgra: np.ndarray) -> np.ndarray:
    return bgra[:, :, [2, 1, 0]]


class TestTraceSources:
    @staticmethod
    def _painted(mode: MainMode, osr2: Osr2State, drive: DriveHud | None = None) -> Osr2PartPainter:
        painter = Osr2PartPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=mode, osr2=osr2), drive=drive or _drive()))
        return painter

    @staticmethod
    def _drawn(mode: str, osr2: str, drive: DriveHud | None = None):
        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=mode, osr2=osr2),
            drive=drive or _drive()))).astype(int)
        return painter, {tuple(pixel) for row in rgb for pixel in row}

    def test_genau_driving_leaves_the_visualizer_pressable(self):
        painter = self._painted(MainMode.KINO, Osr2State.ROBOT_HAND)

        assert painter.tracks
        assert not any(t.dim for t in painter.tracks)

    def test_a_funscript_driving_dims_every_control_but_keeps_the_trace_since_adjusting_a_motion_genau_is_not_sending_once_woke_it_against_the_funscript(self):
        painter = self._painted(MainMode.KINO, Osr2State.FUNSCRIPT)

        assert all(t.dim for t in painter.tracks)
        assert painter.tracks

    def test_the_device_running_itself_draws_its_own_swing_and_names_it(self):
        painter, colors = self._drawn("genau", "auto")

        assert _pill(painter) == "auto"
        assert all(t.dim for t in painter.tracks)
        assert MAGENTA in colors

    def test_the_device_running_itself_wins_over_a_composed_handoff(self):
        painter, colors = self._drawn(
            "kino", "auto",
            drive=_drive(segments=((0, "robot_hand"), (40, "funscript"))))

        assert _pill(painter) == "auto"
        assert MAGENTA in colors

    def test_the_hud_keeps_its_size_whoever_has_the_device(self):
        genau_turn = self._painted(MainMode.KINO, Osr2State.ROBOT_HAND)
        funscript_turn = self._painted(MainMode.KINO, Osr2State.FUNSCRIPT)

        assert genau_turn._image.size == funscript_turn._image.size


class TestEveryMainHudPaints:
    def test_every_mode_and_driver_combination_paints(self):
        wave = tuple(0.5 for _ in range(len(DriveHud().waveform) or 80))
        segments = ((0, "robot_hand"), (30, "neutral"), (50, "funscript"))
        for mode in MainMode:
            for driven in ("robot_hand", "funscript", "neutral", "nothing"):
                hud = MainHud(
                    main_hud_model=MainHudModel(main_mode=mode, osr2=Osr2State.ROBOT_HAND,
                                         osr2_rows=main_hud_rows(mode),
                                         osr2_controls=osr2_controls(broker_running=True)),
                    drive=DriveHud(waveform=wave, driven=driven,
                                   segments=segments))
                Osr2PartPainter().rgba(hud)

    def test_with_a_composed_trace_on_the_hud_the_pill_reads_the_trace_s_own_answer_to_who_has_the_device(self):
        wave = tuple(0.5 for _ in range(80))
        painter = Osr2PartPainter()
        hud = MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND),
            drive=DriveHud(waveform=wave, driven="neutral",
                           segments=((0, "robot_hand"), (30, "neutral"))))
        painter.rgba(hud)

        assert _pill(painter) == "buffer"

    def test_the_pill_is_read_off_the_hud_in_hand_never_off_the_one_painted_before_it(self):
        painter = Osr2PartPainter()
        painter.rgba(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND),
            drive=_drive(driven="neutral", segments=((0, "robot_hand"), (30, "neutral")))))
        with_no_trace = MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND))

        assert osr2_line_on(with_no_trace).state == Osr2State.ROBOT_HAND


class TestHolds:
    @staticmethod
    def _hud(mode: str, osr2: str, control: str) -> MainHud:
        wave = tuple(0.5 for _ in range(80))
        return MainHud(
            main_hud_model=MainHudModel(main_mode=mode, osr2=osr2, osr2_control=control),
            drive=DriveHud(waveform=wave, driven="funscript", position=5000,
                           segments=((0, "robot_hand"), (30, "funscript"))))

    def test_the_pill_names_the_hold_whoever_would_have_had_the_device(self):
        painter = Osr2PartPainter()
        for control in (OSR2_PARKED, OSR2_RETRACTED):
            for mode in MainMode:
                for osr2 in ("robot_hand", "funscript"):
                    hud = self._hud(mode, osr2, control)
                    painter.rgba(hud)
                    assert _pill(painter) == control, (mode, osr2)

    def test_the_pill_says_it_in_words(self):
        assert _OSR2_LABELS[OSR2_PARKED] == "Parked"
        assert _OSR2_LABELS[OSR2_RETRACTED] == "Retracted"

    def test_a_held_device_is_drawn_as_driving_would_draw_it_in_gray(self):
        would_drive = _drive(position=4_200, driven="funscript",
                             segments=((0, "robot_hand"), (30, "funscript")))
        for control in (OSR2_PARKED, OSR2_RETRACTED):
            for mode in MainMode:
                painter = Osr2PartPainter()
                painter.rgba(MainHud(
                    main_hud_model=MainHudModel(main_mode=mode, osr2="funscript", osr2_control=control),
                    drive=would_drive))
                drive = painter._painted[0].drive

                assert drive.waveform == would_drive.waveform, (control, mode)
                assert drive.position == would_drive.position, (control, mode)
                assert {who for _start, _end, who in drive.runs} == {DRIVEN_BY_NEUTRAL}, (
                    control, mode)

    def test_a_held_visualizer_holds_still_with_the_device_on(self):
        for control in (OSR2_PARKED, OSR2_RETRACTED):
            painter = Osr2PartPainter()
            main_hud_model = MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND,
                                   osr2_control=control)
            first = painter.bgra(MainHud(main_hud_model=main_hud_model, drive=_drive(0.0))).copy()

            assert np.array_equal(painter.bgra(MainHud(main_hud_model=main_hud_model, drive=_drive(3.0))),
                                  first), control

    def test_a_held_visualizer_cannot_be_pressed(self):
        for control in (OSR2_PARKED, OSR2_RETRACTED):
            painter = Osr2PartPainter()
            painter.rgba(self._hud("genau", "robot_hand", control))

            assert painter._painted[0].drive.driving is False
            assert painter._painted[0].drive.live is True

    def test_the_held_pill_wears_the_held_lines_gray(self):
        for control in (OSR2_PARKED, OSR2_RETRACTED):
            assert _OSR2_COLORS[control] == trace_ink(DRIVEN_BY_NEUTRAL)


class TestAPausedRoom:
    @staticmethod
    def _main_hud(control: str, *, paused: bool, mode: MainMode = MainMode.GENAU) -> MainHudModel:
        return MainHudModel(main_mode=mode, osr2=Osr2State.ROBOT_HAND, osr2_control=control,
                            paused=paused)

    def test_the_line_reads_as_a_parked_ones_does(self):
        def hud(control: str, *, paused: bool) -> np.ndarray:
            return Osr2PartPainter().bgra(MainHud(main_hud_model=self._main_hud(control, paused=paused)))

        paused = hud(OSR2_DRIVING, paused=True)

        assert np.array_equal(paused, hud(OSR2_PARKED, paused=False))
        assert not np.array_equal(paused, hud(OSR2_DRIVING, paused=False))

    @pytest.mark.parametrize("mode", list(MainMode))
    def test_the_visualizers_speed_amp_and_center_buttons_take_presses(self, mode):
        painter = Osr2PartPainter()
        painter.rgba(MainHud(main_hud_model=self._main_hud(OSR2_DRIVING, paused=True, mode=mode),
                                drive=_drive()))

        taken = {command for command in CONTROL_TIPS
                 if painter.press_at(*_over(painter, command)) == command}

        assert taken == set(CONTROL_TIPS)


class TestTheDotIsWhereTheDeviceIs:
    @staticmethod
    def _hud(control: str, *, osr2: str = Osr2State.ROBOT_HAND,
             paused: bool = False) -> MainHud:
        return MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=osr2, osr2_control=control,
                                 paused=paused),
            drive=_drive(0.0, position=6_000))

    @staticmethod
    def _dot(painter: Osr2PartPainter, hud: MainHud) -> int:
        painter.rgba(hud)
        return painter._painted[0].drive.position

    def _held_from(self, control: str):
        clock = [10.0]
        painter = Osr2PartPainter(clock=lambda: clock[0])
        assert self._dot(painter, self._hud(OSR2_DRIVING)) == 6_000

        def at(seconds_after_the_hold: float, *, osr2: str = Osr2State.ROBOT_HAND,
               held: str = control, paused: bool = False) -> int:
            clock[0] = 11.0 + seconds_after_the_hold
            return self._dot(painter, self._hud(held, osr2=osr2, paused=paused))
        return at

    def test_parked_it_waits_out_the_broker_then_sets_down_at_the_bottom_over_a_second(self):
        at = self._held_from(OSR2_PARKED)

        assert at(0.0) == 6_000
        assert at(0.9) == 6_000
        assert 0 < at(1.6) < 6_000
        assert at(2.0) == 0

    def test_retracted_it_slides_to_the_top(self):
        at = self._held_from(OSR2_RETRACTED)

        assert at(0.0) == 6_000
        assert at(1.6) == POSITION_MAX

    def test_in_a_paused_room_it_goes_home_the_way_a_park_takes_it(self):
        at = self._held_from(OSR2_DRIVING)

        assert at(0.0, paused=True) == 6_000
        assert at(0.9, paused=True) == 6_000
        assert 0 < at(1.6, paused=True) < 6_000
        assert at(2.0, paused=True) == 0

    def test_played_again_it_slides_from_home_back_into_the_motion(self):
        at = self._held_from(OSR2_DRIVING)
        at(0.0, paused=True)
        assert at(2.0, paused=True) == 0

        assert at(2.4) == 0
        assert at(2.8) == 6_000

    def test_with_the_device_switched_off_it_stays_where_it_was(self):
        at = self._held_from(OSR2_PARKED)

        assert at(0.0, osr2=Osr2State.OFF) == 6_000
        assert at(2.0, osr2=Osr2State.OFF) == 6_000

    def test_taken_back_it_slides_from_the_held_end_into_the_motion(self):
        at = self._held_from(OSR2_PARKED)
        at(0.0)
        assert at(2.0) == 0

        assert at(2.4, held=OSR2_DRIVING) == 0
        assert 0 < at(2.55, held=OSR2_DRIVING) < 6_000
        assert at(2.8, held=OSR2_DRIVING) == 6_000


class TestNothingDriving:
    _HANDOFF = ((0, "funscript"), (40, "robot_hand"))

    @staticmethod
    def _off(mode: MainMode, offset: float, control: str = OSR2_DRIVING,
             **drive) -> MainHud:
        return MainHud(
            main_hud_model=MainHudModel(main_mode=mode, osr2=Osr2State.OFF, osr2_control=control),
            drive=_drive(offset, **drive))

    @pytest.mark.parametrize("mode", list(MainMode))
    def test_the_trace_stops_where_it_was_when_the_device_went_quiet(self, mode):
        painter = Osr2PartPainter()
        first = painter.bgra(self._off(mode, 0.0)).copy()

        assert np.array_equal(painter.bgra(self._off(mode, 3.0)), first)

    def test_the_switchs_label_gets_room_for_its_words(self):
        painter = Osr2PartPainter()
        painter.rgba(MainHud(main_hud_model=MainHudModel(
            main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND,
            osr2_rows=(aim_row(learned=False, shape="sine", control=OSR2_DRIVING),))))
        label = next(rect for rect, button in painter.buttons if button.icon == "OSR2 control")

        assert label[2] > text_width(load_font(8), "OSR2 control")

    def test_it_moves_again_the_moment_something_is_driving(self):
        painter = Osr2PartPainter()
        still = painter.bgra(self._off(MainMode.GENAU, 0.0)).copy()

        moving = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND), drive=_drive(3.0)))

        assert not np.array_equal(moving, still)

    def test_a_videos_composed_trace_holds_still_in_gray_with_the_device_off(self):
        painter = Osr2PartPainter()
        first = painter.bgra(self._off(
            MainMode.KINO, 0.0, driven="funscript", segments=self._HANDOFF)).copy()

        later = painter.bgra(self._off(
            MainMode.KINO, 3.0, driven="funscript", segments=self._HANDOFF))

        assert {who for _start, _end, who in painter._painted[0].drive.runs} == {"nothing"}
        assert np.array_equal(later, first)

    def test_the_pill_says_off_whoever_a_videos_composed_trace_has_driving(self):
        painter = Osr2PartPainter()
        hud = self._off(MainMode.KINO, 0.0, driven="funscript", segments=self._HANDOFF)
        painter.rgba(hud)

        assert _pill(painter) == "off"

    @pytest.mark.parametrize("control", [OSR2_PARKED, OSR2_RETRACTED])
    def test_held_with_the_device_off_is_the_dim_gray_of_driving_with_it_off(self, control):
        def drawn(control: str):
            return Osr2PartPainter().bgra(self._off(
                MainMode.KINO, 0.0, control=control, position=4_200,
                driven="funscript", segments=self._HANDOFF))

        assert np.array_equal(drawn(control), drawn(OSR2_DRIVING))

    @pytest.mark.parametrize("control", [OSR2_PARKED, OSR2_RETRACTED])
    def test_held_with_the_device_off_holds_still(self, control):
        painter = Osr2PartPainter()
        first = painter.bgra(self._off(MainMode.GENAU, 0.0, control=control)).copy()

        assert np.array_equal(
            painter.bgra(self._off(MainMode.GENAU, 3.0, control=control)), first)

    def test_a_still_visualizer_arriving_as_a_fresh_scroll_of_genau_s_phase_is_not_repainted(self):
        painter = Osr2PartPainter()
        first = painter.bgra(self._off(MainMode.GENAU, 0.0, control=OSR2_PARKED))

        assert painter.bgra(self._off(MainMode.GENAU, 3.0, control=OSR2_PARKED)) is first


class TestTheDeviceRunningItselfKeepsMoving:
    def test_the_trace_scrolls_on_its_own_beat(self):
        painter = Osr2PartPainter()
        first = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.AUTO), drive=_drive(0.0))).copy()

        later = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.AUTO), drive=_drive(3.0)))

        assert not np.array_equal(later, first)

    @pytest.mark.parametrize("control", [OSR2_PARKED, OSR2_RETRACTED])
    def test_it_wins_over_whatever_the_room_is_doing_to_the_device(self, control):
        painter = Osr2PartPainter()
        main_hud_model = MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.AUTO, osr2_control=control)
        first = painter.bgra(MainHud(main_hud_model=main_hud_model, drive=_drive(0.0))).copy()

        later = painter.bgra(MainHud(main_hud_model=main_hud_model, drive=_drive(3.0)))

        assert _pill(painter) == "auto"
        assert not np.array_equal(later, first)


class TestTheHandoffKeepsMoving:
    _GAP = ((0, "robot_hand"), (40, "neutral"))

    def _in_the_gap(self, offset: float) -> MainHud:
        return MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.FUNSCRIPT),
            drive=_drive(offset, driven="neutral", segments=self._GAP))

    def test_the_trace_goes_on_sliding_through_the_gap(self):
        painter = Osr2PartPainter()
        first = painter.bgra(self._in_the_gap(0.0)).copy()

        later = painter.bgra(self._in_the_gap(3.0))

        assert not np.array_equal(later, first)

    def test_the_line_keeps_the_colors_the_model_gave_it(self):
        assert Osr2PartPainter()._resolve(self._in_the_gap(0.0)).drive.segments == self._GAP


class TestTheLockIsGreen:
    def test_a_held_clip_lights_the_lock_green_since_green_here_means_favorites_and_locking_favorites_the_video(self):

        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2_rows=main_hud_rows(lights=RowLights(locked=True))))))
        bx, by, bw, bh = _rect_of(painter, "main_lock")
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)
        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)

        assert tuple(shades[counts.argmax()]) == GREEN

    def test_an_unheld_lock_sits_on_the_resting_ground(self):

        painter = Osr2PartPainter()
        rgb = _rgb(painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2_rows=main_hud_rows(lights=RowLights(locked=False))))))
        bx, by, bw, bh = _rect_of(painter, "main_lock")
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)
        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)

        assert tuple(shades[counts.argmax()]) == (
            colors.BG_BUTTON.red(), colors.BG_BUTTON.green(), colors.BG_BUTTON.blue())


class TestARowsNameLinesUpWithItsControls:
    def _rows(self, mode: str):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=mode,
                                                    osr2_rows=main_hud_rows(mode))))
        rows: dict[int, list] = {}
        for rect, button in _declared(painter):
            rows.setdefault(rect[1], []).append((rect[0], rect[2], button))
        return painter, {y: sorted(items) for y, items in rows.items()}

    def test_everything_but_the_transport_keeps_its_place_as_the_mode_flips(self):
        def places(mode: str) -> dict:
            transport = {button.command for row in main_hud_rows(mode)[1:] for button in row}
            painter = Osr2PartPainter()
            painter.bgra(MainHud(main_hud_model=MainHudModel(
                main_mode=mode, osr2=Osr2State.ROBOT_HAND, osr2_rows=main_hud_rows(mode),
                osr2_controls=osr2_controls(broker_running=True)), drive=_drive()))
            return {button.command: rect for rect, button in painter.buttons
                    if button.command and button.command not in transport}

        kino, genau = places(MainMode.KINO), places(MainMode.GENAU)
        shown_in_both = kino.keys() & genau.keys()
        assert {c: kino[c] for c in shown_in_both} == {c: genau[c] for c in shown_in_both}
        assert shown_in_both > {"main_kino_activate", "genau_activate", "robot_hand_amplitude_up", "broker_panel"}

    def test_the_cell_is_playback_speed_at_the_tiny_face_plus_the_familys_small_gap(self):
        assert text_width(load_font(SIZE_TINY), PLAYBACK_SPEED_LABEL) + GAP_SMALL == ROW_LABEL_W

    def test_the_name_starts_where_the_controls_start(self):

        for mode in MainMode:
            _painter, rows = self._rows(mode)
            for items in rows.values():
                x, _w, _button = items[0]
                assert x == _PAD

    def test_the_name_does_not_run_under_the_button_beside_it(self):

        for mode in MainMode:
            painter, rows = self._rows(mode)
            for items in rows.values():
                x, width, button = items[0]
                if button.command or len(items) < 2:
                    continue
                assert text_width(painter._fonts.tiny, button.icon) <= width
                assert x + width <= items[1][0]

    def test_a_name_wider_than_the_cell_its_source_gave_it_widens_the_cell(self):
        painter = Osr2PartPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(osr2_rows=(
            (Button("", "Playback speed", "", width=20),
             Button("slower", "\u2212", "Slower")),))))
        (name, _n), (slower, _s) = painter.buttons[:2]

        assert name[2] >= text_width(painter._fonts.tiny, "Playback speed")
        assert name[0] + name[2] <= slower[0]

    def test_both_named_rows_take_the_same_cell_so_they_line_up_a_cell_sized_to_playback_speed_the_longer_of_the_names(self):
        kino, _rows = self._rows("kino")
        genau, _rows = self._rows("genau")

        assert _rect_of(kino, "main_player_speed_down")[0] == _rect_of(
            genau, "genau_clip_seconds_down")[0]


def _declared(painter) -> list:
    return [(rect, button) for rect, button in painter.buttons
            if button.command != minimize_command(button.command.split("_")[0])]


def _button_rect(painter, command: str) -> Rect:
    rects = [rect for rect, button in painter.buttons if button.command == command]
    assert len(rects) == 1, f"{command} drew {len(rects)} buttons"
    return rects[0]


class TestWhereTheMainHudSits:
    @staticmethod
    def _hud(corner, **main_hud_model) -> MainHud:
        return MainHud(
            main_hud_model=MainHudModel(hud_corner=corner, osr2_rows=main_hud_rows(),
                                 osr2_controls=osr2_controls(broker_running=True), **main_hud_model))

    def _painted(self, corner, **main_hud_model):
        painter = Osr2PartPainter()
        painter.bgra(self._hud(corner, **main_hud_model))
        return painter

    @staticmethod
    def _declared_bands(painter) -> dict[int, tuple[int, int]]:
        on_the_line = {button.command for button in osr2_controls(broker_running=True)}
        bars: dict[int, tuple[int, int]] = {}
        for (x, y, w, _h), button in _declared(painter):
            if button.command in on_the_line:
                continue
            left, end = bars.get(y, (x, x + w))
            bars[y] = (min(left, x), max(end, x + w))
        return bars

    def test_every_row_ends_at_the_right_pad_in_a_right_hand_corner(self):
        right = self._painted(HudCorner.LOWER_RIGHT)
        width = right._image.size[0]
        bars = self._declared_bands(right)

        assert bars, "the console drew no buttons"
        assert {end for _left, end in bars.values()} == {width - PAD}

    def test_every_row_starts_at_the_left_pad_in_a_left_hand_corner(self):
        left = self._painted(HudCorner.UPPER_LEFT)

        assert min(rect[0] for rect, _button in left.buttons) == PAD

    def test_the_hud_is_placed_in_the_corner_the_room_moved_it_to(self):
        painter = self._painted(HudCorner.LOWER_RIGHT)
        hud_w, hud_h = painter._image.size

        origin = painter.place(viewport=(1920, 1080), lower_edge=40)

        assert origin == (1920 - MARGIN - hud_w, 1080 - 40 - MARGIN - hud_h)

    def test_a_press_lands_against_wherever_the_funestra_last_put_the_hud(self):
        painter = self._painted(HudCorner.LOWER_RIGHT)
        left, top = painter.place(viewport=(1920, 1080))
        (x, y, w, h), button = painter.buttons[0]

        assert painter.press_at(left + x + w // 2, top + y + h // 2) == button.command
        assert painter.press_at(x + w // 2, y + h // 2) == ""

    def test_the_max_intensity_moves_with_its_line(self):
        def slider_past_broker(painter) -> int:
            (max_intensity,) = [bar for bar in painter.tracks if bar.axis == MAX_INTENSITY]
            return max_intensity.rect[0] - _button_rect(painter, "broker_panel")[0]

        def painted(corner):
            wide = tuple(Button(f"wide_{index}", "W", "") for index in range(30))
            painter = Osr2PartPainter()
            painter.bgra(MainHud(main_hud_model=MainHudModel(
                hud_corner=corner, osr2_rows=(*main_hud_rows(), wide), max_intensity=35,
                osr2_controls=osr2_controls(broker_running=True))))
            return painter

        left = painted(HudCorner.UPPER_LEFT)
        right = painted(HudCorner.UPPER_RIGHT)

        assert (_button_rect(right, "broker_panel")[0]
                > _button_rect(left, "broker_panel")[0]), "the line did not move"
        assert slider_past_broker(right) == slider_past_broker(left)

    def test_it_says_where_the_hud_it_painted_sits_and_whether_it_is_minimized(self):
        painter = self._painted(HudCorner.LOWER_LEFT, hud_minimized=True)

        assert painter.hud_place == HudPlace("main", HudCorner.LOWER_LEFT, MARGIN,
                                             minimized=True, inset=(PAD, PAD))

    def test_before_it_has_painted_anything_it_says_nowhere(self):
        assert Osr2PartPainter().hud_place is None


