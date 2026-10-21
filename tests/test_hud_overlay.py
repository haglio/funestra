"""The HUD a Funestra composites over its picture: the published panel, and its clicks."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from funestra_fakes import FakeEngine
from PIL import Image
from shared_ui.spacing import BUTTON_SIZE_HUD

from funestra.drive_readout import DriveHud, publish_drive
from funestra.hud_button import Button
from funestra.hud_corners import HudPlace
from funestra.hud_minimize import collapsed_panel
from funestra.hud_overlay import HudOverlay
from funestra.hud_placement import HudCorner, HudEdge
from funestra.hud_row import UNDER_THE_PANEL_GAP, RowHud
from funestra.satellite_hud import MARGIN, MINUS_INSET, PAD, HudModel
from funestra.satellite_hud_paint import HudRenderer
from funestra.timeline import TIMELINE_HEIGHT
from funestra.volume import CHIP_H, CHIP_W, SPEAKER_W, VolumeHud, chip_xy


@pytest.fixture
def panel(tmp_path: Path) -> Path:
    """A published HUD panel on disk, with one seed and one action row."""
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


def _overlay(tmp_path: Path, panel_path: Path, engine, clock=None) -> HudOverlay:
    return HudOverlay(
        hud_file=panel_path, command_file=tmp_path / "dashboard_cmd.txt",
        engine=engine, clock=clock or (lambda: 0.0),
    )


def _commands(tmp_path: Path) -> list[str]:
    path = tmp_path / "dashboard_cmd.txt"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]




def _colors_across(row) -> list[tuple[int, int, int]]:
    """One color per pixel of the track the panel drew, which is what a host
    hands back for the next one to be filled with."""
    x0, x1 = row.track
    return [(200, 40, 40)] * (x1 - x0)


class TestTheClipsRowAtItsFoot:
    """The track, the time and the volume a window laid along the lower edge of
    its video ride on this panel: one panel on screen rather than two, and in
    the headset a wrapped video smears such a row round the nadir."""

    _ROW = RowHud(position_ms=0.0, duration_ms=10_000.0,
                  volume=VolumeHud(volume=80, muted=False))

    def test_a_window_handed_a_row_draws_it_on_the_panel(self, tmp_path, panel):
        engine = FakeEngine()
        overlay = _overlay(tmp_path, panel, engine)

        overlay.tick(clip_row=self._ROW)

        assert overlay.targets.row is not None

    def test_a_picture_puts_no_row_on_the_panel(self, tmp_path, panel):
        engine = FakeEngine()
        overlay = _overlay(tmp_path, panel, engine)

        overlay.tick(clip_row=None)

        assert overlay.targets.row is None

    def test_the_rows_rect_still_answers_under_its_old_name(self, tmp_path, panel):
        overlay = _overlay(tmp_path, panel, FakeEngine())

        overlay.tick(clip_row=self._ROW)
        assert overlay.row_rect == overlay.targets.row.rect

        overlay.tick(clip_row=None)
        assert overlay.row_rect is None

    def _on_the_row(self, overlay, px, py):
        x, y, _width, _height = overlay.targets.row.rect
        return MARGIN + x + px, MARGIN + y + py

    def test_a_press_along_the_track_runs_the_clip_there(self, tmp_path, panel):
        seeks: list[float] = []
        overlay = HudOverlay(
            hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
            engine=FakeEngine(), clock=lambda: 0.0, seek=seeks.append,
        )
        overlay.tick(clip_row=self._ROW)
        _x, _y, _width, height = overlay.targets.row.rect
        x0, x1 = overlay.targets.row.track

        overlay.press(*self._on_the_row(overlay, (x0 + x1) // 2,
                                        height - TIMELINE_HEIGHT // 2))

        assert seeks == [pytest.approx(5_000.0, abs=200)]

    def test_a_drag_along_the_track_keeps_running_the_clip(self, tmp_path, panel):
        seeks: list[float] = []
        overlay = HudOverlay(
            hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
            engine=FakeEngine(), clock=lambda: 0.0, seek=seeks.append,
        )
        overlay.tick(clip_row=self._ROW)
        _x, _y, _width, height = overlay.targets.row.rect
        x0, x1 = overlay.targets.row.track
        along = height - TIMELINE_HEIGHT // 2

        overlay.press(*self._on_the_row(overlay, x0, along))
        overlay.drag_to(*self._on_the_row(overlay, (x0 + x1) // 2, along))

        assert seeks[-1] == pytest.approx(5_000.0, abs=200)

    def test_a_press_on_the_speaker_mutes_and_a_drag_across_it_does_not(self, tmp_path, panel):
        mutes: list[int] = []
        levels: list[int] = []
        overlay = HudOverlay(
            hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
            engine=FakeEngine(), clock=lambda: 0.0,
            set_volume=levels.append, toggle_mute=lambda: mutes.append(1),
        )
        overlay.tick(clip_row=self._ROW)
        _x, _y, width, height = overlay.targets.row.rect
        cx, cy = chip_xy(win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)

        overlay.press(*self._on_the_row(overlay, cx + SPEAKER_W // 2, cy + CHIP_H // 2))
        overlay.drag_to(*self._on_the_row(overlay, cx + CHIP_W - 2, cy + CHIP_H // 2))

        assert mutes == [1]
        assert levels == []

    def test_a_scripted_clip_colors_its_track(self, tmp_path, panel):
        """The host measures the track the panel drew and builds the script's
        colors across it; the panel fills the next one with them."""
        plain, scripted = FakeEngine(), FakeEngine()
        _overlay(tmp_path, panel, plain).tick(clip_row=self._ROW)
        colored = _overlay(tmp_path, panel, scripted)
        colored.tick(clip_row=self._ROW)
        colored.tick(clip_row=self._ROW, heatmap=_colors_across(colored.row))

        (_x, _y, bare), = plain.overlays.values()
        (_x, _y, filled), = scripted.overlays.values()
        assert bare.shape == filled.shape
        assert not (bare == filled).all()

    def test_a_fill_measured_across_some_other_track_is_dropped(self, tmp_path, panel):
        """A panel is as wide as what is on it, so a host measures one panel and
        fills the next, and between the two the panel can change width.  The
        wrong length raises out of the track painter rather than stretching --
        which took the window's drawing down with it and left the Main Funestra
        showing no picture at all."""
        plain, mismatched = FakeEngine(), FakeEngine()
        _overlay(tmp_path, panel, plain).tick(clip_row=self._ROW)
        overlay = _overlay(tmp_path, panel, mismatched)
        overlay.tick(clip_row=self._ROW)
        overlay.tick(clip_row=self._ROW, heatmap=[(255, 0, 0)] * 7)

        (_x, _y, bare), = plain.overlays.values()
        (_x, _y, drawn), = mismatched.overlays.values()
        assert (bare == drawn).all()

    def test_the_host_is_told_where_the_row_landed(self, tmp_path, panel):
        """Its width is what the colors must cover, and under it is where the
        loop's two frames hang."""
        overlay = _overlay(tmp_path, panel, FakeEngine())

        overlay.tick(clip_row=self._ROW)

        x, _y, _width, _height = overlay.row.rect
        x0, x1 = overlay.row.track
        left, top, _w, _h = (MARGIN, MARGIN, 0, 0)
        panel_h = overlay._engine.overlays[overlay.overlay_id][2].shape[0]
        assert overlay.row_track == (left + x + x0, left + x + x1,
                                     top + panel_h + UNDER_THE_PANEL_GAP)

    def test_a_picture_leaves_nothing_for_the_frames_to_hang_under(self, tmp_path, panel):
        overlay = _overlay(tmp_path, panel, FakeEngine())

        overlay.tick(clip_row=None)

        assert overlay.row is None
        assert overlay.row_track is None


def test_tick_composites_the_panel_at_the_hud_inset(tmp_path: Path, panel: Path):
    engine = FakeEngine()
    _overlay(tmp_path, panel, engine).tick()

    assert len(engine.overlays) == 1
    (x, y, bgra), = engine.overlays.values()
    assert (x, y) == (MARGIN, MARGIN)
    assert bgra.shape[2] == 4


def test_tick_redraws_only_when_the_published_panel_changes(tmp_path: Path, panel: Path):
    """The source rewrites the file only on a real change, but the Funestra polls it
    every frame — an unchanged read must not re-render the whole panel."""
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)

    overlay.tick()
    first = engine.overlays[overlay.overlay_id][2]
    overlay.tick()
    assert engine.overlays[overlay.overlay_id][2] is first

    panel.write_text(panel.read_text(encoding="utf-8").replace(
        '"locked": false', '"locked": true'), encoding="utf-8")
    overlay.tick()
    assert engine.overlays[overlay.overlay_id][2] is not first


def test_tick_redraws_when_the_clip_on_screen_changes(tmp_path: Path, panel: Path):
    """The HUD names the file the engine has open, and a Funestra left alone walks
    its playlist by itself — the source republishes the panel only when the map under
    it moves, so the name has to redraw off the engine's own answer or it would sit
    on a clip that had already rolled past."""
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)

    overlay.tick(video="one")
    first = engine.overlays[overlay.overlay_id][2]
    overlay.tick(video="one")
    assert engine.overlays[overlay.overlay_id][2] is first

    overlay.tick(video="two")
    assert engine.overlays[overlay.overlay_id][2] is not first


def test_the_funestras_own_rate_brings_a_speed_row_whose_buttons_post_this_sides_speed(
        tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick(playback_speed=1.0)
    rect = {b.command: r for r, b in overlay.targets.buttons}["portrait_speed_up"]

    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["portrait_speed_up"]


def test_tick_redraws_when_the_funestras_rate_changes(tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)

    overlay.tick(playback_speed=1.0)
    first = engine.overlays[overlay.overlay_id][2]
    overlay.tick(playback_speed=1.0)
    assert engine.overlays[overlay.overlay_id][2] is first

    overlay.tick(playback_speed=1.5)
    assert engine.overlays[overlay.overlay_id][2] is not first


def test_no_panel_file_means_no_overlay(tmp_path: Path):
    """A Funestra its source has published no HUD for (an integration run, or
    before the first publish) simply shows no map."""
    engine = FakeEngine()
    _overlay(tmp_path, tmp_path / "absent.json", engine).tick()

    assert engine.overlays == {}


def test_the_overlay_is_removed_when_the_panel_goes_away(tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()

    panel.unlink()
    overlay.tick()

    assert engine.overlays == {}


def test_a_panel_that_cannot_be_read_this_frame_keeps_the_map_up(
    tmp_path: Path, panel: Path, monkeypatch: pytest.MonkeyPatch
):
    """The source replaces this file while the Funestra polls it 60x/s, so a read can
    lose that race and come back as a sharing violation.

    That is not the panel going away — it is one frame that could not see it.
    Tearing the overlay down for it, and rebuilding it on the next frame, is a
    HUD that blinks.
    """
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    drawn = engine.overlays[overlay.overlay_id][2]

    real_read_text = Path.read_text

    def refuse(self, *args, **kwargs):
        if self == panel:
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


def _locked(panel: Path) -> None:
    panel.write_text(panel.read_text(encoding="utf-8").replace(
        '"locked": false', '"locked": true'), encoding="utf-8")


def test_a_panel_the_engine_has_no_memory_to_put_up_keeps_the_last_one_until_it_has(
        tmp_path: Path, panel: Path):
    engine = _EngineOutOfMemory()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    drawn = engine.overlays[overlay.overlay_id][2]

    _locked(panel)
    engine.out_of_memory = True
    with pytest.raises(MemoryError):
        overlay.tick()
    kept = engine.overlays[overlay.overlay_id][2]
    engine.out_of_memory = False
    overlay.tick()

    assert kept is drawn
    assert engine.overlays[overlay.overlay_id][2] is not drawn


def test_presses_land_on_the_panel_on_screen_while_the_next_cannot_be_put_up(
        tmp_path: Path, panel: Path):
    engine = _EngineOutOfMemory()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    targets = overlay.targets

    _locked(panel)
    engine.out_of_memory = True
    with pytest.raises(MemoryError):
        overlay.tick()

    assert overlay.targets is targets


def test_a_panel_there_is_no_memory_to_paint_keeps_the_last_one_until_there_is(
        tmp_path: Path, panel: Path, monkeypatch: pytest.MonkeyPatch):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    drawn = engine.overlays[overlay.overlay_id][2]
    paint = HudRenderer.render
    out_of_memory = [True]

    def render(self, *args, **kwargs):
        if out_of_memory[0]:
            raise MemoryError
        return paint(self, *args, **kwargs)

    monkeypatch.setattr(HudRenderer, "render", render)
    _locked(panel)
    with pytest.raises(MemoryError):
        overlay.tick()
    kept = engine.overlays[overlay.overlay_id][2]
    out_of_memory[0] = False
    overlay.tick()

    assert kept is drawn
    assert engine.overlays[overlay.overlay_id][2] is not drawn


def test_a_single_click_posts_the_switch_once_its_window_lapses(tmp_path: Path, panel: Path):
    """A click on a thumbnail could be the first half of a double-click, so the
    switch is posted by a later tick — not by the press itself."""
    now = [0.0]
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine, clock=lambda: now[0])
    overlay.tick()
    corner_rect = overlay.targets.click[0][0]

    overlay.press(corner_rect[0] + MARGIN + 2, corner_rect[1] + MARGIN + 2)
    overlay.tick()
    assert _commands(tmp_path) == []

    now[0] = 1.0
    overlay.tick()
    assert _commands(tmp_path) == ["portrait_play_video|C:/v/cur.mp4"]


def test_a_double_click_locks_instead_of_switching(tmp_path: Path, panel: Path):
    now = [0.0]
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine, clock=lambda: now[0])
    overlay.tick()
    x, y, _w, _h = overlay.targets.click[1][0]  # the seed thumbnail

    overlay.press(x + MARGIN + 2, y + MARGIN + 2)
    now[0] = 0.2
    overlay.press(x + MARGIN + 2, y + MARGIN + 2)
    now[0] = 2.0
    overlay.tick()

    assert _commands(tmp_path) == ["portrait_lock_video|C:/v/s1.mp4"]


def test_a_loop_button_click_posts_at_once(tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    rect = dict((kind, r) for r, kind in overlay.targets.loop)["seed"]

    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["portrait_seed_loop"]


def test_a_press_outside_the_panel_posts_nothing_and_is_refused(
        tmp_path: Path, panel: Path):
    """Refused rather than merely silent: what the HUD does not take is a press
    on the picture, and the run loop has its own answer for one."""
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()

    taken = [
        overlay.press(2, 2),          # inside the window, outside the HUD's inset
        overlay.press(2000, 2000),    # far off the panel
    ]

    assert taken == [False, False]
    assert _commands(tmp_path) == []


def test_a_press_on_the_panel_s_own_background_is_the_hud_s(tmp_path: Path, panel: Path):
    """The slab is one surface: a press between its controls posts nothing and
    is still the HUD's, not the picture's."""
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    _x, _y, bgra = engine.overlays[overlay.overlay_id]
    height, width = bgra.shape[:2]

    taken = overlay.press(MARGIN + width - 1, MARGIN + height - 1)

    assert taken is True
    assert _commands(tmp_path) == []


def test_no_panel_on_screen_takes_no_press(tmp_path: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, tmp_path / "absent.json", engine)
    overlay.tick()

    assert overlay.press(MARGIN + 2, MARGIN + 2) is False


def test_hovering_a_button_redraws_with_its_tooltip(tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    plain = engine.overlays[overlay.overlay_id][2]
    rect = dict((kind, r) for r, kind in overlay.targets.loop)["action"]

    overlay.motion(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    hovered = engine.overlays[overlay.overlay_id][2]
    assert bytes(hovered) != bytes(plain)  # the tooltip is in the pixels

    # Moving off the button clears it again: the redraw matches the pre-hover
    # pixels, not merely "some new object" (the old identity check held even
    # with the whole clear branch deleted).
    overlay.motion(MARGIN + 2, MARGIN + 2)
    cleared = engine.overlays[overlay.overlay_id][2]
    assert bytes(cleared) == bytes(plain)


def test_pressing_the_lit_filter_button_lifts_the_filter(tmp_path: Path, panel: Path):
    """The published filter is what makes the button a toggle, so a filter set any
    other way — spoken, or from the other side of the map — is lifted by pressing the
    button it lit."""
    engine = FakeEngine()
    panel.write_text(panel.read_text(encoding="utf-8").replace(
        '"funestra": "portrait"', '"funestra": "portrait", "filter_query": "alpha"'), encoding="utf-8")
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()

    rect = dict((name, r) for r, name in overlay.targets.filter)["alpha"]
    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["portrait_no_filter"]


def test_pressing_an_unlit_filter_button_filters_to_its_act(tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()

    rect = dict((name, r) for r, name in overlay.targets.filter)["gamma"]
    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)

    assert _commands(tmp_path) == ["filter_portrait_gamma"]


def test_the_published_loop_state_wins_over_the_optimistic_one(tmp_path: Path, panel: Path):
    """A click lights the button before the source answers, but the published panel
    is authoritative — a loop that ended must not stay lit."""
    engine = FakeEngine()
    overlay = _overlay(tmp_path, panel, engine)
    overlay.tick()
    rect = dict((kind, r) for r, kind in overlay.targets.loop)["seed"]
    overlay.press(rect[0] + MARGIN + 2, rect[1] + MARGIN + 2)
    assert overlay.active_loop == "seed"

    panel.write_text(panel.read_text(encoding="utf-8").replace(
        '"funestra": "portrait"', '"funestra": "portrait", "active_loop": ""'), encoding="utf-8")
    overlay.tick()

    assert overlay.active_loop == ""




def _give_it_the_osr2(panel: Path) -> None:
    published = json.loads(panel.read_text(encoding="utf-8"))
    published.update(osr2="robot_hand", osr2_control="driving")
    panel.write_text(json.dumps(published), encoding="utf-8")


def _publish_motion(path: Path, offset: float) -> None:
    publish_drive(path, DriveHud(
        speed=50, amplitude=80, center=50,
        waveform=tuple(0.5 + 0.4 * math.sin(i / 6 + offset) for i in range(80))))


def _overlay_with_the_motion(tmp_path: Path, panel: Path, engine) -> HudOverlay:
    return HudOverlay(hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
                      engine=engine, clock=lambda: 0.0, drive_file=tmp_path / "drive.txt")


class TestAPanelWithTheOsr2:
    def test_draws_the_motion_genau_publishes_under_the_osr2_line(self, tmp_path: Path, panel: Path):
        _give_it_the_osr2(panel)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_with_the_motion(tmp_path, panel, FakeEngine())

        overlay.tick()

        assert overlay.targets.tracks

    def test_redraws_as_the_motion_moves(self, tmp_path: Path, panel: Path):
        _give_it_the_osr2(panel)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        engine = FakeEngine()
        overlay = _overlay_with_the_motion(tmp_path, panel, engine)
        overlay.tick()
        first = engine.overlays[overlay.overlay_id][2].copy()

        _publish_motion(tmp_path / "drive.txt", 3.0)
        overlay.tick()

        assert not (engine.overlays[overlay.overlay_id][2] == first).all()

    def test_a_panel_without_it_draws_no_motion(self, tmp_path: Path, panel: Path):
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_with_the_motion(tmp_path, panel, FakeEngine())

        overlay.tick()

        assert overlay.targets.tracks == []

    def test_a_band_of_the_readout_keeps_a_drag_until_it_is_let_go(self, tmp_path: Path, panel: Path):
        _give_it_the_osr2(panel)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        overlay = _overlay_with_the_motion(tmp_path, panel, FakeEngine())
        overlay.tick()
        x, y, w, h = next(band.rect for band in overlay.targets.tracks if band.axis == "speed")

        overlay.press(MARGIN + x + 1, MARGIN + y + h // 2)
        dragged = overlay.drag_to(MARGIN + x + w - 2, MARGIN + y + h // 2)
        overlay.release()

        assert _commands(tmp_path) == ["robot_hand_speed_1", "robot_hand_speed_99"]
        assert dragged == "robot_hand_speed_99"
        assert overlay.holding is False


class _Gate:
    def __init__(self, composed: DriveHud) -> None:
        self.asked: list[tuple[DriveHud | None, bool]] = []
        self._composed = composed

    def readout(self, published, *, device_drives_itself: bool = False) -> DriveHud:
        self.asked.append((published, device_drives_itself))
        return self._composed


class TestAPanelWithTheOsr2ItsOwnFunestraScripts:
    def test_draws_genaus_motion_with_the_funestras_own_script_folded_in(self, tmp_path, panel):
        _give_it_the_osr2(panel)
        _publish_motion(tmp_path / "drive.txt", 0.0)
        composed = DriveHud(speed=50, amplitude=80, center=50, driven="funscript",
                            waveform=tuple(0.2 for _ in range(80)))
        gate = _Gate(composed)
        overlay = HudOverlay(hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
                             engine=FakeEngine(), clock=lambda: 0.0,
                             drive_file=tmp_path / "drive.txt", drive_gate=gate)

        overlay.tick()

        ((published, drives_itself),) = gate.asked
        assert published.amplitude == 80 and drives_itself is False
        assert overlay.targets.tracks


def _publish(panel_path: Path, **panel_changes) -> None:
    published = json.loads(panel_path.read_text(encoding="utf-8"))
    published.update(panel_changes)
    panel_path.write_text(json.dumps(published), encoding="utf-8")


def _panel_at(tmp_path: Path, panel_path: Path, engine, **panel_changes):
    _publish(panel_path, **panel_changes)
    overlay = _overlay(tmp_path, panel_path, engine)
    overlay.tick(window=(1200, 800))
    return overlay


@pytest.mark.parametrize("corner", list(HudCorner))
def test_the_minus_sits_where_the_plus_of_the_minimized_panel_sits(
        tmp_path: Path, panel: Path, corner: HudCorner):
    """So a click that minimizes the panel, made again without moving the
    mouse, opens it again."""
    engine = FakeEngine()
    overlay = _panel_at(tmp_path, panel, engine, hud_corner=corner.value)
    (left, top, _bgra), = engine.overlays.values()
    (x, y, w, h), = [rect for rect, b in overlay.targets.buttons
                     if b.command == "portrait_hud_minimize"]

    _publish(panel, hud_minimized=True)
    overlay.tick(window=(1200, 800))

    (plus_left, plus_top, _bgra), = engine.overlays.values()
    ((px, py, pw, ph), _plus), = overlay.targets.buttons
    assert (plus_left + px, plus_top + py, pw, ph) == (left + x, top + y, w, h)


def test_the_panel_is_composited_in_the_corner_the_session_moved_it_to(
        tmp_path: Path, panel: Path):
    """Its own margin from the edges and nothing else: the track that used to
    run along the lower edge is a block of this panel now, so there is nothing
    down there to clear."""
    engine = FakeEngine()

    _panel_at(tmp_path, panel, engine, hud_corner="lower_right")

    (x, y, bgra), = engine.overlays.values()
    height, width = bgra.shape[:2]
    assert x == 1200 - MARGIN - width
    assert y == 800 - MARGIN - height


def test_a_press_in_a_lower_corner_reaches_the_button_drawn_there(
        tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _panel_at(tmp_path, panel, engine, hud_corner="lower_right",
                        rows=[[{"command": "portrait_next", "glyph": "N",
                                "tooltip": "Next", "width": 18}]])
    (left, top, _bgra), = engine.overlays.values()
    (bx, by, bw, bh), button = next(
        (rect, b) for rect, b in overlay.targets.buttons if b.command == "portrait_next")

    assert overlay.press(left + bx + bw // 2, top + by + bh // 2) is True
    assert _commands(tmp_path) == ["portrait_next"]


def test_the_plus_names_itself_where_the_panel_floats_over_a_picture(
        tmp_path: Path, panel: Path):
    """The panel takes the tooltip's room only while the pointer is on the plus,
    so a press beside a collapsed HUD still reaches the video under it."""
    engine = FakeEngine()
    overlay = _panel_at(tmp_path, panel, engine, hud_minimized=True,
                        hud_corner="upper_left")
    (left, top, resting), = [(x, y, bgra) for x, y, bgra in engine.overlays.values()]

    overlay.motion(left + BUTTON_SIZE_HUD // 2, top + BUTTON_SIZE_HUD // 2)
    (x, y, hovered), = [(x, y, bgra) for x, y, bgra in engine.overlays.values()]

    assert resting.shape[:2] == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)
    assert hovered.shape[1] > BUTTON_SIZE_HUD
    assert (x, y) == (left, top)


def test_a_panel_on_its_own_screen_holds_the_tooltips_room_from_the_start(
        tmp_path: Path, panel: Path):
    """In the headset the panel IS a screen, sized from its own bitmap and
    centered on the side it hangs against, so a panel that grew under the
    pointer would carry the plus out from under it and the tooltip would
    flicker as the pointer lost and found it.  The room is there all along."""
    engine = FakeEngine()
    _publish(panel, hud_minimized=True)
    overlay = HudOverlay(hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
                         engine=engine, clock=lambda: 0.0, over_the_video=False)

    overlay.tick()

    (_x, _y, bgra), = engine.overlays.values()
    assert bgra.shape[1] > BUTTON_SIZE_HUD


class TestAPanelWhoseMinusHangsOutsideIt:
    """In the headset the minus hangs on its own between the picture and the
    panel, where the plus hangs once the panel is minimized, so the panel
    carries neither."""

    @staticmethod
    def _overlay(tmp_path: Path, panel: Path, engine) -> HudOverlay:
        return HudOverlay(hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
                          engine=engine, clock=lambda: 0.0, over_the_video=False,
                          minus_on_the_panel=False)

    def test_the_panel_draws_no_minus(self, tmp_path: Path, panel: Path):
        engine = FakeEngine()
        overlay = self._overlay(tmp_path, panel, engine)

        overlay.tick()

        assert engine.overlays
        assert not [b for _rect, b in overlay.targets.buttons
                    if b.command == "portrait_hud_minimize"]

    def test_a_minimized_panel_draws_nothing(self, tmp_path: Path, panel: Path):
        engine = FakeEngine()
        _publish(panel, hud_minimized=True)
        overlay = self._overlay(tmp_path, panel, engine)

        overlay.tick()

        assert engine.overlays == {}
        assert overlay.targets.buttons == []


def test_a_panel_collapsed_by_a_press_on_its_minus_draws_the_plus_alone(
        tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _panel_at(tmp_path, panel, engine, hud_corner="upper_left")
    (left, top, _bgra), = engine.overlays.values()
    (x, y, w, h), _minus = next((rect, b) for rect, b in overlay.targets.buttons
                                if b.command == "portrait_hud_minimize")
    overlay.motion(left + x + w // 2, top + y + h // 2)
    overlay.press(left + x + w // 2, top + y + h // 2)

    _publish(panel, hud_minimized=True)
    overlay.tick(window=(1200, 800))

    (_x, _y, bgra), = engine.overlays.values()
    assert bgra.shape[:2] == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)


def test_its_place_is_the_corner_the_room_put_it_in_and_whether_it_is_minimized(
        tmp_path: Path, panel: Path):
    overlay = _panel_at(tmp_path, panel, FakeEngine(), hud_minimized=True,
                        hud_corner="upper_right")

    assert overlay.hud_place == HudPlace("portrait", HudCorner.UPPER_RIGHT, MARGIN,
                                         minimized=True, inset=MINUS_INSET)


def test_a_panel_with_nothing_published_has_no_place(tmp_path: Path):
    overlay = _overlay(tmp_path, tmp_path / "unpublished.json", FakeEngine())

    overlay.tick(window=(1200, 800))

    assert overlay.hud_place is None


def test_a_minimized_panel_is_the_plus_button_in_that_corner(tmp_path: Path, panel: Path):
    engine = FakeEngine()
    overlay = _panel_at(tmp_path, panel, engine, hud_minimized=True,
                        hud_corner="upper_right")
    (x, y, bgra), = engine.overlays.values()
    height, width = bgra.shape[:2]

    assert (width, height) == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)
    across, down = MINUS_INSET
    assert (x, y) == (1200 - MARGIN - across - width, MARGIN + down)
    assert [b.command for _rect, b in overlay.targets.buttons] == ["portrait_hud_restore"]


class TestANameFlashingWhileMinimized:
    def test_it_is_drawn_beside_the_plus(self, tmp_path: Path, panel: Path):
        engine = FakeEngine()
        _publish(panel, hud_minimized=True)
        overlay = _overlay(tmp_path, panel, engine)

        overlay.tick(window=(1200, 800), flash="scene one")

        (_x, _y, bgra), = engine.overlays.values()
        assert np.array_equal(bgra, collapsed_panel("portrait", flash="scene one")[0])

    def test_the_plus_is_alone_again_once_it_is_over(self, tmp_path: Path, panel: Path):
        engine = FakeEngine()
        _publish(panel, hud_minimized=True)
        overlay = _overlay(tmp_path, panel, engine)
        overlay.tick(window=(1200, 800), flash="scene one")

        overlay.tick(window=(1200, 800))

        (_x, _y, bgra), = engine.overlays.values()
        assert bgra.shape[:2] == (BUTTON_SIZE_HUD, BUTTON_SIZE_HUD)

    @pytest.mark.parametrize("corner", list(HudCorner))
    def test_the_plus_stays_where_it_was(self, tmp_path: Path, panel: Path, corner: HudCorner):
        engine = FakeEngine()
        overlay = _panel_at(tmp_path, panel, engine, hud_minimized=True, hud_corner=corner.value)
        alone = self._plus_on_the_screen(overlay, engine)

        overlay.tick(window=(1200, 800), flash="scene one")

        assert self._plus_on_the_screen(overlay, engine) == alone

    @staticmethod
    def _plus_on_the_screen(overlay: HudOverlay, engine) -> tuple[int, int]:
        (left, top, _bgra), = engine.overlays.values()
        ((x, y, _w, _h), _plus), = overlay.targets.buttons
        return left + x, top + y


def test_a_panel_hanging_on_its_own_screen_keeps_its_default_justification(
        tmp_path: Path, panel: Path):
    """In the headset the panel is a screen of its own rather than a slab over a
    corner of the picture, so the corner the session moved it to says which side
    of the Funestra it hangs against and nothing about how it is laid out."""
    engine = FakeEngine()
    _publish(panel, hud_corner="lower_right", hud_edge="right",
             rows=[[{"command": "portrait_next", "glyph": "N",
                     "tooltip": "Next", "width": 18}]])
    overlay = HudOverlay(
        hud_file=panel, command_file=tmp_path / "dashboard_cmd.txt",
        engine=engine, clock=lambda: 0.0, over_the_video=False)

    overlay.tick(window=(1200, 800))

    assert overlay.edge is HudEdge.RIGHT
    assert min(rect[0] for rect, _b in overlay.targets.buttons) == PAD
    (x, y, _bgra), = engine.overlays.values()
    assert (x, y) == (MARGIN, MARGIN)


class _Foot:
    """A block the source paints at the panel's foot, as the source sees it."""

    def __init__(self, size=(120, 40)) -> None:
        self._size = size

    def size(self):
        return self._size

    def paint(self, image, x, y, width, pointer):
        return []


def _a_windows_own_panel(engine, *, foot=None, posts=None):
    model = HudModel(funestra="portrait", title="Unlocked",
                     rows=((Button("portrait_next", "N", "Next"),),), foot=foot)
    posted = [] if posts is None else posts
    overlay = HudOverlay(panel=lambda: model, post=posted.append, engine=engine,
                         clock=lambda: 0.0)
    overlay.tick()
    return overlay, posted


class TestAWindowsOwnPanel:
    def test_a_press_on_a_button_goes_back_to_the_program_that_handed_the_panel_over(self):
        engine = FakeEngine()
        overlay, posted = _a_windows_own_panel(engine)
        (x, y, w, h), _button = next((rect, b) for rect, b in overlay.targets.buttons
                                     if b.command == "portrait_next")

        overlay.press(MARGIN + x + w // 2, MARGIN + y + h // 2)

        assert posted == ["portrait_next"]

    def test_it_keeps_the_readout_the_program_drew_into_it(self):
        """A session publishes no readout and the room's motion file fills one
        in; the window's own program composes the readout itself, and nothing
        here may wipe it."""
        engine = FakeEngine()
        readout = DriveHud(speed=50, amplitude=80, center=50,
                           waveform=tuple(0.5 for _ in range(80)))
        model = HudModel(funestra="portrait", title="Unlocked", osr2="robot_hand",
                         osr2_control="driving", drive=readout)
        overlay = HudOverlay(panel=lambda: model, post=lambda command: None, engine=engine,
                             clock=lambda: 0.0)

        overlay.tick()

        assert overlay.targets.tracks


class TestTheBlockAtTheFoot:
    """The source painted the block and knows what is drawn where, so the
    pointer goes back to it: a press, a drag, the button coming up and the
    wheel, each with where it landed in the block's own pixels."""

    def _foot_at(self, overlay):
        x, y, _width, _height = overlay.targets.foot
        return MARGIN + x, MARGIN + y

    def test_a_press_on_the_block_is_the_sources_with_where_it_landed(self):
        overlay, posted = _a_windows_own_panel(FakeEngine(), foot=_Foot())
        left, top = self._foot_at(overlay)

        taken = overlay.press(left + 30, top + 7)

        assert taken is True
        assert posted == ["foot_press|30|7"]

    def test_a_held_press_drags_and_the_button_coming_up_lets_go(self):
        overlay, posted = _a_windows_own_panel(FakeEngine(), foot=_Foot())
        left, top = self._foot_at(overlay)
        overlay.press(left + 30, top + 7)

        assert overlay.holding is True
        overlay.drag_to(left + 30, top + 25)
        overlay.release()

        assert posted == ["foot_press|30|7", "foot_drag|30|25", "foot_release|30|25"]
        assert overlay.holding is False

    def test_the_wheel_over_the_block_is_the_sources_too(self):
        overlay, posted = _a_windows_own_panel(FakeEngine(), foot=_Foot())
        left, top = self._foot_at(overlay)

        taken = overlay.wheel(left + 10, top + 10, -2)

        assert taken is True
        assert posted == ["foot_wheel|-2|10|10"]

    def test_the_wheel_elsewhere_on_the_panel_turns_nothing_and_is_still_the_panels(self):
        overlay, posted = _a_windows_own_panel(FakeEngine(), foot=_Foot())

        assert overlay.wheel(MARGIN + 2, MARGIN + 2, 1) is True
        assert overlay.wheel(2000, 2000, 1) is False
        assert posted == []

    def test_a_panel_without_a_block_has_nothing_at_its_foot_to_press(self):
        overlay, posted = _a_windows_own_panel(FakeEngine())

        assert overlay.targets.foot is None
