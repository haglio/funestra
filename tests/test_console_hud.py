from __future__ import annotations

from pathlib import Path

from host_controls_fakes import BAR, AHost, middle_of
from shared_ui.palette import BG_BUTTON

from funestra.hud_kinds import HudFacts, HudKind
from funestra.hud_overlay import (
    HUD_OVERLAY_ID,
    ConsoleHud,
    DrawnOn,
    DriveFeed,
    HudOverlay,
)
from funestra.main_hud import ModeHud
from funestra.modes import LengthMode, MainMode, Osr2State
from funestra.osr2_visualizer import DriveHud, DrivePublisher, drive_text
from funestra.satellite_hud import HudModel, hud_text
from funestra.testing import FakeEngine

WINDOW = (1000, 600)


class SpyGate:
    def __init__(self) -> None:
        self.told_the_video_shows: list[bool] = []

    def visualizer(self, published, *, device_drives_itself: bool = False,
                   video_shows: bool = True):
        self.told_the_video_shows.append(video_shows)
        return published if published is not None else DriveHud()


def _console(path: Path, **facts) -> Path:
    path.write_text(hud_text(HudModel(
        funestra="main", kind=HudKind.MAIN, osr2=Osr2State.ROBOT_HAND,
        facts=HudFacts(**{"locked": True, "latest": False, **facts}))), encoding="utf-8")
    return path


def _overlay(tmp_path: Path, *, top_block=ModeHud, host_controls=None, gate=None,
             visualizer: bool = False) -> tuple[HudOverlay, FakeEngine]:
    engine = FakeEngine()
    (tmp_path / "drive.txt").write_text(drive_text(DriveHud(position=4_000)), encoding="utf-8")
    overlay = HudOverlay(
        source=ConsoleHud(tmp_path / "console.json", tmp_path / "dashboard_cmd.txt", top_block),
        drawn_on=DrawnOn(engine),
        drive=DriveFeed(tmp_path / "drive.txt", gate or SpyGate(),
                        DrivePublisher(tmp_path / "visualizer.txt") if visualizer else None),
        host_controls=host_controls,
        clock=lambda: 0.0,
    )
    return overlay, engine


def _commands(overlay: HudOverlay) -> list[str]:
    return [button.command for _rect, button in overlay.targets.buttons]


def _asked(tmp_path: Path) -> list[str]:
    path = tmp_path / "dashboard_cmd.txt"
    return path.read_text(encoding="utf-8").split() if path.exists() else []


class TestReadingTheConsole:
    def test_what_fun_time_said_is_what_the_hud_shows(self, tmp_path):
        overlay, _engine = _overlay(tmp_path)
        _console(tmp_path / "console.json", main_mode=MainMode.GENAU)

        overlay.tick(viewport=WINDOW)

        assert "genau_next_flick" in _commands(overlay)

    def test_a_torn_read_keeps_the_hud_that_was_there(self, tmp_path):
        overlay, _engine = _overlay(tmp_path)
        _console(tmp_path / "console.json", main_mode=MainMode.GENAU)
        overlay.tick(viewport=WINDOW)

        (tmp_path / "console.json").write_text("{ half a fi", encoding="utf-8")
        overlay.tick(viewport=WINDOW)

        assert "genau_next_flick" in _commands(overlay)

    def test_before_fun_time_has_said_anything_the_hud_is_drawn_at_rest(self, tmp_path):
        overlay, engine = _overlay(tmp_path)

        overlay.tick(viewport=WINDOW)

        assert HUD_OVERLAY_ID in engine.overlays
        assert "main_kino_activate" in _commands(overlay)


class TestWhatTheTitleSays:
    def test_the_top_block_is_asked_of_whoever_runs_on_the_funestra_each_frame(self, tmp_path):
        said = {"video": "video one"}
        overlay, engine = _overlay(
            tmp_path, top_block=lambda: ModeHud(video=said["video"], length_mode=LengthMode.MIXED))
        _console(tmp_path / "console.json")

        overlay.tick(viewport=WINDOW)
        first = engine.overlays[HUD_OVERLAY_ID][2]
        said["video"] = "video two"
        overlay.tick(viewport=WINDOW)

        assert engine.overlays[HUD_OVERLAY_ID][2] is not first

    def test_an_unchanged_hud_is_not_repainted(self, tmp_path):
        overlay, engine = _overlay(tmp_path)
        _console(tmp_path / "console.json")

        overlay.tick(viewport=WINDOW)
        first = engine.overlays[HUD_OVERLAY_ID][2]
        overlay.tick(viewport=WINDOW)

        assert engine.overlays[HUD_OVERLAY_ID][2] is first


def test_a_press_on_a_button_asks_fun_time_for_its_verb(tmp_path):
    overlay, engine = _overlay(tmp_path)
    _console(tmp_path / "console.json")
    overlay.tick(viewport=WINDOW)
    left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
    (x, y, w, h), _button = next(placed for placed in overlay.targets.buttons
                                 if placed[1].command == "main_kino_activate")

    overlay.press(left + x + w // 2, top + y + h // 2)

    assert _asked(tmp_path) == ["main_kino_activate"]


def test_the_gate_is_told_when_genau_has_the_screen(tmp_path):
    gate = SpyGate()
    overlay, _engine = _overlay(tmp_path, gate=gate, visualizer=True)
    _console(tmp_path / "console.json", main_mode=MainMode.GENAU)

    overlay.tick(viewport=WINDOW)

    assert gate.told_the_video_shows == [False]


class TestTheHostsControls:
    @staticmethod
    def _shown(tmp_path, host) -> tuple[HudOverlay, FakeEngine]:
        overlay, engine = _overlay(tmp_path, host_controls=host)
        _console(tmp_path / "console.json", main_mode=MainMode.GENAU)
        overlay.tick(viewport=WINDOW)
        return overlay, engine

    def test_are_drawn_inside_the_hud(self, tmp_path):
        overlay, engine = self._shown(tmp_path, AHost())
        _left, _top, bgra = engine.overlays[HUD_OVERLAY_ID]
        x, y, _width, height = overlay.targets.host_controls.field

        assert tuple(bgra[y + height // 2, x + 3, :3]) == BG_BUTTON[::-1]

    def test_a_row_picked_off_the_list_is_the_hosts_and_asks_fun_time_nothing(self, tmp_path):
        host = AHost()
        overlay, engine = self._shown(tmp_path, host)
        left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        layout = overlay.targets.host_controls
        field_x, field_y = middle_of(layout.field)

        opened = overlay.press(left + field_x, top + field_y)
        overlay.tick(viewport=WINDOW)
        row_x, row_y = middle_of(layout.rows[1])
        picked = overlay.press(left + row_x, top + row_y)

        assert opened is picked is True
        assert host.picked == [1]
        assert _asked(tmp_path) == []

    def test_a_drag_along_the_bar_is_the_hosts_and_asks_fun_time_nothing(self, tmp_path):
        host = AHost()
        overlay, engine = self._shown(tmp_path, host)
        left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        x, y, width, height = overlay.targets.host_controls.bar
        overlay.press(left + x + 2, top + y + height // 2)

        held = overlay.holding
        overlay.drag_to(left + x + width + 40, top + y + height // 2)

        assert held is True
        assert host.set_to[-1] == BAR.high
        assert _asked(tmp_path) == []

    def test_letting_go_lets_it_go(self, tmp_path):
        overlay, engine = self._shown(tmp_path, AHost())
        left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        x, y, _width, height = overlay.targets.host_controls.bar
        overlay.press(left + x + 2, top + y + height // 2)

        overlay.release()

        assert overlay.holding is False
