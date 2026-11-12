from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from shared_ui.spacing import BUTTON_SIZE_HUD

from funestra.hud_button import Button
from funestra.hud_corners import HudPlace
from funestra.hud_minimize import collapsed_hud
from funestra.hud_overlay import (
    DrawnOn,
    DriveFeed,
    HudOverlay,
    PublishedHud,
    WindowsOwnHud,
)
from funestra.hud_placement import HudCorner, HudEdge
from funestra.hud_row import UNDER_THE_HUD_GAP, ItemRowDraw, RowHud, RowPress
from funestra.name_copy import COPY_NAME, COPY_TOOLTIP
from funestra.osr2_visualizer import DriveHud, DrivePublisher, publish_drive, read_drive
from funestra.satellite_hud import MARGIN, MINUS_INSET, PAD, HudModel
from funestra.satellite_hud_paint import HudRenderer
from funestra.scrubber_bar import SCRUBBER_HEIGHT
from funestra.testing import FakeEngine
from funestra.volume import (
    SPEAKER_W,
    VOLUME_CONTROL_H,
    VOLUME_CONTROL_W,
    VolumeHud,
    volume_control_xy,
)


@pytest.fixture
def hud(tmp_path: Path) -> Path:
    thumb = tmp_path / "t.jpg"
    Image.new("RGB", (40, 60), (90, 90, 90)).save(thumb)
    path = tmp_path / "portrait_hud.json"
    path.write_text(json.dumps({
        "funestra": "portrait", "locked": False, "title": "Unlocked",
        "current_action": "alpha",
        "corner": {"path": "C:/v/cur.mp4", "thumb": str(thumb)},
        "seeds": [{"path": "C:/v/s1.mp4", "thumb": str(thumb)}],
        "actions": [{"path": "C:/v/a1.mp4", "thumb": str(thumb), "label": "gamma"}],
    }), encoding="utf-8")
    return path


def _overlay(tmp_path: Path, hud_path: Path, engine, clock=None, **parts) -> HudOverlay:
    drawn_on = parts.pop("drawn_on", None) or DrawnOn(engine)
    return HudOverlay(
        source=PublishedHud(hud_path, tmp_path / "dashboard_cmd.txt"),
        drawn_on=drawn_on, clock=clock or (lambda: 0.0), **parts,
    )


def _commands(tmp_path: Path) -> list[str]:
    path = tmp_path / "dashboard_cmd.txt"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]




def _colors_across(row) -> list[tuple[int, int, int]]:
    x0, x1 = row.track
    return [(200, 40, 40)] * (x1 - x0)


class TestTheClipsRowAtItsFootSinceAlongAWrappedVideosEdgeItSmearsOutOfTheControllersReach:
    _ROW = RowHud(position_ms=0.0, duration_ms=10_000.0,
                  volume=VolumeHud(volume=80, muted=False))

    def test_a_window_handed_a_row_draws_it_on_the_hud(self, tmp_path, hud):
        engine = FakeEngine()
        overlay = _overlay(tmp_path, hud, engine)

        overlay.tick(item_row=ItemRowDraw(self._ROW))

        assert overlay.targets.row is not None

    def test_an_image_puts_no_row_on_the_hud(self, tmp_path, hud):
        engine = FakeEngine()
        overlay = _overlay(tmp_path, hud, engine)

        overlay.tick(item_row=None)

        assert overlay.targets.row is None

    def _on_the_row(self, overlay, px, py):
        x, y, _width, _height = overlay.targets.row.rect
        return MARGIN + x + px, MARGIN + y + py

    def test_a_press_along_the_track_runs_the_clip_there(self, tmp_path, hud):
        seeks: list[float] = []
        overlay = _overlay(tmp_path, hud, FakeEngine(), row=RowPress(seek=seeks.append))
        overlay.tick(item_row=ItemRowDraw(self._ROW))
        _x, _y, _width, height = overlay.targets.row.rect
        x0, x1 = overlay.targets.row.track

        overlay.press(*self._on_the_row(overlay, (x0 + x1) // 2,
                                        height - SCRUBBER_HEIGHT // 2))

        assert seeks == [pytest.approx(5_000.0, abs=200)]

    def test_a_drag_along_the_track_keeps_running_the_clip(self, tmp_path, hud):
        seeks: list[float] = []
        overlay = _overlay(tmp_path, hud, FakeEngine(), row=RowPress(seek=seeks.append))
        overlay.tick(item_row=ItemRowDraw(self._ROW))
        _x, _y, _width, height = overlay.targets.row.rect
        x0, x1 = overlay.targets.row.track
        along = height - SCRUBBER_HEIGHT // 2

        overlay.press(*self._on_the_row(overlay, x0, along))
        overlay.drag_to(*self._on_the_row(overlay, (x0 + x1) // 2, along))

        assert seeks[-1] == pytest.approx(5_000.0, abs=200)

    def test_a_press_on_the_speaker_mutes_and_a_drag_across_it_does_not(self, tmp_path, hud):
        mutes: list[int] = []
        levels: list[int] = []
        overlay = _overlay(tmp_path, hud, FakeEngine(), row=RowPress(
            set_volume=levels.append, toggle_mute=lambda: mutes.append(1)))
        overlay.tick(item_row=ItemRowDraw(self._ROW))
        _x, _y, width, height = overlay.targets.row.rect
        cx, cy = volume_control_xy(viewport_w=width, viewport_h=height, timeline_h=SCRUBBER_HEIGHT)

        overlay.press(*self._on_the_row(overlay, cx + SPEAKER_W // 2, cy + VOLUME_CONTROL_H // 2))
        overlay.drag_to(*self._on_the_row(overlay, cx + VOLUME_CONTROL_W - 2, cy + VOLUME_CONTROL_H // 2))

        assert mutes == [1]
        assert levels == []

    def test_a_scripted_clip_colors_its_track(self, tmp_path, hud):
        plain, scripted = FakeEngine(), FakeEngine()
        _overlay(tmp_path, hud, plain).tick(item_row=ItemRowDraw(self._ROW))
        colored = _overlay(tmp_path, hud, scripted)
        colored.tick(item_row=ItemRowDraw(self._ROW))
        colored.tick(item_row=ItemRowDraw(self._ROW, _colors_across(colored.row)))

        (_x, _y, bare), = plain.overlays.values()
        (_x, _y, filled), = scripted.overlays.values()
        assert bare.shape == filled.shape
        assert not (bare == filled).all()

    def test_a_fill_measured_across_some_other_track_is_dropped(self, tmp_path, hud):
        plain, mismatched = FakeEngine(), FakeEngine()
        _overlay(tmp_path, hud, plain).tick(item_row=ItemRowDraw(self._ROW))
        overlay = _overlay(tmp_path, hud, mismatched)
        overlay.tick(item_row=ItemRowDraw(self._ROW))
        overlay.tick(item_row=ItemRowDraw(self._ROW, [(255, 0, 0)] * 7))

        (_x, _y, bare), = plain.overlays.values()
        (_x, _y, drawn), = mismatched.overlays.values()
        assert (bare == drawn).all()

    def test_the_host_is_told_where_the_row_landed(self, tmp_path, hud):
        overlay = _overlay(tmp_path, hud, FakeEngine())

        overlay.tick(item_row=ItemRowDraw(self._ROW))

        x, _y, _width, _height = overlay.row.rect
        x0, x1 = overlay.row.track
        left, top, _w, _h = (MARGIN, MARGIN, 0, 0)
        hud_h = overlay._engine.overlays[overlay.overlay_id][2].shape[0]
        assert overlay.row_track == (left + x + x0, left + x + x1,
                                     top + hud_h + UNDER_THE_HUD_GAP)

    def test_an_image_leaves_nothing_for_the_frames_to_hang_under(self, tmp_path, hud):
        overlay = _overlay(tmp_path, hud, FakeEngine())

        overlay.tick(item_row=None)

        assert overlay.row is None
        assert overlay.row_track is None


def test_tick_composites_the_hud_at_the_hud_inset(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    _overlay(tmp_path, hud, engine).tick()

    assert len(engine.overlays) == 1
    (x, y, bgra), = engine.overlays.values()
    assert (x, y) == (MARGIN, MARGIN)
    assert bgra.shape[2] == 4


def test_tick_redraws_only_when_the_published_hud_changes(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)

    overlay.tick()
    first = engine.overlays[overlay.overlay_id][2]
    overlay.tick()
    assert engine.overlays[overlay.overlay_id][2] is first

    hud.write_text(hud.read_text(encoding="utf-8").replace(
        '"locked": false', '"locked": true'), encoding="utf-8")
    overlay.tick()
    assert engine.overlays[overlay.overlay_id][2] is not first


def test_tick_redraws_when_the_clip_on_screen_changes_since_fun_time_republishes_only_when_the_nav_map_moves(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)

    overlay.tick(video="one")
    first = engine.overlays[overlay.overlay_id][2]
    overlay.tick(video="one")
    assert engine.overlays[overlay.overlay_id][2] is first

    overlay.tick(video="two")
    assert engine.overlays[overlay.overlay_id][2] is not first


def test_the_funestras_own_rate_brings_a_speed_row_whose_buttons_post_this_sides_speed(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick(playback_speed=1.0)
    rect = {b.command: r for r, b in overlay.targets.buttons}["portrait_speed_up"]

    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["portrait_speed_up"]


def test_tick_redraws_when_the_funestras_rate_changes(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)

    overlay.tick(playback_speed=1.0)
    first = engine.overlays[overlay.overlay_id][2]
    overlay.tick(playback_speed=1.0)
    assert engine.overlays[overlay.overlay_id][2] is first

    overlay.tick(playback_speed=1.5)
    assert engine.overlays[overlay.overlay_id][2] is not first


def test_no_hud_file_means_no_overlay(tmp_path: Path):
    engine = FakeEngine()
    _overlay(tmp_path, tmp_path / "absent.json", engine).tick()

    assert engine.overlays == {}


def test_the_overlay_is_removed_when_the_hud_goes_away(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()

    hud.unlink()
    overlay.tick()

    assert engine.overlays == {}


def test_a_hud_that_cannot_be_read_this_frame_keeps_the_nav_map_up(
    tmp_path: Path, hud: Path, monkeypatch: pytest.MonkeyPatch
):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    drawn = engine.overlays[overlay.overlay_id][2]

    real_read_text = Path.read_text

    def refuse(self, *args, **kwargs):
        if self == hud:
            raise PermissionError(32, "The process cannot access the file")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", refuse)
    overlay.tick()

    assert engine.overlays[overlay.overlay_id][2] is drawn


class _EngineOutOfMemory(FakeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.out_of_memory = False

    def overlay(self, ident: int, x: int, y: int, bgra) -> None:
        if self.out_of_memory:
            raise MemoryError
        super().overlay(ident, x, y, bgra)


def _locked(hud: Path) -> None:
    hud.write_text(hud.read_text(encoding="utf-8").replace(
        '"locked": false', '"locked": true'), encoding="utf-8")


def test_a_hud_the_engine_has_no_memory_to_put_up_keeps_the_last_one_until_it_has(
        tmp_path: Path, hud: Path):
    engine = _EngineOutOfMemory()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    drawn = engine.overlays[overlay.overlay_id][2]

    _locked(hud)
    engine.out_of_memory = True
    with pytest.raises(MemoryError):
        overlay.tick()
    kept = engine.overlays[overlay.overlay_id][2]
    engine.out_of_memory = False
    overlay.tick()

    assert kept is drawn
    assert engine.overlays[overlay.overlay_id][2] is not drawn


def test_presses_land_on_the_hud_on_screen_while_the_next_cannot_be_put_up(
        tmp_path: Path, hud: Path):
    engine = _EngineOutOfMemory()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    targets = overlay.targets

    _locked(hud)
    engine.out_of_memory = True
    with pytest.raises(MemoryError):
        overlay.tick()

    assert overlay.targets is targets


def test_a_hud_there_is_no_memory_to_paint_keeps_the_last_one_until_there_is(
        tmp_path: Path, hud: Path, monkeypatch: pytest.MonkeyPatch):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    drawn = engine.overlays[overlay.overlay_id][2]
    paint = HudRenderer.render
    out_of_memory = [True]

    def render(self, *args, **kwargs):
        if out_of_memory[0]:
            raise MemoryError
        return paint(self, *args, **kwargs)

    monkeypatch.setattr(HudRenderer, "render", render)
    _locked(hud)
    with pytest.raises(MemoryError):
        overlay.tick()
    kept = engine.overlays[overlay.overlay_id][2]
    out_of_memory[0] = False
    overlay.tick()

    assert kept is drawn
    assert engine.overlays[overlay.overlay_id][2] is not drawn


def test_a_single_click_posts_the_switch_once_its_window_lapses(tmp_path: Path, hud: Path):
    now = [0.0]
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine, clock=lambda: now[0])
    overlay.tick()
    corner_rect = overlay.targets.click[0][0]

    overlay.press(corner_rect[0] + MARGIN + 2, corner_rect[1] + MARGIN + 2)
    overlay.tick()
    assert _commands(tmp_path) == []

    now[0] = 1.0
    overlay.tick()
    assert _commands(tmp_path) == ["portrait_play_video|C:/v/cur.mp4"]


def test_a_double_click_locks_instead_of_switching(tmp_path: Path, hud: Path):
    now = [0.0]
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine, clock=lambda: now[0])
    overlay.tick()
    x, y, _w, _h = overlay.targets.click[1][0]

    overlay.press(x + MARGIN + 2, y + MARGIN + 2)
    now[0] = 0.2
    overlay.press(x + MARGIN + 2, y + MARGIN + 2)
    now[0] = 2.0
    overlay.tick()

    assert _commands(tmp_path) == ["portrait_lock_video|C:/v/s1.mp4"]


def test_a_loop_button_click_posts_at_once(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    rect = {kind: r for r, kind in overlay.targets.loop}["seed"]

    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["portrait_seed_loop"]


def test_a_press_outside_the_hud_posts_nothing_and_is_refused(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()

    taken = [
        overlay.press(2, 2),
        overlay.press(2000, 2000),
    ]

    assert taken == [False, False]
    assert _commands(tmp_path) == []


def test_a_press_between_the_huds_controls_is_still_the_huds(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    _x, _y, bgra = engine.overlays[overlay.overlay_id]
    height, width = bgra.shape[:2]

    taken = overlay.press(MARGIN + width - 1, MARGIN + height - 1)

    assert taken is True
    assert _commands(tmp_path) == []


def test_no_hud_on_screen_takes_no_press(tmp_path: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, tmp_path / "absent.json", engine)
    overlay.tick()

    assert overlay.press(MARGIN + 2, MARGIN + 2) is False


def test_a_button_with_no_tooltip_lights_under_the_pointer_and_draws_no_tooltip(
        tmp_path: Path, hud: Path):
    published = json.loads(hud.read_text(encoding="utf-8"))
    published["rows"] = [[{"command": "go_kino", "glyph": "Kino", "tooltip": ""},
                          {"command": "go_genau", "glyph": "Genau", "tooltip": ""}]]
    hud.write_text(json.dumps(published), encoding="utf-8")
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    plain = engine.overlays[overlay.overlay_id][2]
    rects = {button.command: rect for rect, button in overlay.targets.buttons}
    kino_rect, genau_rect = rects["go_kino"], rects["go_genau"]

    overlay.motion(kino_rect[0] + MARGIN + 2, kino_rect[1] + MARGIN + 2)
    on_kino = engine.overlays[overlay.overlay_id][2]
    overlay.motion(genau_rect[0] + MARGIN + 2, genau_rect[1] + MARGIN + 2)
    on_genau = engine.overlays[overlay.overlay_id][2]

    assert plain.shape == on_kino.shape
    assert bytes(on_kino) != bytes(plain)
    assert bytes(on_genau) != bytes(on_kino)


def test_hovering_a_button_redraws_with_its_tooltip_and_clears_it_to_the_very_pixels_from_before(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    plain = engine.overlays[overlay.overlay_id][2]
    rect = {kind: r for r, kind in overlay.targets.loop}["action"]

    overlay.motion(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    hovered = engine.overlays[overlay.overlay_id][2]
    assert bytes(hovered) != bytes(plain)

    overlay.motion(MARGIN + 2, MARGIN + 2)
    cleared = engine.overlays[overlay.overlay_id][2]
    assert bytes(cleared) == bytes(plain)


def _copy_icon(targets) -> tuple[int, int, int, int]:
    return next(rect for rect, button in targets.buttons if button.command == COPY_NAME)


def test_a_press_on_the_copy_icon_puts_the_whole_name_on_the_clipboard_and_posts_nothing(
        tmp_path: Path, hud: Path):
    copied = []
    overlay = _overlay(tmp_path, hud, FakeEngine(), clipboard=copied.append)
    overlay.tick(video="a name long enough that the line runs out of room for it " * 3)

    x, y, w, h = _copy_icon(overlay.targets)
    overlay.press(x + w // 2 + MARGIN, y + h // 2 + MARGIN)

    assert copied == ["a name long enough that the line runs out of room for it " * 3]
    assert _commands(tmp_path) == []


def test_the_copy_icon_names_what_it_does(tmp_path: Path, hud: Path):
    overlay = _overlay(tmp_path, hud, FakeEngine())
    overlay.tick(video="video one")

    copy = next(button for _rect, button in overlay.targets.buttons if button.command == COPY_NAME)

    assert copy.tooltip_on_hover == COPY_TOOLTIP


def test_with_no_name_on_the_hud_there_is_nothing_to_copy(tmp_path: Path, hud: Path):
    overlay = _overlay(tmp_path, hud, FakeEngine())
    overlay.tick(video="")

    assert not [button for _rect, button in overlay.targets.buttons if button.command == COPY_NAME]


def test_pressing_the_lit_filter_button_lifts_the_filter(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    hud.write_text(hud.read_text(encoding="utf-8").replace(
        '"funestra": "portrait"', '"funestra": "portrait", "filter_query": "alpha"'), encoding="utf-8")
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()

    rect = {name: r for r, name in overlay.targets.filter}["alpha"]
    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["portrait_no_filter"]


def test_pressing_an_unlit_filter_button_filters_to_its_act(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()

    rect = {name: r for r, name in overlay.targets.filter}["gamma"]
    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["filter_portrait_gamma"]


def test_the_published_loop_state_wins_over_the_optimistic_one(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, hud, engine)
    overlay.tick()
    rect = {kind: r for r, kind in overlay.targets.loop}["seed"]
    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)
    assert overlay.active_loop == "seed"

    hud.write_text(hud.read_text(encoding="utf-8").replace(
        '"funestra": "portrait"', '"funestra": "portrait", "active_loop": ""'), encoding="utf-8")
    overlay.tick()

    assert overlay.active_loop == ""




def _give_it_the_osr2(hud: Path) -> None:
    published = json.loads(hud.read_text(encoding="utf-8"))
    published.update(osr2="robot_hand", osr2_control="driving")
    hud.write_text(json.dumps(published), encoding="utf-8")


def _publish_motion(path: Path, offset: float) -> None:
    publish_drive(path, DriveHud(
        speed=50, amplitude=80, center=50,
        waveform=tuple(0.5 + 0.4 * math.sin(i / 6 + offset) for i in range(80))))


def _overlay_with_the_motion(tmp_path: Path, hud: Path, engine) -> HudOverlay:
    return _overlay(tmp_path, hud, engine, drive=DriveFeed(tmp_path / "drive.txt"))


class TestAHudWithTheOsr2:
    def test_draws_the_motion_genau_publishes_under_the_osr2_line(self, tmp_path: Path, hud: Path):
        _give_it_the_osr2(hud)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_with_the_motion(tmp_path, hud, FakeEngine())

        overlay.tick()

        assert overlay.targets.tracks

    def test_redraws_as_the_motion_moves(self, tmp_path: Path, hud: Path):
        _give_it_the_osr2(hud)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        engine = FakeEngine()
        overlay = _overlay_with_the_motion(tmp_path, hud, engine)
        overlay.tick()
        first = engine.overlays[overlay.overlay_id][2].copy()

        _publish_motion(tmp_path / "drive.txt", 3.0)
        overlay.tick()

        assert not (engine.overlays[overlay.overlay_id][2] == first).all()

    def test_a_hud_without_it_draws_no_motion(self, tmp_path: Path, hud: Path):
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_with_the_motion(tmp_path, hud, FakeEngine())

        overlay.tick()

        assert overlay.targets.tracks == []

    def test_a_band_of_the_visualizer_keeps_a_drag_until_it_is_let_go(self, tmp_path: Path, hud: Path):
        _give_it_the_osr2(hud)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_with_the_motion(tmp_path, hud, FakeEngine())
        overlay.tick()
        x, y, w, h = next(bar.rect for bar in overlay.targets.tracks if bar.axis == "speed")

        overlay.press(MARGIN + x + 1, MARGIN + y + h // 2)
        dragged = overlay.drag_to(MARGIN + x + w - 2, MARGIN + y + h // 2)
        overlay.release()

        assert _commands(tmp_path) == ["robot_hand_speed_1", "robot_hand_speed_99"]
        assert dragged == "robot_hand_speed_99"
        assert overlay.holding is False


def _overlay_handing_on_the_motion(tmp_path: Path, hud: Path, engine) -> HudOverlay:
    return _overlay(tmp_path, hud, engine, drive=DriveFeed(
        tmp_path / "drive.txt", visualizer=DrivePublisher(tmp_path / "visualizer.txt")))


class TestAHudWhoseHostDrawsTheOsr2:
    def test_hands_its_host_the_motion_it_would_have_drawn(self, tmp_path: Path, hud: Path):
        _give_it_the_osr2(hud)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_handing_on_the_motion(tmp_path, hud, FakeEngine())

        overlay.tick()

        assert read_drive(tmp_path / "visualizer.txt") == read_drive(tmp_path / "drive.txt")

    def test_a_hud_without_the_osr2_hands_on_nothing(self, tmp_path: Path, hud: Path):
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_handing_on_the_motion(tmp_path, hud, FakeEngine())

        overlay.tick()

        assert not (tmp_path / "visualizer.txt").exists()

    def test_draws_its_own_hud_as_one_without_the_osr2(self, tmp_path: Path, hud: Path):
        plain_engine, handing_engine = FakeEngine(), FakeEngine()
        plain = _overlay(tmp_path, hud, plain_engine)
        plain.tick()
        _give_it_the_osr2(hud)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        handing = _overlay_handing_on_the_motion(tmp_path, hud, handing_engine)

        handing.tick()

        assert np.array_equal(handing_engine.overlays[handing.overlay_id][2],
                              plain_engine.overlays[plain.overlay_id][2])

    def test_does_not_redraw_its_hud_as_the_motion_moves(self, tmp_path: Path, hud: Path):
        _give_it_the_osr2(hud)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        engine = FakeEngine()
        overlay = _overlay_handing_on_the_motion(tmp_path, hud, engine)
        overlay.tick()
        engine.overlays[overlay.overlay_id] = "drawn before"

        _publish_motion(tmp_path / "drive.txt", 3.0)
        overlay.tick()

        assert engine.overlays[overlay.overlay_id] == "drawn before"


class _Gate:
    def __init__(self, composed: DriveHud) -> None:
        self.asked: list[tuple[DriveHud | None, bool]] = []
        self._composed = composed

    def visualizer(self, published, *, device_drives_itself: bool = False) -> DriveHud:
        self.asked.append((published, device_drives_itself))
        return self._composed


class TestAHudWithTheOsr2ItsOwnFunestraScripts:
    def test_draws_genaus_motion_with_the_funestras_own_script_folded_in(self, tmp_path, hud):
        _give_it_the_osr2(hud)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        composed = DriveHud(speed=50, amplitude=80, center=50, driven="funscript",
                            waveform=tuple(0.2 for _ in range(80)))
        gate = _Gate(composed)
        overlay = _overlay(tmp_path, hud, FakeEngine(),
                           drive=DriveFeed(tmp_path / "drive.txt", gate))

        overlay.tick()

        ((published, drives_itself),) = gate.asked
        assert published.amplitude == 80
        assert drives_itself is False
        assert overlay.targets.tracks


def _publish(hud_path: Path, **hud_changes) -> None:
    published = json.loads(hud_path.read_text(encoding="utf-8"))
    published.update(hud_changes)
    hud_path.write_text(json.dumps(published), encoding="utf-8")


def _hud_at(tmp_path: Path, hud_path: Path, engine, **hud_changes):
    _publish(hud_path, **hud_changes)
    overlay = _overlay(tmp_path, hud_path, engine)
    overlay.tick(viewport=(1200, 800))
    return overlay


@pytest.mark.parametrize("corner", list(HudCorner))
def test_the_minus_sits_where_the_plus_of_the_minimized_hud_sits_so_a_second_click_in_the_same_place_opens_it_again(
        tmp_path: Path, hud: Path, corner: HudCorner):
    engine = FakeEngine()
    overlay = _hud_at(tmp_path, hud, engine, hud_corner=corner.value)
    (left, top, _bgra), = engine.overlays.values()
    (x, y, w, h), = [rect for rect, b in overlay.targets.buttons
                     if b.command == "portrait_hud_minimize"]

    _publish(hud, hud_minimized=True)
    overlay.tick(viewport=(1200, 800))

    (plus_left, plus_top, _bgra), = engine.overlays.values()
    ((px, py, pw, ph), _plus), = overlay.targets.buttons
    assert (plus_left + px, plus_top + py, pw, ph) == (left + x, top + y, w, h)


def test_the_hud_is_composited_in_the_corner_the_session_moved_it_to(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()

    _hud_at(tmp_path, hud, engine, hud_corner="lower_right")

    (x, y, bgra), = engine.overlays.values()
    height, width = bgra.shape[:2]
    assert x == 1200 - MARGIN - width
    assert y == 800 - MARGIN - height


def test_a_press_in_a_lower_corner_reaches_the_button_drawn_there(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _hud_at(tmp_path, hud, engine, hud_corner="lower_right",
                      rows=[[{"command": "portrait_next", "glyph": "N",
                              "tooltip": "Next", "width": 18}]])
    (left, top, _bgra), = engine.overlays.values()
    (bx, by, bw, bh), _button = next(
        (rect, b) for rect, b in overlay.targets.buttons if b.command == "portrait_next")

    assert overlay.press(left + bx + bw // 2, top + by + bh // 2) is True
    assert _commands(tmp_path) == ["portrait_next"]


def test_the_plus_names_itself_where_the_hud_floats_over_an_item_taking_the_tooltip_s_room_only_while_pointed_at_so_a_press_beside_it_still_reaches_the_video(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _hud_at(tmp_path, hud, engine, hud_minimized=True,
                      hud_corner="upper_left")
    (left, top, resting), = [(x, y, bgra) for x, y, bgra in engine.overlays.values()]

    overlay.motion(left + BUTTON_SIZE_HUD // 2, top + BUTTON_SIZE_HUD // 2)
    (x, y, hovered), = [(x, y, bgra) for x, y, bgra in engine.overlays.values()]

    assert resting.shape[:2] == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)
    assert hovered.shape[1] > BUTTON_SIZE_HUD
    assert (x, y) == (left, top)


def test_a_hud_on_its_own_screen_holds_the_tooltips_room_from_the_start_since_growing_under_the_pointer_would_carry_the_plus_out_from_under_it(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()
    _publish(hud, hud_minimized=True)
    overlay = _overlay(tmp_path, hud, engine, drawn_on=DrawnOn(engine, over_the_video=False))

    overlay.tick()

    (_x, _y, bgra), = engine.overlays.values()
    assert bgra.shape[1] > BUTTON_SIZE_HUD


class TestAHudWhoseMinusHangsOutsideIt:
    @staticmethod
    def _overlay(tmp_path: Path, hud: Path, engine) -> HudOverlay:
        return _overlay(tmp_path, hud, engine, drawn_on=DrawnOn(
            engine, over_the_video=False, minus_on_the_hud=False))

    def test_the_hud_draws_no_minus(self, tmp_path: Path, hud: Path):
        engine = FakeEngine()
        overlay = self._overlay(tmp_path, hud, engine)

        overlay.tick()

        assert engine.overlays
        assert not [b for _rect, b in overlay.targets.buttons
                    if b.command == "portrait_hud_minimize"]

    def test_a_minimized_hud_draws_nothing(self, tmp_path: Path, hud: Path):
        engine = FakeEngine()
        _publish(hud, hud_minimized=True)
        overlay = self._overlay(tmp_path, hud, engine)

        overlay.tick()

        assert engine.overlays == {}
        assert overlay.targets.buttons == []


def test_a_hud_collapsed_by_a_press_on_its_minus_draws_the_plus_alone(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _hud_at(tmp_path, hud, engine, hud_corner="upper_left")
    (left, top, _bgra), = engine.overlays.values()
    (x, y, w, h), _minus = next((rect, b) for rect, b in overlay.targets.buttons
                                if b.command == "portrait_hud_minimize")
    overlay.motion(left + x + w // 2, top + y + h // 2)
    overlay.press(left + x + w // 2, top + y + h // 2)

    _publish(hud, hud_minimized=True)
    overlay.tick(viewport=(1200, 800))

    (_x, _y, bgra), = engine.overlays.values()
    assert bgra.shape[:2] == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)


def test_its_place_is_the_corner_the_room_put_it_in_and_whether_it_is_minimized(
        tmp_path: Path, hud: Path):
    overlay = _hud_at(tmp_path, hud, FakeEngine(), hud_minimized=True,
                      hud_corner="upper_right")

    assert overlay.hud_place == HudPlace("portrait", HudCorner.UPPER_RIGHT, MARGIN,
                                         minimized=True, inset=MINUS_INSET)


def test_a_hud_with_nothing_published_has_no_place(tmp_path: Path):
    overlay = _overlay(tmp_path, tmp_path / "unpublished.json", FakeEngine())

    overlay.tick(viewport=(1200, 800))

    assert overlay.hud_place is None


def test_a_minimized_hud_is_the_plus_button_in_that_corner(tmp_path: Path, hud: Path):
    engine = FakeEngine()
    overlay = _hud_at(tmp_path, hud, engine, hud_minimized=True,
                      hud_corner="upper_right")
    (x, y, bgra), = engine.overlays.values()
    height, width = bgra.shape[:2]

    assert (width, height) == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)
    across, down = MINUS_INSET
    assert (x, y) == (1200 - MARGIN - across - width, MARGIN + down)
    assert [b.command for _rect, b in overlay.targets.buttons] == ["portrait_hud_restore"]


class TestANameFlashingWhileMinimized:
    def test_it_is_drawn_beside_the_plus(self, tmp_path: Path, hud: Path):
        engine = FakeEngine()
        _publish(hud, hud_minimized=True)
        overlay = _overlay(tmp_path, hud, engine)

        overlay.tick(viewport=(1200, 800), flash="scene one")

        (_x, _y, bgra), = engine.overlays.values()
        assert np.array_equal(bgra, collapsed_hud("portrait", flash="scene one")[0])

    def test_the_plus_is_alone_again_once_it_is_over(self, tmp_path: Path, hud: Path):
        engine = FakeEngine()
        _publish(hud, hud_minimized=True)
        overlay = _overlay(tmp_path, hud, engine)
        overlay.tick(viewport=(1200, 800), flash="scene one")

        overlay.tick(viewport=(1200, 800))

        (_x, _y, bgra), = engine.overlays.values()
        assert bgra.shape[:2] == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)

    @pytest.mark.parametrize("corner", list(HudCorner))
    def test_the_plus_stays_where_it_was(self, tmp_path: Path, hud: Path, corner: HudCorner):
        engine = FakeEngine()
        overlay = _hud_at(tmp_path, hud, engine, hud_minimized=True, hud_corner=corner.value)
        alone = self._plus_on_the_screen(overlay, engine)

        overlay.tick(viewport=(1200, 800), flash="scene one")

        assert self._plus_on_the_screen(overlay, engine) == alone

    @staticmethod
    def _plus_on_the_screen(overlay: HudOverlay, engine) -> tuple[int, int]:
        (left, top, _bgra), = engine.overlays.values()
        ((x, y, _w, _h), _plus), = overlay.targets.buttons
        return left + x, top + y


def test_a_hud_hanging_on_its_own_screen_keeps_its_default_justification(
        tmp_path: Path, hud: Path):
    engine = FakeEngine()
    _publish(hud, hud_corner="lower_right", hud_edge="right",
             rows=[[{"command": "portrait_next", "glyph": "N",
                     "tooltip": "Next", "width": 18}]])
    overlay = _overlay(tmp_path, hud, engine, drawn_on=DrawnOn(engine, over_the_video=False))

    overlay.tick(viewport=(1200, 800))

    assert overlay.edge is HudEdge.RIGHT
    assert min(rect[0] for rect, _b in overlay.targets.buttons) == PAD
    (x, y, _bgra), = engine.overlays.values()
    assert (x, y) == (MARGIN, MARGIN)


class _Foot:
    def __init__(self, size=(120, 40)) -> None:
        self._size = size

    def size(self):
        return self._size

    def paint(self, image, x, y, width, pointer):
        return []


def _a_windows_own_hud(engine, *, foot=None, posts=None):
    model = HudModel(funestra="portrait", title="Unlocked",
                     rows=((Button("portrait_next", "N", "Next"),),), foot=foot)
    posted = [] if posts is None else posts
    overlay = HudOverlay(source=WindowsOwnHud(lambda: model, posted.append),
                         drawn_on=DrawnOn(engine), clock=lambda: 0.0)
    overlay.tick()
    return overlay, posted


class TestAWindowsOwnHud:
    def test_a_press_on_a_button_goes_back_to_the_program_that_handed_the_hud_over(self):
        engine = FakeEngine()
        overlay, posted = _a_windows_own_hud(engine)
        (x, y, w, h), _button = next((rect, b) for rect, b in overlay.targets.buttons
                                     if b.command == "portrait_next")

        overlay.press(MARGIN + x + w // 2, MARGIN + y + h // 2)

        assert posted == ["portrait_next"]

    def test_it_keeps_the_visualizer_the_program_drew_into_it(self):
        engine = FakeEngine()
        visualizer = DriveHud(speed=50, amplitude=80, center=50,
                           waveform=tuple(0.5 for _ in range(80)))
        model = HudModel(funestra="portrait", title="Unlocked", osr2="robot_hand",
                         osr2_control="driving", drive=visualizer)
        overlay = HudOverlay(source=WindowsOwnHud(lambda: model, lambda command: None),
                             drawn_on=DrawnOn(engine), clock=lambda: 0.0)

        overlay.tick()

        assert overlay.targets.tracks


class TestTheBlockAtTheFoot:
    def _foot_at(self, overlay):
        x, y, _width, _height = overlay.targets.foot
        return MARGIN + x, MARGIN + y

    def test_a_press_on_the_block_is_the_sources_with_where_it_landed(self):
        overlay, posted = _a_windows_own_hud(FakeEngine(), foot=_Foot())
        left, top = self._foot_at(overlay)

        taken = overlay.press(left + 30, top + 7)

        assert taken is True
        assert posted == ["foot_press|30|7"]

    def test_a_held_press_drags_and_the_button_coming_up_lets_go(self):
        overlay, posted = _a_windows_own_hud(FakeEngine(), foot=_Foot())
        left, top = self._foot_at(overlay)
        overlay.press(left + 30, top + 7)

        assert overlay.holding is True
        overlay.drag_to(left + 30, top + 25)
        overlay.release()

        assert posted == ["foot_press|30|7", "foot_drag|30|25", "foot_release|30|25"]
        assert overlay.holding is False

    def test_the_wheel_over_the_block_is_the_sources_too(self):
        overlay, posted = _a_windows_own_hud(FakeEngine(), foot=_Foot())
        left, top = self._foot_at(overlay)

        taken = overlay.wheel(left + 10, top + 10, -2)

        assert taken is True
        assert posted == ["foot_wheel|-2|10|10"]

    def test_the_wheel_elsewhere_on_the_hud_turns_nothing_and_is_still_the_huds(self):
        overlay, posted = _a_windows_own_hud(FakeEngine(), foot=_Foot())

        assert overlay.wheel(MARGIN + 2, MARGIN + 2, 1) is True
        assert overlay.wheel(2000, 2000, 1) is False
        assert posted == []

    def test_a_press_on_a_published_huds_block_is_said_to_that_side(
            self, tmp_path: Path, hud: Path):
        painted = tmp_path / "portrait_foot.png"
        Image.new("RGBA", (120, 40), (10, 20, 30, 255)).save(painted)
        _publish(hud, foot={"file": str(painted), "width": 120, "height": 40})
        overlay = _overlay(tmp_path, hud, FakeEngine())
        overlay.tick(viewport=(1200, 800))
        left, top = self._foot_at(overlay)

        overlay.press(left + 30, top + 7)
        overlay.release()

        assert _commands(tmp_path) == ["portrait_foot_press|30|7", "portrait_foot_release|30|7"]

    def test_a_hud_without_a_block_has_nothing_at_its_foot_to_press(self):
        overlay, _posted = _a_windows_own_hud(FakeEngine())

        assert overlay.targets.foot is None
