"""A Funestra, ticked: it plays what it was handed, answers its files, publishes its status and paints its own controls."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from console_rows import console_rows
from funestra_fakes import FakeEngine
from host_controls_fakes import AHost, middle_of

from funestra.console import ConsoleModel, ModeHud, console_text
from funestra.flick_picture import BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID, Picture
from funestra.funestra import Channels, Funestra, User, _Nobody
from funestra.hud_button import Button
from funestra.hud_corners import CORNER_PLUS_OVERLAY_ID
from funestra.hud_minimize import BUTTON
from funestra.hud_overlay import HUD_OVERLAY_ID
from funestra.hud_placement import HudEdge
from funestra.hud_row import PARTS_Y
from funestra.loop_dial import DIAL_SIZE
from funestra.modes import LengthMode, MainMode, Osr2State
from funestra.playhead import FIGURE_SPACE
from funestra.playlist import read_playlist
from funestra.pointer import OMNIPAUSE_TOGGLE
from funestra.satellite_hud import MARGIN, HudModel
from funestra.session_quit import SESSION_QUIT
from funestra.timeline import TIMELINE_HEIGHT
from funestra.volume import CHIP_H, CHIP_W, chip_xy

WINDOW = (640, 480)


def _on_the_row(funestra, engine, part: str = "track", *, along: int | None = None):
    """A window point on one of the row's controls, which the panel draws at
    its foot.  The panel is wherever the room put it, so this is read back off
    the overlay it was composited at."""
    left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
    row = funestra._panel.row
    x, y, width, height = row.rect
    if part == "track":
        x0, x1 = row.track
        return left + x + (along if along is not None else (x0 + x1) // 2), top + y + height - 4
    if part == "dial":
        return left + x + row.dial + DIAL_SIZE - 3, top + y + PARTS_Y + DIAL_SIZE // 2  # quarter past
    cx, cy = chip_xy(win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)
    across = 4 if part == "speaker" else CHIP_W - 6
    return left + x + cx + across, top + y + cy + CHIP_H // 2


def _clips(tmp_path: Path, *names: str) -> list[Path]:
    clips = []
    for name in names:
        clip = tmp_path / f"{name}.mp4"
        clip.write_bytes(b"")
        clips.append(clip)
    return clips


def _channels(tmp_path: Path, lines: list[str], *, commands: str = "QUIT\n",
              hud: bool = False, in_a_session: bool = False) -> Channels:
    (tmp_path / "playlist.tsv").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    (tmp_path / "cmd.txt").write_text(commands, encoding="utf-8")
    return Channels(
        playlist=tmp_path / "playlist.tsv",
        command=tmp_path / "cmd.txt",
        paused=tmp_path / "paused.txt",
        status=tmp_path / "status.txt",
        hud=tmp_path / "portrait_hud.json" if hud else None,
        dashboard_cmd=tmp_path / "dashboard_cmd.txt" if hud or in_a_session else None,
    )


def _funestra(tmp_path: Path, lines: list[str], *, audible: bool = True, tiles: bool = False,
              **channel_choices) -> tuple[Funestra, FakeEngine]:
    channels = _channels(tmp_path, lines, **channel_choices)
    engine = FakeEngine()
    return Funestra(engine, channels=channels, playlist=read_playlist(channels.playlist),
                    audible=audible, tiles=tiles), engine


def _status(tmp_path: Path) -> str:
    return (tmp_path / "status.txt").read_text(encoding="utf-8")


def _asked(tmp_path: Path) -> list[str]:
    path = tmp_path / "dashboard_cmd.txt"
    return path.read_text(encoding="utf-8").split() if path.exists() else []


def test_one_pass_plays_publishes_and_paints_then_quit_stops_it(tmp_path):
    clips = _clips(tmp_path, "v0", "v1")
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in clips])

    funestra.tick(window=WINDOW)

    assert engine.opened[0] == clips[0]
    assert f"video={clips[0]}" in _status(tmp_path)
    assert funestra.stopped is True
    funestra.close()
    assert engine.closed is True


def test_a_window_wearing_no_panel_draws_nothing_over_its_picture(tmp_path):
    """The track, the time and the volume are a block of the panel, so a window
    with no panel to wear has nowhere to put them -- and the picture comes
    through untouched instead of carrying a row along its lower edge."""
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    assert engine.overlays == {}


def test_the_row_says_where_the_clip_is_and_how_long_it_runs(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    row = funestra.clip_row()
    assert (row.position_ms, row.duration_ms) == (0.0, engine.duration_ms)
    assert row.playhead is not None
    assert row.volume is funestra._volume.hud


def test_a_scripted_clips_track_is_filled_across_the_width_the_panel_drew_it_at(tmp_path):
    """The colors fill the track, and a panel is as wide as what is on it, so
    they are measured across the row the panel drew rather than the window."""
    clip = _clips(tmp_path, "v0")[0]
    script = tmp_path / "v0.funscript"
    script.write_text('{"actions": [{"at": 0, "pos": 0}, {"at": 900, "pos": 100}, '
                      '{"at": 2400, "pos": 10}]}', encoding="utf-8")
    funestra, _engine = _funestra(tmp_path, [f"{clip}\t{script}"], hud=True)
    _publish_panel(tmp_path)

    funestra.tick(window=WINDOW)
    funestra.tick(window=WINDOW)

    x0, x1 = funestra._panel.row.track
    assert len(funestra._strip.colors) == x1 - x0


def test_a_picture_on_screen_puts_no_row_on_the_panel(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                 hud=True)
    _publish_panel(tmp_path)
    engine.showing_picture = True

    funestra.tick(window=WINDOW)

    assert funestra.clip_row() is None
    assert funestra._panel.row is None


def test_commands_drain_and_act_before_the_frame_is_published(tmp_path):
    clips = _clips(tmp_path, "v0", "v1")
    funestra, _engine = _funestra(tmp_path, [str(clip) for clip in clips], commands="NEXT\nQUIT\n")

    funestra.tick(window=WINDOW)

    assert f"video={clips[1]}" in _status(tmp_path)


def test_a_list_written_under_the_window_is_taken_with_no_verb_sent(tmp_path):
    """The host writes the list and then queues one reload, and that queue drops the
    line when the file is held for longer than 25ms -- after which the window went
    on playing what it had, with the new list on disk beside it, for good."""
    clips = _clips(tmp_path, "v0", "v1", "v2")
    funestra, _engine = _funestra(tmp_path, [str(clips[0])], commands="")
    (tmp_path / "playlist.tsv").write_text(f"{clips[2]}\n", encoding="utf-8")

    funestra.tick(window=WINDOW)

    assert f"video={clips[2]}" in _status(tmp_path)


def test_reload_playlist_reads_the_list_it_was_handed_again(tmp_path):
    clips = _clips(tmp_path, "v0", "v1", "v2")
    funestra, _engine = _funestra(tmp_path, [str(clips[0])], commands="")
    (tmp_path / "playlist.tsv").write_text(f"{clips[0]}\n{clips[2]}\n", encoding="utf-8")
    (tmp_path / "cmd.txt").write_text("RELOAD_PLAYLIST\nNEXT\n", encoding="utf-8")

    funestra.tick(window=WINDOW)

    assert f"video={clips[2]}" in _status(tmp_path)


def test_the_paused_flag_reaches_the_engine_each_pass(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])
    (tmp_path / "paused.txt").write_text("1", encoding="utf-8")

    funestra.tick(window=WINDOW)

    assert engine.paused is True


def test_a_paused_flag_already_up_opens_the_engine_paused(tmp_path):
    clips = _clips(tmp_path, "v0")
    channels = _channels(tmp_path, [str(clips[0])])
    channels.paused.write_text("1", encoding="utf-8")

    funestra = Funestra(FakeEngine(), channels=channels, playlist=read_playlist(channels.playlist))

    assert funestra.playback.is_paused is True


class TestTheWindowsClose:
    def test_in_a_session_it_asks_the_session_and_keeps_playing(self, tmp_path):
        funestra, _engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                      commands="", in_a_session=True)

        funestra.close_requested()

        assert funestra.stopped is False
        assert _asked(tmp_path) == [SESSION_QUIT]

    def test_with_no_session_to_ask_it_ends_this_funestra(self, tmp_path):
        funestra, _engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                      commands="")

        funestra.close_requested()

        assert funestra.stopped is True


def _wearing_a_panel(tmp_path, *, audible: bool = True):
    funestra, engine = _funestra(
        tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
        hud=True, audible=audible)
    _publish_panel(tmp_path)
    funestra.tick(window=WINDOW)
    return funestra, engine


class TestAPress:
    """On the row the panel draws, which is where the track, the time and the
    volume are now."""

    def test_on_the_track_seeks_the_clip(self, tmp_path):
        funestra, engine = _wearing_a_panel(tmp_path)
        x0, x1 = funestra._panel.row.track

        funestra.press(*_on_the_row(funestra, engine), window=WINDOW)

        assert len(engine.seeks) == 1
        assert abs(engine.seeks[0] - engine.duration_ms / 2) <= engine.duration_ms / (x1 - x0)

    def test_on_the_speaker_unmutes_this_engine(self, tmp_path):
        funestra, engine = _wearing_a_panel(tmp_path)

        funestra.press(*_on_the_row(funestra, engine, "speaker"), window=WINDOW)

        assert engine.muted is False
        assert engine.seeks == []

    def test_on_the_speaker_of_a_silent_build_sets_nothing(self, tmp_path):
        funestra, engine = _wearing_a_panel(tmp_path, audible=False)

        funestra.press(*_on_the_row(funestra, engine, "speaker"), window=WINDOW)

        assert engine.muted is True

    def test_held_along_the_slider_keeps_setting_the_level(self, tmp_path):
        funestra, engine = _wearing_a_panel(tmp_path)
        at = _on_the_row(funestra, engine, "slider")

        funestra.press(*at, window=WINDOW)
        funestra.motion(*at, held=True, window=WINDOW)

        assert engine.volume == 100

    def test_anywhere_off_the_panel_asks_the_session_to_pause_everything(self, tmp_path):
        funestra, engine = _wearing_a_panel(tmp_path)
        left, top, panel = engine.overlays[HUD_OVERLAY_ID]

        funestra.press(left + panel.shape[1] // 2, top + panel.shape[0] + 20, window=WINDOW)

        assert _asked(tmp_path) == ["omnipause_toggle"]


class TestACornerTheHudIsNotIn:
    def test_a_press_there_asks_the_room_to_open_the_hud_there(self, tmp_path):
        funestra, _engine = _wearing_a_panel(tmp_path)

        funestra.press(WINDOW[0] - 2, WINDOW[1] - 2, window=WINDOW)

        assert _asked(tmp_path) == ["portrait_hud_restore_at|lower_right"]

    def test_a_press_beside_the_hud_in_its_own_corner_still_pauses_the_room(self, tmp_path):
        funestra, _engine = _wearing_a_panel(tmp_path)

        funestra.press(2, 2, window=WINDOW)

        assert _asked(tmp_path) == ["omnipause_toggle"]

    def test_on_the_main_funestra_the_press_opens_the_console_there(self, tmp_path):
        funestra, _engine, _kino = _main(tmp_path)
        funestra.tick(window=WINDOW)

        funestra.press(2, WINDOW[1] - 2, window=WINDOW)

        assert _asked(tmp_path) == ["main_hud_restore_at|lower_left"]

    def test_the_pointer_there_puts_a_plus_where_the_minimized_hud_would_sit(self, tmp_path):
        funestra, engine = _wearing_a_panel(tmp_path)
        funestra.motion(WINDOW[0] - 2, WINDOW[1] - 2, held=False, window=WINDOW)
        funestra.tick(window=WINDOW)
        left, top, plus = engine.overlays[CORNER_PLUS_OVERLAY_ID]
        shown_at = (left + plus.shape[1] - BUTTON, top + plus.shape[0] - BUTTON)

        _publish_panel(tmp_path, hud_corner="lower_right", hud_minimized=True)
        funestra.leave()
        funestra.tick(window=WINDOW)

        hud_left, hud_top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        ((x, y, _w, _h), _restore), = funestra._panel.targets.buttons
        assert shown_at == (hud_left + x, hud_top + y)

    def test_the_pointer_leaving_the_window_takes_the_plus_down(self, tmp_path):
        funestra, engine = _wearing_a_panel(tmp_path)
        funestra.motion(WINDOW[0] - 2, WINDOW[1] - 2, held=False, window=WINDOW)
        funestra.tick(window=WINDOW)

        funestra.leave()
        funestra.tick(window=WINDOW)

        assert CORNER_PLUS_OVERLAY_ID not in engine.overlays


def test_each_pass_carries_a_still_s_move_a_little_further(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    assert engine.pushes == 1


def test_a_tiling_funestra_lays_its_picture_out_across_its_window(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")], tiles=True)

    funestra.tick(window=WINDOW)

    assert engine.tiled_to == [WINDOW]


def test_a_funestra_that_does_not_tile_is_never_asked_to(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    assert engine.tiled_to == []


def _publish_panel(tmp_path: Path, **panel) -> None:
    (tmp_path / "portrait_hud.json").write_text(json.dumps({"funestra": "portrait", **panel}),
                                                encoding="utf-8")


def test_the_panel_its_source_publishes_is_the_one_thing_over_the_picture(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")], hud=True)
    _publish_panel(tmp_path)

    funestra.tick(window=WINDOW)

    assert list(engine.overlays) == [HUD_OVERLAY_ID]


def test_a_panel_over_the_picture_carries_its_own_minus_so_none_hangs_outside_it(tmp_path):
    funestra, _engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")], hud=True)
    _publish_panel(tmp_path)

    funestra.tick(window=WINDOW)

    assert funestra.outside_buttons is None


def test_on_a_window_the_way_of_playing_is_mpv_opened_on_that_window(tmp_path):
    clips = _clips(tmp_path, "v0")
    channels = _channels(tmp_path, [str(clips[0])])
    engine = FakeEngine()

    with patch("funestra.funestra.MpvEngine", return_value=engine) as mpv:
        funestra = Funestra.on_window(4242, channels=channels, playlist=read_playlist(channels.playlist))

    mpv.assert_called_once_with(4242, muted=True, loop_file=False, prefetch=True)
    assert funestra.playback.current_video == clips[0]


def _console_channels(tmp_path: Path, lines: list[str], *, commands: str = "") -> Channels:
    channels = _channels(tmp_path, lines, commands=commands, in_a_session=True)
    return replace(channels, console=tmp_path / "console.json", drive=tmp_path / "drive.txt")


def _publish_console(tmp_path: Path, **over) -> None:
    model = ConsoleModel(main_mode=MainMode.KINO, rows=console_rows(), osr2=Osr2State.ROBOT_HAND, **over)
    (tmp_path / "console.json").write_text(console_text(model), encoding="utf-8")


class Kino:
    """What runs on a Funestra, as the Funestra sees it: its own verbs, a pass
    of its own each frame, lines in the status file, and the console's top block."""

    def __init__(self, playback) -> None:
        self.playback = playback
        self.commands: list[str] = []
        self.ticks: list[tuple[int, float]] = []
        self.video = "Jane Doe - scene one"
        self.showing: list[bool] = []
        self.closed = False

    def apply_command(self, command: str) -> bool:
        self.commands.append(command)
        return command.startswith("KINO_")

    def tick(self) -> None:
        self.ticks.append((self.playback.loads, self.playback.position_ms))

    def status_fields(self) -> dict[str, str]:
        return {"length_mode": "clips", "compilation": "Vol 3"}

    def top_block(self) -> ModeHud:
        return ModeHud(video=self.video, length_mode=LengthMode.CLIPS)

    def set_showing(self, showing: bool) -> None:
        self.showing.append(showing)

    def picture(self) -> Picture | None:
        return None

    def close(self) -> None:
        self.closed = True


class Genau(Kino):
    """A User that puts its own picture up: frames it decoded itself, counted
    in frames, which the Funestra shows in place of the video."""

    def __init__(self, playback) -> None:
        super().__init__(playback)
        self.video = "alpha"
        self.frame = np.zeros((8, 16, 3), dtype=np.uint8)
        self.flick = Path("C:/flicks/alpha.mp4")
        self.played, self.count = 6, 20
        self.elapsed_ms, self.interval_ms = 4_000.0, 10_000.0
        self.sought_times: list[float] = []
        self.sought_turns: list[float] = []

    def apply_command(self, command: str) -> bool:
        self.commands.append(command)
        return command.startswith("GENAU_")

    def status_fields(self) -> dict[str, str]:
        return {}

    def top_block(self) -> ModeHud:
        return ModeHud(video=self.video)

    def picture(self) -> Picture | None:
        return Picture(frame=self.frame, played=self.played, count=self.count,
                       elapsed_ms=self.elapsed_ms, interval_ms=self.interval_ms,
                       seek_time=self.sought_times.append, seek_loop=self.sought_turns.append,
                       flick=self.flick)


def _main(tmp_path: Path, *, commands: str = "", user=Kino,
          genau: bool = False, host_controls=None) -> tuple[Funestra, FakeEngine, Kino]:
    channels = _console_channels(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0", "v1")],
                                 commands=commands)
    _publish_console(tmp_path)
    engine = FakeEngine()
    made: list[Kino] = []

    def make(playback):
        made.append(user(playback))
        return made[-1]

    users = {"kino": make, **({"genau": Genau} if genau else {})}
    funestra = Funestra(engine, channels=channels, playlist=read_playlist(channels.playlist),
                        locked=True, sound_is_the_rooms=True, users=users,
                        host_controls=host_controls)
    return funestra, engine, made[0]


class TestTheMainFunestra:
    """A Funestra handed a console file draws the room's console in place of a
    satellite panel, opens holding its item, and leaves its sound to the room."""

    def test_it_opens_holding_its_item(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path)

        assert funestra.playback.is_locked is True
        assert engine.loop_file is True

    def test_it_draws_the_console_the_room_published(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path)

        funestra.tick(window=WINDOW)

        assert list(engine.overlays) == [HUD_OVERLAY_ID]

    def test_the_controls_its_host_hands_it_are_on_the_console_and_pressed_there(self, tmp_path):
        host = AHost()
        funestra, engine, _kino = _main(tmp_path, host_controls=host)
        funestra.tick(window=WINDOW)
        left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        x, y = middle_of(funestra._panel._painter.host_controls_layout.bar)

        funestra.press(left + x, top + y, window=WINDOW)

        assert host.set_to == [pytest.approx(110.0, abs=1.0)]

    def test_the_console_leads_with_what_runs_on_the_funestra_says_it_is_playing(self, tmp_path):
        funestra, engine, kino = _main(tmp_path)
        funestra.tick(window=WINDOW)
        before = engine.overlays[HUD_OVERLAY_ID][2]

        kino.video = "Ann Bly - scene two"
        funestra.tick(window=WINDOW)

        assert engine.overlays[HUD_OVERLAY_ID][2] is not before

    def test_a_press_on_a_console_button_asks_the_room_and_never_pauses_it(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path)
        funestra.tick(window=WINDOW)
        left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        (x, y, w, h), button = funestra._panel._painter.buttons[0]

        funestra.press(left + x + w // 2, top + y + h // 2, window=WINDOW)

        assert _asked(tmp_path) == [button.command]

    def test_a_press_on_the_slab_between_buttons_asks_for_nothing(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path)
        funestra.tick(window=WINDOW)
        left, top, bgra = engine.overlays[HUD_OVERLAY_ID]

        funestra.press(left + bgra.shape[1] - 2, top + bgra.shape[0] - 2, window=WINDOW)

        assert _asked(tmp_path) == []

    def test_its_sound_is_the_rooms_so_the_chip_asks_rather_than_sets(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path)
        funestra.tick(window=WINDOW)

        funestra.press(*_on_the_row(funestra, engine, "slider"), window=WINDOW)

        assert _asked(tmp_path) == ["audio_set_volume|100"]
        assert engine.volume == 100

    def test_the_rooms_level_reaches_the_engine_through_the_command_file(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path, commands="SET_VOLUME 40 0\n")

        funestra.tick(window=WINDOW)

        assert engine.volume == 40

    def test_it_opens_unmuted_so_the_rooms_level_is_heard(self, tmp_path):
        _funestra, engine, _kino = _main(tmp_path)

        assert engine.muted is False

    def test_a_held_band_is_let_go_when_the_button_comes_up(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path)
        _publish_console(tmp_path, max_intensity=50)
        funestra.tick(window=WINDOW)
        left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        x, y, _w, h = funestra._panel._painter.tracks[0].rect
        funestra.press(left + x, top + y + h // 2, window=WINDOW)
        assert funestra._panel.holding is True

        funestra.release()

        assert funestra._panel.holding is False


class TestWhatRunsOnTheFunestra:
    def test_what_runs_on_it_can_be_told_from_what_cannot(self):
        assert isinstance(_Nobody(), User)
        assert not isinstance(object(), User)

    def test_it_is_handed_the_playback_it_runs_on(self, tmp_path):
        funestra, _engine, kino = _main(tmp_path)

        assert kino.playback is funestra.playback

    def test_its_verbs_are_asked_before_the_funestras_own(self, tmp_path):
        funestra, _engine, kino = _main(tmp_path, commands="KINO_THING\nNEXT\n")

        funestra.tick(window=WINDOW)

        assert kino.commands == ["KINO_THING", "NEXT"]
        assert funestra.playback.index == 1

    def test_a_verb_neither_answers_is_named_on_the_log(self, tmp_path, caplog):
        funestra, _engine, _kino = _main(tmp_path, commands="FLOOP\n")

        with caplog.at_level("WARNING", logger="funestra.funestra"):
            funestra.tick(window=WINDOW)

        assert "FLOOP" in caplog.text

    def test_it_takes_a_pass_of_its_own_each_frame_before_the_playback_advances(self, tmp_path):
        funestra, engine, kino = _main(tmp_path, commands="NEXT\n")
        funestra.playback.set_locked(False)
        engine.position_ms = 1_000.0

        funestra.tick(window=WINDOW)
        engine.simulate_eof_advance()
        funestra.tick(window=WINDOW)

        assert [loads for loads, _position in kino.ticks] == [2, 2]
        assert funestra.playback.loads == 3

    def test_its_lines_ride_in_the_status_file_after_the_funestras_own(self, tmp_path):
        funestra, _engine, _kino = _main(tmp_path)

        funestra.tick(window=WINDOW)

        status = _status(tmp_path)
        assert "length_mode=clips\n" in status
        assert "compilation=Vol 3\n" in status
        assert status.index("portrait=") < status.index("length_mode=")


def _scripted_main(tmp_path: Path) -> tuple[Funestra, FakeEngine]:
    clip = _clips(tmp_path, "v0")[0]
    script = tmp_path / "v0.funscript"
    script.write_text('{"actions": [{"at": 0, "pos": 0}, {"at": 900, "pos": 100}, '
                      '{"at": 2400, "pos": 10}]}', encoding="utf-8")
    channels = _console_channels(tmp_path, [f"{clip}\t{script}"])
    _publish_console(tmp_path)
    engine = FakeEngine(duration_ms=600_000.0)
    engine.screenshot = np.zeros((10, 20, 4), dtype=np.uint8)
    return Funestra(engine, channels=channels, playlist=read_playlist(channels.playlist),
                    locked=True, sound_is_the_rooms=True, users={"kino": Kino}), engine


class TestAStretchOfTheItem:
    def test_a_mark_zooms_the_track_to_the_stretch_around_it(self, tmp_path):
        funestra, engine = _scripted_main(tmp_path)
        funestra.tick(window=WINDOW)
        assert funestra.clip_row().duration_ms == engine.duration_ms

        funestra.playback.set_mark(50_000)
        engine.position_ms = 51_000.0
        funestra.tick(window=WINDOW)

        row = funestra.clip_row()
        assert row.duration_ms < engine.duration_ms
        assert row.record_in_ms == 50_000 - funestra._strip.window[0]

    def test_a_press_on_the_zoomed_track_seeks_inside_the_stretch_it_shows(self, tmp_path):
        funestra, engine = _scripted_main(tmp_path)
        funestra.playback.set_mark(50_000)
        engine.position_ms = 51_000.0
        funestra.tick(window=WINDOW)

        funestra.press(*_on_the_row(funestra, engine), window=WINDOW)

        assert 48_000 <= engine.seeks[-1] <= 70_000

    def test_a_running_range_hangs_its_two_frames_under_the_panel(self, tmp_path):
        funestra, engine = _scripted_main(tmp_path)
        funestra.playback.set_ab_loop(2_000, 4_000)
        engine.position_ms = 2_000.0

        funestra.tick(window=WINDOW)
        engine.position_ms = 3_700.0
        funestra.tick(window=WINDOW)

        assert {Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID} <= set(engine.overlays)
        assert engine.overlays[Funestra.IN_FRAME_OVERLAY_ID][2] is engine.screenshot
        panel_top, panel = engine.overlays[HUD_OVERLAY_ID][1], engine.overlays[HUD_OVERLAY_ID][2]
        assert engine.overlays[Funestra.IN_FRAME_OVERLAY_ID][1] >= panel_top + panel.shape[0]

    def test_the_end_of_the_range_takes_both_frames_down(self, tmp_path):
        funestra, engine = _scripted_main(tmp_path)
        funestra.playback.set_ab_loop(2_000, 4_000)
        funestra.tick(window=WINDOW)

        funestra.playback.clear_ab_loop()
        funestra.tick(window=WINDOW)

        assert not {Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID} & set(engine.overlays)

    def test_a_frame_mpv_could_not_give_is_asked_for_again(self, tmp_path):
        funestra, engine = _scripted_main(tmp_path)
        engine.screenshot = None
        funestra.playback.set_ab_loop(2_000, 4_000)

        funestra.tick(window=WINDOW)

        assert Funestra.IN_FRAME_OVERLAY_ID not in engine.overlays
        assert engine.screenshots == 1

    def test_the_frames_sit_under_the_panel(self):
        assert max(Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID) < HUD_OVERLAY_ID


class TestWhoHasTheWindow:
    """Two things run on the Main Funestra -- Kino and Genau -- and the room says
    which one has the window.  The other keeps running out of sight."""

    def test_the_first_user_has_the_window_until_the_room_says_otherwise(self, tmp_path):
        funestra, _engine, kino = _main(tmp_path, genau=True)

        assert funestra.showing == "kino"
        assert kino.showing == [True]

    def test_show_hands_the_window_over_and_tells_both(self, tmp_path):
        funestra, _engine, kino = _main(tmp_path, commands="SHOW genau\n", genau=True)

        funestra.tick(window=WINDOW)

        assert funestra.showing == "genau"
        assert kino.showing == [True, False]
        assert funestra._users["genau"].showing == [True]

    def test_show_naming_nobody_on_this_window_is_refused_and_named_on_the_log(self, tmp_path, caplog):
        funestra, _engine, _kino = _main(tmp_path, commands="SHOW slideshow\n", genau=True)

        with caplog.at_level("WARNING", logger="funestra.funestra"):
            funestra.tick(window=WINDOW)

        assert funestra.showing == "kino"
        assert "SHOW slideshow" in caplog.text

    def test_every_user_takes_its_pass_and_answers_its_own_verbs_whoever_has_the_window(self, tmp_path):
        funestra, _engine, kino = _main(tmp_path, commands="GENAU_THING\nKINO_THING\n", genau=True)

        funestra.tick(window=WINDOW)

        genau = funestra._users["genau"]
        assert kino.commands == ["GENAU_THING", "KINO_THING"]
        assert genau.commands == ["GENAU_THING"]
        assert len(kino.ticks) == len(genau.ticks) == 1

    def test_closing_the_window_closes_everything_running_on_it(self, tmp_path):
        funestra, _engine, kino = _main(tmp_path, genau=True)

        funestra.close()

        assert (kino.closed, funestra._users["genau"].closed) == (True, True)


class TestAUsersOwnPicture:
    """Genau shows frames it decoded itself, so with the window it puts them up
    over the video, and the row and the track answer for them."""

    def _genau_in_front(self, tmp_path):
        funestra, engine, _kino = _main(tmp_path, commands="SHOW genau\n", genau=True)
        funestra.tick(window=WINDOW)
        return funestra, engine, funestra._users["genau"]

    def test_its_frame_goes_up_over_the_video_under_the_console(self, tmp_path):
        _funestra, engine, _genau = self._genau_in_front(tmp_path)

        assert {BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID, HUD_OVERLAY_ID} <= set(engine.overlays)
        assert engine.overlays[FIRST_TILE_OVERLAY_ID][2].shape[1] == WINDOW[0]

    def test_a_corner_the_console_is_not_in_still_shows_its_plus_over_the_frame(
            self, tmp_path):
        funestra, engine, _genau = self._genau_in_front(tmp_path)

        funestra.motion(WINDOW[0] - 2, WINDOW[1] - 2, held=False, window=WINDOW)
        funestra.tick(window=WINDOW)

        assert CORNER_PLUS_OVERLAY_ID in engine.overlays

    def test_a_press_in_a_corner_the_console_is_not_in_asks_for_the_console_there(
            self, tmp_path):
        funestra, _engine, _genau = self._genau_in_front(tmp_path)

        funestra.press(WINDOW[0] - 2, WINDOW[1] - 2, window=WINDOW)

        assert _asked(tmp_path) == ["main_hud_restore_at|lower_right"]

    def test_the_console_leads_with_what_it_says_it_is_playing(self, tmp_path):
        funestra, engine, genau = self._genau_in_front(tmp_path)
        before = engine.overlays[HUD_OVERLAY_ID][2]

        genau.video = "beta"
        funestra.tick(window=WINDOW)

        assert engine.overlays[HUD_OVERLAY_ID][2] is not before

    def test_the_row_runs_its_pictures_time_on_screen_and_turns_its_dial(self, tmp_path):
        """A flick has two senses of time: the track runs how long it has been
        up of the seconds it gets, and the dial beside it goes round with the
        loop of the clip itself."""
        funestra, _engine, genau = self._genau_in_front(tmp_path)

        row = funestra._panel._clip_row

        assert (row.position_ms, row.duration_ms) == (genau.elapsed_ms, genau.interval_ms)
        assert row.playhead.text == f"frame {FIGURE_SPACE}6 / 20 · 0:04 / 0:10"
        assert row.loop == (genau.played, genau.count)
        assert row.volume is funestra._volume.hud

    def test_a_press_on_the_track_puts_its_picture_that_far_into_its_time_rather_than_the_video(
            self, tmp_path):
        funestra, engine, genau = self._genau_in_front(tmp_path)
        x0, x1 = funestra._panel.row.track

        funestra.press(*_on_the_row(funestra, engine), window=WINDOW)

        assert engine.seeks == []
        assert len(genau.sought_times) == 1
        assert abs(genau.sought_times[0] - genau.interval_ms / 2) <= genau.interval_ms / (x1 - x0)
        assert genau.sought_turns == []

    def test_a_press_on_the_dial_turns_its_pictures_loop(self, tmp_path):
        funestra, engine, genau = self._genau_in_front(tmp_path)

        funestra.press(*_on_the_row(funestra, engine, "dial"), window=WINDOW)

        assert engine.seeks == []
        assert genau.sought_times == []
        assert genau.sought_turns == [pytest.approx(0.25, abs=0.03)]

    def test_the_videos_loop_frames_stay_down_while_it_has_the_window(self, tmp_path):
        funestra, engine, _genau = self._genau_in_front(tmp_path)
        funestra.playback.set_ab_loop(2_000, 4_000)
        engine.screenshot = np.zeros((10, 20, 4), dtype=np.uint8)

        funestra.tick(window=WINDOW)

        assert not {Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID} & set(engine.overlays)

    def test_handing_the_window_back_takes_its_picture_down_and_the_videos_row_returns(self, tmp_path):
        funestra, engine, _genau = self._genau_in_front(tmp_path)
        (tmp_path / "cmd.txt").write_text("SHOW kino\n", encoding="utf-8")

        funestra.tick(window=WINDOW)

        assert not {BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID} & set(engine.overlays)
        assert funestra._panel._clip_row.duration_ms == engine.duration_ms


class TestAWindowsOwnPanel:
    """A window handed a panel of its own -- built in its process, as a
    standalone Origenerator builds its Slideshow's -- wears it where a session
    would have published one, and hands its presses to what runs on the window."""

    def _own_panel(self, tmp_path, *, user=Kino, muted=True):
        clips = _clips(tmp_path, "v0", "v1")
        channels = _channels(tmp_path, [str(clip) for clip in clips], commands="")
        engine = FakeEngine()
        made: list[Kino] = []

        def make(playback):
            made.append(user(playback))
            return made[-1]

        panel = [HudModel(funestra="portrait", lock_label="Unlocked",
                          rows=((Button("portrait_next", "N", "Next"),),))]
        funestra = Funestra(engine, channels=channels, playlist=read_playlist(channels.playlist),
                            users={"slideshow": make}, panel=lambda: panel[0], muted=muted)
        return funestra, engine, made[0], panel

    def test_it_is_drawn_over_the_picture_where_no_session_published_one(self, tmp_path):
        funestra, engine, _user, _panel = self._own_panel(tmp_path)

        funestra.tick(window=WINDOW)

        assert list(engine.overlays) == [HUD_OVERLAY_ID]

    def test_a_press_on_one_of_its_buttons_reaches_what_runs_on_the_window(self, tmp_path):
        funestra, engine, user, _panel = self._own_panel(tmp_path)
        funestra.tick(window=WINDOW)
        left, top, _bgra = engine.overlays[HUD_OVERLAY_ID]
        (x, y, w, h), _button = next((rect, b) for rect, b in funestra._panel.targets.buttons
                                     if b.command == "portrait_next")

        funestra.press(left + x + w // 2, top + y + h // 2, window=WINDOW)

        assert user.commands == ["portrait_next"]
        assert _asked(tmp_path) == []

    def test_a_press_on_the_picture_asks_what_runs_on_the_window_to_pause(self, tmp_path):
        funestra, engine, user, _panel = self._own_panel(tmp_path)
        funestra.tick(window=WINDOW)
        left, top, panel = engine.overlays[HUD_OVERLAY_ID]

        funestra.press(left + panel.shape[1] // 2, top + panel.shape[0] + 20, window=WINDOW)

        assert user.commands == [OMNIPAUSE_TOGGLE]
        assert _asked(tmp_path) == []

    def test_it_is_redrawn_when_the_panel_changes_and_only_then(self, tmp_path):
        funestra, engine, _user, panel = self._own_panel(tmp_path)
        funestra.tick(window=WINDOW)
        funestra.tick(window=WINDOW)  # the second fills the track at the width the first measured
        first = engine.overlays[HUD_OVERLAY_ID][2]
        funestra.tick(window=WINDOW)
        assert engine.overlays[HUD_OVERLAY_ID][2] is first

        panel[0] = replace(panel[0], locked=True, lock_label="Locked")
        funestra.tick(window=WINDOW)

        assert engine.overlays[HUD_OVERLAY_ID][2] is not first

    def test_it_comes_down_when_what_runs_on_the_window_has_no_panel_to_show(self, tmp_path):
        funestra, engine, _user, panel = self._own_panel(tmp_path)
        funestra.tick(window=WINDOW)

        panel[0] = None
        funestra.tick(window=WINDOW)

        assert HUD_OVERLAY_ID not in engine.overlays

    def test_it_names_the_item_as_what_runs_on_the_window_names_it(self, tmp_path):
        funestra, engine, user, _panel = self._own_panel(tmp_path)
        funestra.tick(window=WINDOW)
        first = engine.overlays[HUD_OVERLAY_ID][2]

        user.video = "Example Studio / seed 7"
        funestra.tick(window=WINDOW)

        assert engine.overlays[HUD_OVERLAY_ID][2] is not first

    def test_the_rows_track_and_chip_are_the_windows_own(self, tmp_path):
        funestra, engine, _user, _panel = self._own_panel(tmp_path)
        funestra.tick(window=WINDOW)

        funestra.press(*_on_the_row(funestra, engine), window=WINDOW)

        assert len(engine.seeks) == 1

    def test_it_opens_heard_when_told_to(self, tmp_path):
        funestra, _engine, _user, _panel = self._own_panel(tmp_path, muted=False)

        assert funestra._volume.hud.muted is False

    def test_it_opens_silent_unless_told_otherwise(self, tmp_path):
        funestra, _engine, _user, _panel = self._own_panel(tmp_path)

        assert funestra._volume.hud.muted is True


def test_on_a_window_the_way_of_playing_can_be_heard(tmp_path):
    clips = _clips(tmp_path, "v0")
    channels = _channels(tmp_path, [str(clips[0])])

    with patch("funestra.funestra.MpvEngine", return_value=FakeEngine()) as mpv:
        Funestra.on_window(4242, channels=channels, playlist=read_playlist(channels.playlist),
                           muted=False)

    mpv.assert_called_once_with(4242, muted=False, loop_file=False, prefetch=True)


def test_a_window_told_to_fall_silent_mutes_its_engine_and_its_chip(tmp_path):
    funestra, engine = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])
    funestra.tick(window=WINDOW)

    funestra.set_muted(True)
    assert (engine.muted, funestra._volume.hud.muted) == (True, True)

    funestra.set_muted(False)
    assert (engine.muted, funestra._volume.hud.muted) == (False, False)


class _ASurface:
    """A screen of the window's own beside the picture: what a headset gives
    its panel, which hangs there rather than lying over the video."""

    def __init__(self, width: int | None = None) -> None:
        self.width = width
        self.overlays: dict[int, tuple[int, int, object]] = {}

    def overlay(self, ident: int, x: int, y: int, bgra) -> None:
        self.overlays[ident] = (x, y, bgra)

    def remove_overlay(self, ident: int) -> None:
        self.overlays.pop(ident, None)


class TestAPanelBesideThePicture:
    """A headset hangs the panel as a screen of its own beside the picture, so
    a Funestra on such a window draws it there and leaves the picture alone."""

    def _wearing_a_panel_beside(self, tmp_path, surface=None):
        surface = surface or _ASurface()
        clips = _clips(tmp_path, "v0")
        channels = _channels(tmp_path, [str(clips[0])], hud=True, commands="")
        _publish_panel(tmp_path)
        engine = FakeEngine()
        funestra = Funestra(engine, channels=channels, playlist=read_playlist(channels.playlist),
                            panel_surface=surface)
        funestra.tick(window=WINDOW)
        return funestra, engine, surface

    def test_the_panel_is_drawn_on_the_surface_and_nothing_on_the_picture(self, tmp_path):
        _funestra, engine, surface = self._wearing_a_panel_beside(tmp_path)

        assert list(surface.overlays) == [HUD_OVERLAY_ID]
        assert engine.overlays == {}

    def test_it_fills_its_surface_from_the_corner_whatever_corner_the_room_published(self, tmp_path):
        """The room's corner places a panel over the picture; a screen of its
        own has no picture to be placed on, so the panel starts at its edge the
        way test_hud_overlay says a panel beside the picture does."""
        (tmp_path / "portrait_hud.json").write_text(
            json.dumps({"funestra": "portrait", "hud_corner": "lower_right"}), encoding="utf-8")
        clips = _clips(tmp_path, "v0")
        channels = _channels(tmp_path, [str(clips[0])], hud=True, commands="")
        surface = _ASurface()
        funestra = Funestra(FakeEngine(), channels=channels,
                            playlist=read_playlist(channels.playlist), panel_surface=surface)

        funestra.tick(window=WINDOW)

        assert surface.overlays[HUD_OVERLAY_ID][:2] == (MARGIN, MARGIN)

    def _main_beside(self, tmp_path, surface, *, genau: bool = False, commands: str = "",
                     users_picture=None):
        channels = _console_channels(
            tmp_path, [str(clip) for clip in _clips(tmp_path, "v0", "v1")], commands=commands)
        _publish_console(tmp_path)
        engine = FakeEngine()
        users = {"kino": Kino, **({"genau": Genau} if genau else {})}
        funestra = Funestra(engine, channels=channels, playlist=read_playlist(channels.playlist),
                            locked=True, sound_is_the_rooms=True, users=users,
                            panel_surface=surface, users_picture=users_picture)
        funestra.tick(window=WINDOW)
        return funestra, engine

    def test_the_console_is_held_to_the_surfaces_width(self, tmp_path):
        """A console sized to its contents changes size between the modes and
        with the title, and a screen that grows and shrinks is a screen that
        moves; the surface says the one width it is held to."""
        surface = _ASurface(width=600)

        self._main_beside(tmp_path, surface)

        assert surface.overlays[HUD_OVERLAY_ID][2].shape[1] == 600

    def test_the_window_is_told_which_edge_of_the_picture_the_panel_hangs_along(self, tmp_path):
        """The room moves the panel between the picture's edges; a window that
        hangs the panel beside the picture has to hear which one."""
        funestra, _engine = self._main_beside(tmp_path, _ASurface())
        assert funestra.panel_edge is HudEdge.LOWER

        _publish_console(tmp_path, hud_edge=HudEdge.RIGHT)
        funestra.tick(window=WINDOW)

        assert funestra.panel_edge is HudEdge.RIGHT

    def test_a_published_panel_says_its_edge_the_same_way(self, tmp_path):
        funestra, _engine, _surface = self._wearing_a_panel_beside(tmp_path)
        (tmp_path / "portrait_hud.json").write_text(
            json.dumps({"funestra": "portrait", "hud_edge": "upper"}), encoding="utf-8")

        funestra.tick(window=WINDOW)

        assert funestra.panel_edge is HudEdge.UPPER

    def test_minimized_beside_the_picture_the_panel_leaves_its_plus_to_the_window(self, tmp_path):
        funestra, _engine, surface = self._wearing_a_panel_beside(tmp_path)
        _publish_panel(tmp_path, hud_minimized=True)

        funestra.tick(window=WINDOW)

        assert HUD_OVERLAY_ID not in surface.overlays
        assert funestra.panel_minimized

    def test_minimized_beside_the_picture_the_console_leaves_its_plus_to_the_window(self, tmp_path):
        surface = _ASurface(width=380)
        funestra, _engine = self._main_beside(tmp_path, surface)
        _publish_console(tmp_path, hud_minimized=True)

        funestra.tick(window=WINDOW)

        assert HUD_OVERLAY_ID not in surface.overlays
        assert funestra.panel_minimized

    def test_an_open_panel_is_not_minimized(self, tmp_path):
        funestra, _engine, _surface = self._wearing_a_panel_beside(tmp_path)

        assert not funestra.panel_minimized

    def test_the_window_is_handed_the_minus_that_hangs_outside_an_open_panel(self, tmp_path):
        funestra, _engine, _surface = self._wearing_a_panel_beside(tmp_path)

        assert funestra.outside_buttons.toggle(pointed=False).command == "portrait_hud_minimize"

    def test_minimized_the_window_is_handed_the_plus_on_that_same_spot_to_open_it(self, tmp_path):
        funestra, _engine, _surface = self._wearing_a_panel_beside(tmp_path)
        _publish_panel(tmp_path, hud_minimized=True)

        funestra.tick(window=WINDOW)

        assert funestra.outside_buttons.toggle(pointed=False).command == "portrait_hud_restore"

    def test_the_console_beside_the_picture_hands_the_window_its_minus_too(self, tmp_path):
        funestra, _engine = self._main_beside(tmp_path, _ASurface(width=380))

        assert funestra.outside_buttons.toggle(pointed=False).command == "main_hud_minimize"

    def test_before_its_panel_has_been_read_nothing_hangs_outside_it(self, tmp_path):
        clips = _clips(tmp_path, "v0")
        channels = _channels(tmp_path, [str(clips[0])], hud=True, commands="")
        funestra = Funestra(FakeEngine(), channels=channels,
                            playlist=read_playlist(channels.playlist), panel_surface=_ASurface())

        assert funestra.outside_buttons is None

    def test_a_press_is_placed_by_the_surfaces_own_pixels_and_where_the_panel_was_drawn(self, tmp_path):
        """A squeeze on the hanging screen lands in the panel's own pixels; the
        window adds where the panel was drawn and the row answers as it would
        over the picture."""
        funestra, engine, surface = self._wearing_a_panel_beside(tmp_path)
        funestra.tick(window=WINDOW)
        left, top, _bgra = surface.overlays[HUD_OVERLAY_ID]
        x, y, _width, height = funestra._panel.row.rect
        x0, x1 = funestra._panel.row.track

        funestra.press(left + x + (x0 + x1) // 2, top + y + height - 4, window=WINDOW)

        assert len(engine.seeks) == 1
        assert abs(engine.seeks[0] - engine.duration_ms / 2) <= engine.duration_ms / (x1 - x0)

    def test_the_loops_frames_stay_off_a_picture_the_panel_does_not_lie_on(self, tmp_path):
        """They hang under the panel's track in the window; a panel on a screen
        of its own has no stretch of the picture under it to hang them from."""
        funestra, engine = self._main_beside(tmp_path, _ASurface())
        funestra.playback.set_ab_loop(1_000, 3_000)
        engine.screenshot = np.zeros((10, 20, 4), dtype=np.uint8)

        funestra.tick(window=WINDOW)
        funestra.tick(window=WINDOW)

        assert engine.overlays == {}
        assert engine.screenshots == 0


class _APictureSurface:
    """Where a headset puts a User's own picture: a texture of its own, wrapped
    the way the clip is, rather than tiles over the video."""

    def __init__(self) -> None:
        self.shown: list[tuple[Picture, tuple[int, int]]] = []
        self.hidden = 0

    def show(self, picture: Picture, window: tuple[int, int]) -> None:
        self.shown.append((picture, window))

    def hide(self) -> None:
        self.hidden += 1


class TestAUsersOwnPictureElsewhere:
    """A window may show a User's own picture somewhere other than over the
    engine's: it is handed the picture whenever one is up and told when none is."""

    def test_the_picture_is_handed_over_and_the_video_is_left_alone(self, tmp_path):
        surface = _APictureSurface()
        funestra, engine = TestAPanelBesideThePicture()._main_beside(
            tmp_path, _ASurface(), genau=True, commands="SHOW genau\n", users_picture=surface)
        genau = funestra._users["genau"]

        funestra.tick(window=WINDOW)

        picture, window = surface.shown[-1]
        assert (picture.frame, picture.played, picture.count, picture.flick, window) == (
            genau.frame, genau.played, genau.count, genau.flick, WINDOW)
        assert engine.overlays == {}

    def test_it_is_told_when_no_picture_is_up(self, tmp_path):
        surface = _APictureSurface()
        funestra, _engine = TestAPanelBesideThePicture()._main_beside(
            tmp_path, _ASurface(), genau=True, commands="SHOW genau\n", users_picture=surface)
        (tmp_path / "cmd.txt").write_text("SHOW kino\n", encoding="utf-8")

        funestra.tick(window=WINDOW)

        assert surface.hidden == 1


class TestTheWindowsOwnVerbs:
    """A window may answer verbs of its own -- a headset's projection, tilt and
    scenes -- asked after what runs on it and before the Funestra's own."""

    def _answering(self, tmp_path, commands: str):
        heard: list[str] = []

        def window_verbs(command: str) -> bool:
            heard.append(command)
            return command.startswith("TILT_")

        channels = _console_channels(
            tmp_path, [str(clip) for clip in _clips(tmp_path, "v0", "v1")], commands=commands)
        _publish_console(tmp_path)
        engine = FakeEngine()
        funestra = Funestra(engine, channels=channels, playlist=read_playlist(channels.playlist),
                            locked=True, sound_is_the_rooms=True, users={"kino": Kino},
                            window_verbs=window_verbs)
        return funestra, engine, heard

    def test_a_verb_of_the_windows_own_is_answered_and_not_refused(self, tmp_path, caplog):
        funestra, _engine, heard = self._answering(tmp_path, "TILT_UP\n")

        with caplog.at_level("WARNING", logger="funestra.funestra"):
            funestra.tick(window=WINDOW)

        assert heard == ["TILT_UP"]
        assert "Unhandled" not in caplog.text

    def test_what_runs_on_the_window_is_asked_first_and_the_funestra_last(self, tmp_path):
        funestra, engine, heard = self._answering(tmp_path, "KINO_THING\nNEXT\n")

        funestra.tick(window=WINDOW)

        assert heard == ["NEXT"]
        assert funestra._users["kino"].commands == ["KINO_THING", "NEXT"]
        assert funestra.playback.index == 1
