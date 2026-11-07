from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from host_controls_fakes import a_hud
from main_hud_rows import RowLights, main_hud_rows, motion_rows
from shared_ui import colors
from shared_ui.app_icon import LETTERS
from shared_ui.palette import BG_PRIMARY, BLUE, BORDER_PANEL, GREEN, MAGENTA, TEXT_MUTED, WHITE
from shared_ui.spacing import BUTTON_GAP

from funestra.drive_layout import AMPLITUDE, CENTER, MAX_INTENSITY, SPEED
from funestra.geometry import Rect
from funestra.host_controls import HostControlsSection
from funestra.hud import (
    TOOLTIP_PAD,
    load_font,
    text_width,
)
from funestra.hud_button import Button
from funestra.hud_corners import HudPlace
from funestra.hud_icons import BROKER_ICON, shared_icon
from funestra.hud_minimize import ROOM as MINUS_ROOM
from funestra.hud_minimize import minimize_command
from funestra.hud_osr2 import COLORS as _OSR2_COLORS
from funestra.hud_osr2 import LABELS as _OSR2_LABELS
from funestra.hud_placement import HudCorner
from funestra.hud_row import SCRUBBER, RowHud, row_part
from funestra.main_hud import (
    BUTTON,
    OSR2_DRIVING,
    OSR2_PARKED,
    OSR2_RETRACTED,
    MainHudModel,
    aim_row,
    osr2_controls,
)
from funestra.main_hud_painter import (
    _PAD,
    MARGIN,
    MainHud,
    MainHudPainter,
    ModeHud,
    compilation_label,
    hud_xy,
    osr2_line_on,
    with_playback_speed,
)
from funestra.main_hud_painter import _PAD as PAD
from funestra.modes import LengthMode, MainMode, Osr2State
from funestra.osr2_visualizer import (
    CONTROL_TIPS,
    DRIVEN_BY_NEUTRAL,
    DriveHud,
    section_size,
    trace_ink,
    tracks,
)
from funestra.playhead import video_playhead
from funestra.robot_hand import POSITION_MAX
from funestra.volume import VolumeHud

MIXED, FULL, CLIPS = LengthMode.MIXED, LengthMode.FULL, LengthMode.CLIPS


def _drive(offset: float = 0.0, **over) -> DriveHud:
    return DriveHud(speed=50, amplitude=80, center=50, shape="sine",
                    waveform=tuple(0.5 + 0.4 * np.sin(i / 6 + offset) for i in range(80)),
                    **over)


def _line(*, locked: bool = True, order_latest: bool = False, **modes) -> str:
    return MainHud(modes=ModeHud(**modes),
                      main_hud_model=MainHudModel(main_mode=MainMode.KINO, locked=locked,
                                           latest=order_latest)).title


def _pill(painter: MainHudPainter) -> str:
    return osr2_line_on(painter._painted[0]).state


def _rect_of(painter: MainHudPainter, command: str) -> Rect:
    return next(rect for rect, button in painter.buttons if button.command == command)


def _over(painter: MainHudPainter, command: str) -> tuple[int, int]:
    bx, by, bw, bh = _rect_of(painter, command)
    left, top = hud_xy()
    return left + bx + bw // 2, top + by + bh // 2


class TestLine:
    def test_says_whether_the_main_funestra_is_holding_the_video_on_screen(self):
        assert _line(locked=True) == "Locked · Shuffle"
        assert _line(locked=False) == "Unlocked · Shuffle"

    def test_says_which_length_mode_the_library_is_in_and_says_it_last_and_says_nothing_for_mixed_since_with_three_kinds_of_video_one_word_would_not_say_which(self):
        assert _line(length_mode=MIXED) == "Locked · Shuffle"
        assert _line(length_mode=FULL) == "Locked · Shuffle · Full"
        assert _line(length_mode=CLIPS) == "Locked · Shuffle · Clips"

    def test_ends_with_every_word_the_room_narrowed_the_browse_by_in_either_mode(self):
        for main_mode in MainMode:
            hud = MainHud(main_hud_model=MainHudModel(main_mode=main_mode, latest=False,
                                                  filters=("VR", "Clips", "Portrait")))

            assert hud.title == "Locked · Shuffle · VR · Clips · Portrait"

    def test_the_rooms_words_stand_in_for_kinos_own_length_word(self):
        hud = MainHud(modes=ModeHud(length_mode=CLIPS),
                         main_hud_model=MainHudModel(latest=False, filters=("Full",)))

        assert hud.title == "Locked · Shuffle · Full"

    def test_claims_no_length_mode_without_a_library_backing_the_playlist(self):
        assert _line(length_mode=None) == "Locked · Shuffle"

    def test_a_genau_primary_says_its_order_and_the_pace_it_moves_at(self):
        def line(**over) -> str:
            return MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU, latest=False, **over),
                              drive=_drive(advance_interval=5)).title

        assert line(locked=False) == "Unlocked · Shuffle · 5s"
        assert line(locked=True) == "Locked · Shuffle"

    def test_a_genau_primary_says_which_order_it_was_put_in(self):
        def line(**over) -> str:
            return MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU, **over),
                              drive=_drive(advance_interval=5)).title

        assert line(locked=False, latest=True) == "Unlocked · Latest · 5s"
        assert line(locked=True, latest=True) == "Locked · Latest"

    def test_the_pace_belongs_to_genau_and_is_not_claimed_while_main_funestra_is_showing(self):
        assert MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, locked=False, latest=False),
                          drive=_drive(advance_interval=5)).title == "Unlocked · Shuffle"

    def test_a_host_with_no_browse_order_names_none(self):
        assert MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU, locked=True)).title == (
            "Locked")
        assert MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU, locked=False),
                          drive=_drive(advance_interval=5)).title == "Unlocked · 5s"

    def test_names_the_compilation_and_where_you_are_in_it_keeping_the_length_mode_it_returns_to(self):
        def line(**over) -> str:
            return _line(compilation="Vol6", position=9, total=20, **over)

        assert line(locked=False) == "Vol6 · 9/20 · Shuffle"
        assert line(locked=True) == "Vol6 · 9/20 · Locked · Shuffle"
        assert line(locked=False, length_mode=CLIPS) == "Vol6 · 9/20 · Shuffle · Clips"

    def test_says_which_browse_order_the_main_funestra_is_in(self):
        assert _line(order_latest=True) == "Locked · Latest"
        assert _line(order_latest=False) == "Locked · Shuffle"
        assert _line(order_latest=True, length_mode=CLIPS) == (
            "Locked · Latest · Clips")

    def test_says_when_fun_time_has_narrowed_to_f_mode(self):
        assert _line(scripted_filter=True) == "Locked · Shuffle · F-Mode"
        assert _line(length_mode=CLIPS, scripted_filter=True) == (
            "Locked · Shuffle · F-Mode · Clips")


class TestCompilationLabel:
    def test_keeps_only_the_volume(self):
        assert compilation_label(
            "various - Ultimate Example Studio Alpha Collection - Volume 6 (v1)"
        ) == "Volume 6"

    def test_an_undashed_title_survives_whole(self):
        assert compilation_label("Scene Five 3") == "Scene Five 3"


class TestPainter:
    def test_held_to_a_width_it_paints_every_mode_that_wide_since_a_hud_that_is_a_screen_of_its_own_would_seem_to_move_if_it_grew_and_shrank(self):
        painter = MainHudPainter(width=600)

        widths = {
            mode: painter.rgba(MainHud(
                modes=ModeHud(video="scene one"),
                main_hud_model=MainHudModel(main_mode=mode, locked=False,
                                     rows=main_hud_rows(mode)),
                drive=_drive()))[1][0]
            for mode in MainMode
        }

        assert widths == {MainMode.KINO: 600, MainMode.GENAU: 600}

    def test_held_to_a_width_it_keeps_one_width_whatever_row_it_carries(self):
        painter = MainHudPainter(width=300)
        flick = RowHud(position_ms=4_000, duration_ms=10_000,
                       playhead=video_playhead(4_000, 10_000, 0.0), loop=(6, 238))
        video = RowHud(position_ms=42_000, duration_ms=195_000,
                       playhead=video_playhead(42_000, 195_000, 30.0))

        widths = {
            painter.rgba(MainHud(
                modes=ModeHud(video="scene one"),
                main_hud_model=MainHudModel(main_mode=mode, locked=False, rows=main_hud_rows(mode)),
                drive=_drive()), item_row=row)[1][0]
            for mode in MainMode for row in (flick, video, None)
        }

        assert len(widths) == 1

    def test_a_file_name_too_long_for_the_held_width_is_elided_rather_than_widening_it(self):
        painter = MainHudPainter(width=600)
        long_name = "Jane Doe - scene one - " + "a long descriptor " * 12

        _rgba, (width, _height) = painter.rgba(MainHud(
            modes=ModeHud(video=long_name), main_hud_model=MainHudModel(main_mode=MainMode.KINO, locked=False)))

        assert width == 600

    def test_a_width_its_own_parts_cannot_fit_in_is_widened_not_clipped(self):
        hud = MainHud(modes=ModeHud(video="scene one"),
                         main_hud_model=MainHudModel(main_mode=MainMode.GENAU, locked=False), drive=_drive())

        _rgba, (natural, _h) = MainHudPainter().rgba(hud)
        _rgba, (held, _h) = MainHudPainter(width=50).rgba(hud)

        assert held >= natural

    def test_a_tooltip_longer_than_the_hud_is_wide_stays_on_the_hud(self):
        painter = MainHudPainter()
        hud = MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, locked=False,
                                              rows=main_hud_rows()))
        plain = _rgb(painter.bgra(hud))
        tiny = load_font(8)
        (x, y, w, h), _button = max(
            ((rect, button) for rect, button in painter.buttons if button.tooltip),
            key=lambda pair: text_width(tiny, pair[1].tooltip))
        tipped = _rgb(MainHudPainter().bgra(hud, hover=(x + w // 2, y + h // 2)))

        rows, cols = np.nonzero((tipped != plain).any(axis=2))
        one_line_height = sum(tiny.getmetrics()) + 2 * TOOLTIP_PAD

        assert len(cols)
        assert cols.max() < plain.shape[1] - 1
        assert rows.max() - rows.min() + 1 > one_line_height

    def test_the_top_line_sits_tight_to_the_top(self):
        painter = MainHudPainter()
        bgra = painter.bgra(MainHud(modes=ModeHud(length_mode=FULL)))
        rgb = _rgb(bgra)

        line_h = sum(load_font(11).getmetrics())
        bar = rgb[PAD:PAD + line_h, :, :]
        assert (bar > 200).any()

    def test_the_status_leads_and_the_file_name_is_the_muted_line_under_it(self):
        painter = MainHudPainter()
        bgra = painter.bgra(MainHud(modes=ModeHud(
            video="Some Video Name", length_mode=MIXED)))
        rgb = _rgb(bgra)

        body_h = sum(load_font(11).getmetrics())
        bright_rows = np.nonzero((rgb > 200).any(axis=(1, 2)))[0]
        muted = (rgb[:, :, 0] > 100) & (rgb[:, :, 0] < 160)
        muted_rows = np.nonzero(muted.any(axis=1))[0]

        assert bright_rows.min() < PAD + body_h
        assert muted_rows.max() > bright_rows.min()

    def test_a_longer_file_name_widens_the_hud(self):
        narrow = MainHudPainter().bgra(MainHud(modes=ModeHud(
            video="A Much Much Longer Video Name Indeed")))
        wide = MainHudPainter().bgra(MainHud(modes=ModeHud(
            video="A Much Much Longer Video Name Indeed, And Then Some More Of It")))

        assert wide.shape[1] > narrow.shape[1]

    def test_the_visualizer_grows_the_hud(self):
        painter = MainHudPainter()
        plain = painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO))).shape[0]
        driving = MainHudPainter().bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO), drive=_drive())).shape[0]

        assert driving > plain

    def test_the_dot_lights_only_while_the_main_has_the_floor(self):
        def dot(active: bool):
            bgra = MainHudPainter().bgra(
                MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, active=active)))
            body = sum(load_font(11).getmetrics())
            cx, cy = PAD + MINUS_ROOM + 5, PAD + body // 2
            return tuple(int(v) for v in _rgb(bgra)[cy, cx])

        assert np.allclose(dot(True), WHITE, atol=45)
        assert np.allclose(dot(False), TEXT_MUTED, atol=45)

    def test_the_dot_does_not_shift_the_words_around(self):
        painter = MainHudPainter()

        lit = painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, active=True)))
        idle = MainHudPainter().bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, active=False)))

        assert lit.shape == idle.shape

    def test_an_unchanged_hud_is_not_repainted(self):
        painter = MainHudPainter()
        hud = MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO))

        assert painter.bgra(hud) is painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO)))

    def test_a_heatmap_is_known_by_being_the_same_array_so_a_host_rebuilds_it_rather_than_writing_into_it(self):
        painter = MainHudPainter()
        hud = MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO))
        heatmap = np.zeros((8, 3), dtype=np.uint8)
        first = painter.bgra(hud, heatmap=heatmap)

        heatmap[:] = 255
        assert painter.bgra(hud, heatmap=heatmap) is first
        assert painter.bgra(hud, heatmap=heatmap.copy()) is not first

    def test_the_visualizers_arrows_are_hit_targets_even_though_it_draws_them(self):
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO), drive=_drive()))

        actions = {b.command for _rect, b in painter.buttons}
        for action in ("robot_hand_amplitude_up", "robot_hand_center_down", "robot_hand_speed_up"):
            assert action in actions

    def test_the_osr2_state_is_shown(self):
        painter = MainHudPainter()
        bgra = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.FUNSCRIPT)))
        rgb = _rgb(bgra)
        green = (rgb[:, :, 1] > 130) & (rgb[:, :, 0] < 110) & (rgb[:, :, 2] < 110)
        assert green.any()

    def _busiest_shade(self, command: str, model: MainHudModel, modes=None):
        painter = MainHudPainter()
        rgb = _rgb(painter.bgra(MainHud(main_hud_model=model, modes=modes or ModeHud())))
        bx, by, bw, bh = _rect_of(painter, command)
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)
        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)
        return tuple(shades[counts.argmax()]), pixels

    def test_the_mode_you_are_in_lights_blue_as_on_the_satellites_since_a_lighter_ground_could_not_be_found_at_a_glance(self):
        shade, pixels = self._busiest_shade(
            "main_kino_activate",
            MainHudModel(main_mode=MainMode.KINO, rows=main_hud_rows("kino")))

        assert shade == BLUE
        green = (pixels[:, :, 1] > 130) & (pixels[:, :, 0] < 110) & (pixels[:, :, 2] < 110)
        assert not green.any()

    def test_an_ordinary_toggle_that_is_on_fills_the_familys_blue_since_the_active_gray_could_not_be_told_from_off(self):
        blue = BLUE
        shade, _pixels = self._busiest_shade(
            "robot_hand_toggle_learned",
            MainHudModel(main_mode=MainMode.GENAU, rows=main_hud_rows("genau"),
                         osr2_rows=motion_rows(learned=True)))

        assert shade == blue

    def test_a_choice_the_funestra_is_holding_but_not_applying_fills_the_gray_as_a_compilation_sets_the_browse_order_and_length_aside_and_restores_them(self):
        gray = (colors.BG_BUTTON_ACTIVE.red(), colors.BG_BUTTON_ACTIVE.green(),
                colors.BG_BUTTON_ACTIVE.blue())
        shade, _pixels = self._busiest_shade(
            "main_shuffle",
            MainHudModel(main_mode=MainMode.KINO, latest=False,
                         rows=main_hud_rows(lights=RowLights(remembered=True))),
            modes=ModeHud(length_mode=LengthMode.MIXED, compilation="Volume 6"))

        assert shade == gray

    def test_a_control_at_rest_still_carries_the_familys_thin_edge(self):
        painter = MainHudPainter()
        rgb = _rgb(painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, rows=main_hud_rows()))))
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
        for action, grid in (("broker_panel", LETTERS["B"]),
                             ("main_fmode", LETTERS["F"])):
            pixels = self._button_pixels(action, MainHudModel(
                main_mode=MainMode.KINO, rows=main_hud_rows(lights=RowLights(favorites=True)),
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
            "main_minimize", MainHudModel(main_mode=MainMode.KINO, rows=main_hud_rows()))
        inside = pixels[2:-2, 2:-2]
        ys, xs = np.nonzero((inside > 150).all(axis=2))

        assert len(ys), "the minimize button drew no mark at all"
        assert xs.max() - xs.min() > ys.max() - ys.min()

    @staticmethod
    def _button_pixels(command: str, model: MainHudModel) -> np.ndarray:
        painter = MainHudPainter()
        rgb = _rgb(painter.bgra(MainHud(main_hud_model=model)))
        bx, by, bw, bh = _rect_of(painter, command)
        return rgb[by:by + bh, bx:bx + bw]

    def _broker_pixels(self, broker: bool) -> np.ndarray:
        return self._button_pixels("broker_panel", MainHudModel(
            main_mode=MainMode.KINO, osr2_controls=osr2_controls(broker_running=broker)))

    def test_f_mode_is_the_one_lit_control_that_stays_green_since_green_here_belongs_to_the_favorites_and_the_funscripts(self):
        pixels = self._button_pixels(
            "main_fmode",
            MainHudModel(main_mode=MainMode.KINO,
                         rows=main_hud_rows(lights=RowLights(favorites=True)))).astype(int)

        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)
        assert tuple(shades[counts.argmax()]) == (48, 160, 48)

    def test_the_enhanced_filter_wears_yellow_off_and_on_the_yellow_of_the_plus_origenerator_marks_an_enhanced_image_with(self):
        yellow = (255, 200, 120)
        off = self._button_pixels("genau_filter_enhanced", MainHudModel(
            main_mode=MainMode.GENAU, rows=main_hud_rows("genau", enhanced=False)))
        on = self._button_pixels("genau_filter_enhanced", MainHudModel(
            main_mode=MainMode.GENAU, rows=main_hud_rows("genau", enhanced=True)))

        assert (np.abs(off.astype(int) - yellow).sum(axis=2) < 30).any()
        shades, counts = np.unique(on.astype(int).reshape(-1, 3), axis=0,
                                   return_counts=True)
        assert tuple(shades[counts.argmax()]) == yellow

    def test_the_slab_is_the_canvas_gray_unless_a_host_asks_for_another(self):
        default = _rgb(MainHudPainter().bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU))))
        asked = _rgb(MainHudPainter().bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU), ground=(40, 40, 40))))

        assert tuple(default[3, 3]) == BG_PRIMARY
        assert tuple(asked[3, 3]) != BG_PRIMARY
        assert asked[3, 3].min() > default[3, 3].min()

    def test_the_ground_is_part_of_what_the_repaint_cache_compares(self):
        painter = MainHudPainter()
        first = _rgb(painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU))))[3, 3]
        second = _rgb(painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.GENAU),
                                              ground=(40, 40, 40))))[3, 3]

        assert tuple(first) != tuple(second)

    def test_a_lit_marks_ink_stays_white_over_a_colored_fill_since_a_mark_that_changed_color_read_as_a_different_button(self):
        painter = MainHudPainter()
        rgb = _rgb(painter.bgra(
            MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO,
                                            rows=main_hud_rows(lights=RowLights(recording=True))))))
        bx, by, bw, bh = _rect_of(painter, "main_player_record_tap")
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)

        assert tuple(pixels[bh // 2, 2]) == (255, 60, 60)
        assert (pixels > 240).all(axis=2).any()


class TestPresses:
    @staticmethod
    def _painted(mode: MainMode = MainMode.KINO) -> MainHudPainter:
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=mode,
                                                    rows=main_hud_rows(mode))))
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
        painter = MainHudPainter()
        height, width = painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO))).shape[:2]
        left, top = hud_xy()

        assert painter.covers(left, top)
        assert painter.covers(left + width - 1, top + height - 1)
        assert not painter.covers(left + width, top)
        assert not painter.covers(left, top + height)
        assert not painter.covers(left - 1, top - 1)

    def test_nothing_is_under_a_press_before_the_hud_is_first_painted(self):
        left, top = hud_xy()

        assert not MainHudPainter().covers(left, top)

    def test_the_huds_own_corner_is_not_read_as_the_windows(self):
        painter = self._painted()
        bx, by, _bw, _bh = _rect_of(painter, "main_prev")

        assert painter.press_at(bx, by) == ""

    def test_a_visualizers_arrow_press_reaches_genau(self):
        painter = MainHudPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND), drive=_drive()))

        assert painter.press_at(*_over(painter, "robot_hand_amplitude_up")) == "robot_hand_amplitude_up"

    def test_the_visualizers_controls_are_dead_while_a_funscript_has_the_device_since_a_press_there_once_woke_genau_against_the_funscript(self):
        painter = MainHudPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.FUNSCRIPT), drive=_drive()))

        over = _over(painter, "robot_hand_amplitude_up")
        assert painter.press_at(*over) == ""
        assert all(b.dim for _rect, b in painter.buttons if b.command.startswith("genau_amplitude"))

    def test_the_cursor_over_a_button_is_reported_in_hud_coordinates(self):
        painter = self._painted()
        mx, my = _over(painter, "main_next")
        left, top = hud_xy()

        assert painter.hover_at(mx, my) == (mx - left, my - top)

    def test_a_button_with_no_tooltip_still_answers_the_pointer(self):
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(rows=((Button("go_kino", "Kino", ""),),))))
        mx, my = _over(painter, "go_kino")
        left, top = hud_xy()

        assert painter.hover_at(mx, my) == (mx - left, my - top)


class TestThePointer:
    @staticmethod
    def _hud(corner: HudCorner = HudCorner.UPPER_LEFT) -> MainHud:
        return MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO, hud_corner=corner,
                                               rows=main_hud_rows(MainMode.KINO)))

    @staticmethod
    def _ground(rgb: np.ndarray, painter: MainHudPainter, command: str) -> int:
        x, y, _w, h = _rect_of(painter, command)
        return int(rgb[y + h // 2, x + 2].sum())

    def test_the_button_under_the_pointer_draws_lighter(self):
        painter = MainHudPainter()
        at_rest = _rgb(painter.bgra(self._hud()))

        painter.motion(*_over(painter, "main_next"))
        under_the_pointer = _rgb(painter.bgra(self._hud()))

        assert (self._ground(under_the_pointer, painter, "main_next")
                > self._ground(at_rest, painter, "main_next"))

    def test_the_pointer_moving_off_the_hud_puts_the_button_back(self):
        painter = MainHudPainter()
        at_rest = _rgb(painter.bgra(self._hud()))
        painter.motion(*_over(painter, "main_next"))
        painter.bgra(self._hud())

        painter.motion(-1, -1)

        assert (_rgb(painter.bgra(self._hud())) == at_rest).all()

    def test_the_pointer_leaving_the_window_puts_the_button_back(self):
        painter = MainHudPainter()
        at_rest = _rgb(painter.bgra(self._hud()))
        painter.motion(*_over(painter, "main_next"))
        painter.bgra(self._hud())

        painter.leave()

        assert (_rgb(painter.bgra(self._hud())) == at_rest).all()

    def test_a_hud_sent_to_another_corner_forgets_where_the_pointer_was(self):
        painter = MainHudPainter()
        painter.bgra(self._hud())
        painter.motion(*_over(painter, "main_next"))

        moved = _rgb(painter.bgra(self._hud(HudCorner.UPPER_RIGHT)))

        assert (moved == _rgb(MainHudPainter().bgra(self._hud(HudCorner.UPPER_RIGHT)))).all()


class TestDrags:
    @staticmethod
    def _painted(osr2: Osr2State = Osr2State.ROBOT_HAND) -> MainHudPainter:
        painter = MainHudPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=osr2,
                                 rows=main_hud_rows()),
            drive=_drive()))
        return painter

    @staticmethod
    def _bar(painter: MainHudPainter, axis: str):
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
        painter = MainHudPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND,
                                 max_intensity=50),
            drive=_drive()))
        max_intensity = self._bar(painter, MAX_INTENSITY)

        assert painter.press_at(*self._at(max_intensity, 1.0)) == "max_intensity_100"
        assert painter.drag_to(*self._at(max_intensity, 0.0)) == "max_intensity_0"

    def test_there_are_no_bars_at_all_where_nothing_is_driving(self):
        painter = MainHudPainter()
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
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(
            rows=((Button("go_on", "⏭", "On to the next"),),
                  (Button("", "Pace", "", width=40),
                   Button("slower", shared_icon("minus"), "Slower", group_break=True))),
            osr2_controls=(Button("wake_broker", BROKER_ICON, "Wake it", warn=True),),
        )))

        assert [button.command for _rect, button in _declared(painter)] == [
            "go_on", "", "slower", "wake_broker"]

    def test_the_rows_that_aim_the_device_are_drawn_under_the_rest_and_over_its_line(self):
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(
            osr2=Osr2State.ROBOT_HAND,
            rows=((Button("go_on", "⏭", "On to the next"),),),
            osr2_rows=((Button("robot_hand_park", "P", "Parked"),),),
            osr2_controls=(Button("broker_panel", BROKER_ICON, "Broker"),))))

        assert (_button_rect(painter, "go_on")[1]
                < _button_rect(painter, "robot_hand_park")[1]
                < _button_rect(painter, "broker_panel")[1])

    def test_a_hud_that_declares_no_buttons_draws_none(self):
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=MainMode.KINO)))

        assert _declared(painter) == []

    def test_with_no_controls_on_its_line_the_osr2_label_starts_the_line(self):
        rgb = _rgb(MainHudPainter().bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU))))
        height = rgb.shape[0]
        line = rgb[height - PAD - BUTTON:height - PAD, 3:].astype(int)
        inked = (np.abs(line - np.array(BG_PRIMARY)).max(axis=2) > 40).any(axis=0)

        assert 3 + np.nonzero(inked)[0].min() <= PAD + 2


class TestAConsoleAnotherFunestraTookTheOsr2From:
    @staticmethod
    def _painted(*, has_osr2: bool) -> tuple[MainHudPainter, np.ndarray]:
        painter = MainHudPainter()
        bgra = painter.bgra(MainHud(
            main_hud_model=MainHudModel(
                main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND,
                rows=((Button("main_take_osr2", "OSR2", "Take the OSR2"),),),
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
    def test_the_drawing_funestra_folds_in_its_own_rate(self):
        main_hud_model = with_playback_speed(MainHudModel(main_mode=MainMode.KINO), 1.75)

        assert main_hud_model.playback_speed == 1.75

    def test_the_painter_writes_the_hosts_numbers_into_the_read_outs_that_name_them(self):
        def visualizers(hud: MainHud) -> list[str]:
            painter = MainHudPainter()
            painter.bgra(hud)
            return [button.icon for _rect, button in painter.buttons if button.host_value]

        assert visualizers(MainHud(main_hud_model=with_playback_speed(
            MainHudModel(main_mode=MainMode.KINO, rows=main_hud_rows("kino")), 1.75))) == ["1.75\u00d7"]
        assert visualizers(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, rows=main_hud_rows("genau")),
            drive=_drive(advance_interval=7))) == ["7s"]


class TestPlacement:
    def test_the_hud_sits_in_the_top_left_corner(self):
        assert hud_xy() == (8, 8)


def _rgb(bgra: np.ndarray) -> np.ndarray:
    return bgra[:, :, [2, 1, 0]]


class TestTraceSources:
    @staticmethod
    def _painted(mode: MainMode, osr2: Osr2State, drive: DriveHud | None = None) -> MainHudPainter:
        painter = MainHudPainter()
        painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=mode, osr2=osr2), drive=drive or _drive()))
        return painter

    @staticmethod
    def _drawn(mode: str, osr2: str, drive: DriveHud | None = None):
        painter = MainHudPainter()
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
                    modes=ModeHud(video="clip one"),
                    main_hud_model=MainHudModel(main_mode=mode, osr2=Osr2State.ROBOT_HAND,
                                         rows=main_hud_rows(mode),
                                         osr2_controls=osr2_controls(broker_running=True)),
                    drive=DriveHud(waveform=wave, driven=driven,
                                   segments=segments))
                MainHudPainter().rgba(hud)

    def test_with_a_composed_trace_on_the_hud_the_pill_reads_the_trace_s_own_answer_to_who_has_the_device(self):
        wave = tuple(0.5 for _ in range(80))
        painter = MainHudPainter()
        hud = MainHud(
            modes=ModeHud(video="clip one"),
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND),
            drive=DriveHud(waveform=wave, driven="neutral",
                           segments=((0, "robot_hand"), (30, "neutral"))))
        painter.rgba(hud)

        assert _pill(painter) == "buffer"

    def test_the_pill_is_read_off_the_hud_in_hand_never_off_the_one_painted_before_it(self):
        painter = MainHudPainter()
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
            modes=ModeHud(video="clip one"),
            main_hud_model=MainHudModel(main_mode=mode, osr2=osr2, osr2_control=control),
            drive=DriveHud(waveform=wave, driven="funscript", position=5000,
                           segments=((0, "robot_hand"), (30, "funscript"))))

    def test_the_pill_names_the_hold_whoever_would_have_had_the_device(self):
        painter = MainHudPainter()
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
                painter = MainHudPainter()
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
            painter = MainHudPainter()
            main_hud_model = MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND,
                                   osr2_control=control)
            first = painter.bgra(MainHud(main_hud_model=main_hud_model, drive=_drive(0.0))).copy()

            assert np.array_equal(painter.bgra(MainHud(main_hud_model=main_hud_model, drive=_drive(3.0))),
                                  first), control

    def test_a_held_visualizer_cannot_be_pressed(self):
        for control in (OSR2_PARKED, OSR2_RETRACTED):
            painter = MainHudPainter()
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
            return MainHudPainter().bgra(MainHud(main_hud_model=self._main_hud(control, paused=paused)))

        paused = hud(OSR2_DRIVING, paused=True)

        assert np.array_equal(paused, hud(OSR2_PARKED, paused=False))
        assert not np.array_equal(paused, hud(OSR2_DRIVING, paused=False))

    @pytest.mark.parametrize("mode", list(MainMode))
    def test_the_visualizers_speed_amp_and_center_buttons_take_presses(self, mode):
        painter = MainHudPainter()
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
    def _dot(painter: MainHudPainter, hud: MainHud) -> int:
        painter.rgba(hud)
        return painter._painted[0].drive.position

    def _held_from(self, control: str):
        clock = [10.0]
        painter = MainHudPainter(clock=lambda: clock[0])
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
        painter = MainHudPainter()
        first = painter.bgra(self._off(mode, 0.0)).copy()

        assert np.array_equal(painter.bgra(self._off(mode, 3.0)), first)

    def test_the_switchs_label_gets_room_for_its_words(self):
        painter = MainHudPainter()
        painter.rgba(MainHud(main_hud_model=MainHudModel(
            main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND,
            osr2_rows=(aim_row(learned=False, shape="sine", control=OSR2_DRIVING),))))
        label = next(rect for rect, button in painter.buttons if button.icon == "OSR2 control")

        assert label[2] > text_width(load_font(8), "OSR2 control")

    def test_it_moves_again_the_moment_something_is_driving(self):
        painter = MainHudPainter()
        still = painter.bgra(self._off(MainMode.GENAU, 0.0)).copy()

        moving = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND), drive=_drive(3.0)))

        assert not np.array_equal(moving, still)

    def test_a_videos_composed_trace_holds_still_in_gray_with_the_device_off(self):
        painter = MainHudPainter()
        first = painter.bgra(self._off(
            MainMode.KINO, 0.0, driven="funscript", segments=self._HANDOFF)).copy()

        later = painter.bgra(self._off(
            MainMode.KINO, 3.0, driven="funscript", segments=self._HANDOFF))

        assert {who for _start, _end, who in painter._painted[0].drive.runs} == {"nothing"}
        assert np.array_equal(later, first)

    def test_the_pill_says_off_whoever_a_videos_composed_trace_has_driving(self):
        painter = MainHudPainter()
        hud = self._off(MainMode.KINO, 0.0, driven="funscript", segments=self._HANDOFF)
        painter.rgba(hud)

        assert _pill(painter) == "off"

    @pytest.mark.parametrize("control", [OSR2_PARKED, OSR2_RETRACTED])
    def test_held_with_the_device_off_is_the_dim_gray_of_driving_with_it_off(self, control):
        def drawn(control: str):
            return MainHudPainter().bgra(self._off(
                MainMode.KINO, 0.0, control=control, position=4_200,
                driven="funscript", segments=self._HANDOFF))

        assert np.array_equal(drawn(control), drawn(OSR2_DRIVING))

    @pytest.mark.parametrize("control", [OSR2_PARKED, OSR2_RETRACTED])
    def test_held_with_the_device_off_holds_still(self, control):
        painter = MainHudPainter()
        first = painter.bgra(self._off(MainMode.GENAU, 0.0, control=control)).copy()

        assert np.array_equal(
            painter.bgra(self._off(MainMode.GENAU, 3.0, control=control)), first)

    def test_a_still_visualizer_arriving_as_a_fresh_scroll_of_genau_s_phase_is_not_repainted(self):
        painter = MainHudPainter()
        first = painter.bgra(self._off(MainMode.GENAU, 0.0, control=OSR2_PARKED))

        assert painter.bgra(self._off(MainMode.GENAU, 3.0, control=OSR2_PARKED)) is first


class TestTheDeviceRunningItselfKeepsMoving:
    def test_the_trace_scrolls_on_its_own_beat(self):
        painter = MainHudPainter()
        first = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.AUTO), drive=_drive(0.0))).copy()

        later = painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.AUTO), drive=_drive(3.0)))

        assert not np.array_equal(later, first)

    @pytest.mark.parametrize("control", [OSR2_PARKED, OSR2_RETRACTED])
    def test_it_wins_over_whatever_the_room_is_doing_to_the_device(self, control):
        painter = MainHudPainter()
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
        painter = MainHudPainter()
        first = painter.bgra(self._in_the_gap(0.0)).copy()

        later = painter.bgra(self._in_the_gap(3.0))

        assert not np.array_equal(later, first)

    def test_the_line_keeps_the_colors_the_model_gave_it(self):
        assert MainHudPainter()._resolve(self._in_the_gap(0.0)).drive.segments == self._GAP


class TestTheLockIsGreen:
    def test_a_held_clip_lights_the_lock_green_since_green_here_means_favorites_and_locking_favorites_the_video(self):

        painter = MainHudPainter()
        rgb = _rgb(painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, rows=main_hud_rows(lights=RowLights(locked=True))))))
        bx, by, bw, bh = _rect_of(painter, "main_lock")
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)
        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)

        assert tuple(shades[counts.argmax()]) == GREEN

    def test_an_unheld_lock_sits_on_the_resting_ground(self):

        painter = MainHudPainter()
        rgb = _rgb(painter.bgra(MainHud(
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, rows=main_hud_rows(lights=RowLights(locked=False))))))
        bx, by, bw, bh = _rect_of(painter, "main_lock")
        pixels = rgb[by:by + bh, bx:bx + bw].astype(int)
        shades, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)

        assert tuple(shades[counts.argmax()]) == (
            colors.BG_BUTTON.red(), colors.BG_BUTTON.green(), colors.BG_BUTTON.blue())


class TestARowsNameLinesUpWithItsControls:
    def _rows(self, mode: str):
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(main_mode=mode,
                                                    rows=main_hud_rows(mode))))
        rows: dict[int, list] = {}
        for rect, button in _declared(painter):
            rows.setdefault(rect[1], []).append((rect[0], rect[2], button))
        return painter, {y: sorted(items) for y, items in rows.items()}

    def test_the_mode_switch_keeps_its_place_as_the_mode_flips_and_only_the_transport_changes(self):
        stays_put = {"main_kino_activate", "genau_activate"}

        def places(mode: str) -> dict:
            painter = MainHudPainter()
            painter.bgra(MainHud(main_hud_model=MainHudModel(
                main_mode=mode, rows=main_hud_rows(mode))))
            return {button.command: rect for rect, button in painter.buttons
                    if button.command in stays_put}

        assert places(MainMode.KINO) == places(MainMode.GENAU)
        assert set(places(MainMode.KINO)) == stays_put

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
                assert text_width(painter._tiny, button.icon) <= width
                assert x + width <= items[1][0]

    def test_a_name_wider_than_the_cell_its_source_gave_it_widens_the_cell(self):
        painter = MainHudPainter()
        painter.bgra(MainHud(main_hud_model=MainHudModel(rows=(
            (Button("", "Playback speed", "", width=20),
             Button("slower", "\u2212", "Slower")),))))
        (name, _n), (slower, _s) = painter.buttons[:2]

        assert name[2] >= text_width(painter._tiny, "Playback speed")
        assert name[0] + name[2] <= slower[0]

    def test_both_named_rows_take_the_same_cell_so_they_line_up_a_cell_sized_to_playback_speed_the_longer_of_the_names(self):
        kino, _rows = self._rows("kino")
        genau, _rows = self._rows("genau")

        assert _rect_of(kino, "main_player_speed_down")[0] == _rect_of(
            genau, "genau_clip_seconds_down")[0]


class TestTheRowTheMainHudCarriesForItsVideo:
    @staticmethod
    def _hud() -> MainHud:
        return MainHud(modes=ModeHud(video="scene one"),
                          main_hud_model=MainHudModel(main_mode=MainMode.KINO, locked=False))

    def test_a_funestra_that_hands_over_no_row_grows_none(self):
        painter = MainHudPainter()
        row = RowHud(position_ms=30_000, duration_ms=60_000, volume=VolumeHud(volume=40))

        with_row = painter.rgba(self._hud(), item_row=row)[1][1]
        without = MainHudPainter().rgba(self._hud())[1][1]

        assert with_row > without

    def test_the_clip_s_funscript_colors_fill_that_track(self):
        painter = MainHudPainter()
        row = RowHud(position_ms=0, duration_ms=60_000)
        plain = painter.rgba(self._hud(), item_row=row)[0]
        x0, x1 = painter.row.track
        colors = np.array([(200, 40 + x % 150, 30) for x in range(x1 - x0)],
                          dtype=np.uint8)

        colored = MainHudPainter().rgba(self._hud(), item_row=row, heatmap=colors)[0]

        assert colored != plain

    def test_it_lands_at_the_foot_of_the_hud(self):
        painter = MainHudPainter()
        row = RowHud(position_ms=30_000, duration_ms=60_000, volume=VolumeHud(volume=40))

        _rgba, (_width, height) = painter.rgba(self._hud(), item_row=row)
        _x, y, _width, row_h = painter.row.rect

        assert y + row_h <= height
        assert all(rect[1] + rect[3] <= y for rect, _button in painter.buttons)
        x0, x1 = painter.row.track
        assert row_part((x0 + x1) // 2, row_h - 2, painter.row) == SCRUBBER


class TestTheHostsControls:
    @staticmethod
    def _hud() -> MainHud:
        return MainHud(modes=ModeHud(video="scene one"),
                          main_hud_model=MainHudModel(main_mode=MainMode.KINO, locked=False))

    def test_the_hud_grows_by_the_room_they_take(self):
        without = MainHudPainter().rgba(self._hud())[1][1]

        with_them = MainHudPainter().rgba(self._hud(), host_controls=a_hud())[1][1]

        assert with_them >= without + HostControlsSection.height

    def test_they_land_at_the_foot_under_everything_else(self):
        painter = MainHudPainter()
        row = RowHud(position_ms=30_000, duration_ms=60_000, volume=VolumeHud(volume=40))

        _rgba, (_width, height) = painter.rgba(self._hud(), item_row=row, host_controls=a_hud())
        _x, y, _field_width, field_height = painter.host_controls_layout.field

        assert field_height == HostControlsSection.height
        assert y + field_height == height - PAD
        assert painter.row.rect[1] + painter.row.rect[3] <= y
        assert all(rect[1] + rect[3] <= y for rect, _button in painter.buttons)

    def test_controls_wider_than_the_hud_widen_it_rather_than_being_cut(self):
        wide = replace(a_hud(), choices=("A name far too long for a console held to its width",))
        painter = MainHudPainter(width=380)

        _rgba, (width, _height) = painter.rgba(self._hud(), host_controls=wide)

        assert width >= HostControlsSection().least_width(wide) + 2 * PAD > 380

    def test_a_change_in_what_the_host_shows_is_on_the_next_paint(self):
        painter = MainHudPainter()

        curved = painter.rgba(self._hud(), host_controls=a_hud("Curved"))[0]
        round_ = painter.rgba(self._hud(), host_controls=a_hud("Round"))[0]

        assert curved != round_

    def test_a_minimized_main_hud_has_none_to_press(self):
        painter = MainHudPainter()
        painter.rgba(self._hud(), host_controls=a_hud())
        hud = self._hud()
        minimized = replace(hud, main_hud_model=replace(hud.main_hud_model, hud_minimized=True))

        painter.rgba(minimized, host_controls=a_hud())

        assert painter.host_controls_layout is None


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
            modes=ModeHud(video="scene one"),
            main_hud_model=MainHudModel(hud_corner=corner, rows=main_hud_rows(),
                                 osr2_controls=osr2_controls(broker_running=True), **main_hud_model))

    def _painted(self, corner, **main_hud_model):
        painter = MainHudPainter(width=420)
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

        left = self._painted(HudCorner.UPPER_LEFT, max_intensity=35)
        right = self._painted(HudCorner.UPPER_RIGHT, max_intensity=35)

        assert (_button_rect(right, "broker_panel")[0]
                > _button_rect(left, "broker_panel")[0]), "the line did not move"
        assert slider_past_broker(right) == slider_past_broker(left)

    @pytest.mark.parametrize("corner", [HudCorner.UPPER_LEFT, HudCorner.UPPER_RIGHT])
    def test_the_title_moves_over_for_the_minus_in_the_huds_corner(self, corner):
        painter = self._painted(corner)
        x, y, w, h = _button_rect(painter, "main_hud_minimize")
        rgba = np.asarray(painter._image).astype(int)
        fill = rgba[y + h // 2, rgba.shape[1] // 2]
        bar = rgba[y:y + h, 2:rgba.shape[1] - 2]
        drawn = [column + 2 for column in np.nonzero(
            (np.abs(bar - fill).sum(axis=2) > 12).any(axis=0))[0]
            if not x <= column + 2 < x + w]

        assert drawn, "the title drew nothing"
        assert ((max(drawn) < x - BUTTON_GAP) if corner.right
                else (min(drawn) >= x + w + BUTTON_GAP))

    @pytest.mark.parametrize("corner", [HudCorner.LOWER_LEFT, HudCorner.LOWER_RIGHT])
    def test_the_clips_row_moves_over_for_the_minus_in_a_lower_corner(self, corner):
        painter = MainHudPainter(width=420)
        painter.bgra(self._hud(corner), item_row=RowHud(position_ms=1_000,
                                                        duration_ms=60_000))
        x, y, w, h = _button_rect(painter, "main_hud_minimize")
        rx, ry, rw, rh = painter.row.rect

        beside = "the minus is not beside the row"
        assert ry < y + h, beside
        assert y < ry + rh, beside
        assert (rx + rw <= x) if corner.right else (rx >= x + w)

    def test_a_minimized_main_hud_is_the_restore_button_and_nothing_else(self):
        painter = self._painted(HudCorner.LOWER_LEFT, hud_minimized=True)
        (rect, button), = painter.buttons

        assert rect[2:] == (BUTTON, BUTTON)
        assert button.command == "main_hud_restore"
        assert painter.tracks == []

    def test_it_says_where_the_hud_it_painted_sits_and_whether_it_is_minimized(self):
        painter = self._painted(HudCorner.LOWER_LEFT, hud_minimized=True)

        assert painter.hud_place == HudPlace("main", HudCorner.LOWER_LEFT, MARGIN,
                                             minimized=True, inset=(PAD, PAD))

    def test_before_it_has_painted_anything_it_says_nowhere(self):
        assert MainHudPainter().hud_place is None

    def test_a_minimized_main_hud_keeps_the_plus_in_its_own_corner(self):
        painter = self._painted(HudCorner.LOWER_LEFT, hud_minimized=True)
        (x, y, _w, _h), _button = painter.buttons[0]
        width, height = painter._image.size

        assert (x, y + BUTTON) == (0, height)
        assert width > BUTTON


def _dividers(bgra) -> list[int]:
    rgba = bgra[:, :, [2, 1, 0, 3]]
    return [y for y in range(rgba.shape[0]) if (rgba[y] == (*BORDER_PANEL, 255)).all()]


def _span(rects) -> tuple[int, int]:
    rects = list(rects)
    return min(y for _x, y, _w, _h in rects), max(y + h for _x, y, _w, h in rects)


class TestEverySectionIsSetOffFromTheNextByALine:
    def test_a_main_hud_carrying_every_section_has_a_line_between_each_and_the_next(self):
        painter = MainHudPainter()
        drive = _drive()
        bgra = painter.bgra(MainHud(
            modes=ModeHud(video="scene one"),
            main_hud_model=MainHudModel(main_mode=MainMode.KINO, osr2=Osr2State.ROBOT_HAND,
                                 rows=main_hud_rows(), osr2_rows=motion_rows(),
                                 osr2_controls=osr2_controls(broker_running=True)),
            drive=drive), item_row=RowHud(duration_ms=60_000))
        controls = _span(rect for rect, button in _declared(painter)
                         if button.command.startswith(("main_", "genau_")))
        visualizer_top = painter.tracks[0].rect[1] - tracks(0, 0, drive)[0].rect[1]
        device = (_button_rect(painter, "robot_hand_toggle_learned")[1],
                  visualizer_top + section_size()[1])
        _x, row_y, _w, _row_h = painter.row.rect

        lines = _dividers(bgra)

        assert len(lines) == 3
        assert lines[0] < controls[0]
        assert controls[1] <= lines[1] < device[0]
        assert device[1] <= lines[2] < row_y
        assert (_rgb(bgra)[lines[0] + 1:controls[0], 1:-1] == BG_PRIMARY).all()


class TestADeviceOnlyMainHud:
    @staticmethod
    def _painted() -> tuple[MainHudPainter, np.ndarray]:
        painter = MainHudPainter(device_only=True)
        bgra = painter.bgra(MainHud(
            modes=ModeHud(video="scene one"),
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND,
                                 rows=main_hud_rows("genau"), osr2_rows=motion_rows(),
                                 osr2_controls=osr2_controls(broker_running=True)),
            drive=_drive()), item_row=RowHud(duration_ms=60_000))
        return painter, bgra

    def test_it_has_no_minus_since_nothing_under_it_could_be_uncovered(self):
        painter, _bgra = self._painted()

        assert minimize_command("main") not in [button.command for _r, button in painter.buttons]

    def test_its_first_line_is_the_row_that_aims_the_device(self):
        painter, bgra = self._painted()

        assert _button_rect(painter, "robot_hand_toggle_learned")[1] == PAD
        assert _dividers(bgra) == []

    def test_nothing_is_drawn_beside_the_row_that_aims_the_device(self):
        painter, bgra = self._painted()
        x, y, w, h = _button_rect(painter, "robot_hand_toggle_learned")

        assert (_rgb(bgra)[y:y + h, x + w:-1] == BG_PRIMARY).all()

    def test_it_keeps_no_room_for_a_minus_in_a_lower_corner(self):
        painter = MainHudPainter(device_only=True)
        painter.bgra(MainHud(
            modes=ModeHud(video="scene one"),
            main_hud_model=MainHudModel(main_mode=MainMode.GENAU, osr2=Osr2State.ROBOT_HAND,
                                 hud_corner=HudCorner.LOWER_LEFT, osr2_rows=motion_rows(),
                                 osr2_controls=osr2_controls(broker_running=True)),
            drive=_drive()))

        assert _button_rect(painter, "robot_hand_toggle_learned")[0] == PAD

    def test_a_long_name_for_the_video_does_not_widen_it(self):
        def width(video: str) -> int:
            return MainHudPainter(device_only=True).rgba(MainHud(
                modes=ModeHud(video=video),
                main_hud_model=MainHudModel(osr2_rows=motion_rows()), drive=_drive()))[1][0]

        assert width("Jane Doe - scene one - " + "a long descriptor " * 6) == width("")
