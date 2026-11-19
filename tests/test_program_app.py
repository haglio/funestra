from __future__ import annotations

import contextlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pytest
from PIL import Image

import funestra.program.app as program_app
from funestra.channel_manifest import channel_flag, channels_from_args
from funestra.funestra import Channels
from funestra.funestra_setup import FunestraSetup
from funestra.funestra_verbs import QUIT
from funestra.program.app import _run
from funestra.program.cli import build_parser, resolve_playlist
from funestra.program.window_verbs import WindowVerbs

WINDOW = (640, 480)


class _FakePygame:
    QUIT = 256
    MOUSEBUTTONDOWN = 1025
    MOUSEMOTION = 1024

    def __init__(self, event_batches=()):
        self._batches = list(event_batches)
        self.quit_called = False
        self.display = SimpleNamespace(
            set_icon=lambda *_a: None,
            set_mode=lambda *_a, **_kw: None,
            set_caption=lambda *_a: None,
            get_wm_info=lambda: {"window": 4242},
            get_window_size=lambda: WINDOW,
        )
        self.event = SimpleNamespace(get=self._next_batch)
        self.time = SimpleNamespace(Clock=lambda: SimpleNamespace(tick=lambda _fps: None))
        self.NOFRAME = 32
        self.HIDDEN = 128
        self.KEYDOWN = 768
        self.mouse = SimpleNamespace(get_pos=lambda: (0, 0))
        self.key = pygame.key
        self.window = SimpleNamespace(resizable=False)
        self.Window = SimpleNamespace(from_display_module=lambda: self.window)

    def _next_batch(self):
        return self._batches.pop(0) if self._batches else []

    def init(self):
        pass

    def quit(self):
        self.quit_called = True


class _FakeFunestra:
    def __init__(self, *, passes: int = 1) -> None:
        self._passes_left = passes
        self.ticks: list[tuple[int, int]] = []
        self.presses: list[tuple] = []
        self.right_presses: list[tuple] = []
        self.motions: list[tuple] = []
        self.closes_requested = 0
        self.closed = False
        self.applied: list[str] = []

    @property
    def stopped(self) -> bool:
        return self._passes_left <= 0

    def tick(self, *, viewport) -> None:
        self.ticks.append(viewport)
        self._passes_left -= 1

    def press(self, x, y, *, viewport) -> None:
        self.presses.append((x, y, viewport))

    def right_press(self, x, y, *, viewport) -> None:
        self.right_presses.append((x, y, viewport))

    def motion(self, x, y, *, held, viewport) -> None:
        self.motions.append((x, y, held, viewport))

    def close_requested(self) -> None:
        self.closes_requested += 1

    def close(self) -> None:
        self.closed = True

    def apply(self, command: str) -> None:
        self.applied.append(command)
        self._passes_left = 0


class _OpensAFunestra:
    def __init__(self, funestra: _FakeFunestra) -> None:
        self.funestra = funestra
        self.asked: tuple | None = None

    def on_window(self, wid, setup):
        self.asked = (wid, setup)
        return self.funestra


def _loop_args(tmp_path: Path, playlist: list[Path], *, no_audio: bool = False,
               tile: bool = False, **extra: str):
    argv = [channel_flag("playlist"), str(tmp_path / "playlist.tsv"),
            channel_flag("command"), str(tmp_path / "cmd.txt"),
            channel_flag("paused"), str(tmp_path / "paused.txt"),
            channel_flag("status"), str(tmp_path / "status.txt"),
            "--title", "Portrait AI Funestra"]
    if no_audio:
        argv.append("--no-audio")
    if tile:
        argv.append("--tile")
    for flag, value in extra.items():
        argv += [f"--{flag.replace('_', '-')}"] + ([] if value is True else [value])
    (tmp_path / "playlist.tsv").write_text(
        "".join(f"{video}\n" for video in playlist), encoding="utf-8")
    return build_parser().parse_args(argv)


def _videos(tmp_path: Path, *names: str) -> list[Path]:
    out = []
    for name in names:
        video = tmp_path / f"{name}.mp4"
        video.write_bytes(b"")
        out.append(video)
    return out


def _run_loop(tmp_path: Path, args, *, fake=None, passes: int = 1, claim_identity=None,
              wear_button=lambda *_worn: None, **how):
    fake = fake or _FakePygame()
    opens = _OpensAFunestra(_FakeFunestra(passes=passes))
    with patch("funestra.program.app.pygame", fake), \
         patch("funestra.program.app.before_the_window_exists"), \
         patch("funestra.program.app.wear_the_sessions_taskbar_button", wear_button), \
         patch("funestra.program.app.Funestra", opens):
        code = _run(args, playlist=resolve_playlist(args), claim_identity=claim_identity, **how)
    return code, opens, fake


def test_a_funestra_wears_the_icon_the_session_hands_it(tmp_path):
    handed = tmp_path / "preview_icon.ico"
    Image.new("RGBA", (16, 16), (200, 30, 30, 255)).save(handed)
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"), icon=str(handed))
    fake = _FakePygame()
    worn = []
    fake.display.set_icon = worn.append
    fake.image = pygame.image

    _run_loop(tmp_path, args, fake=fake)

    assert len(worn) == 1


def test_the_funestra_is_opened_on_the_window_with_what_the_launch_hands_it(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0", "v1"))

    _code, opens, _fake = _run_loop(tmp_path, args)

    wid, setup = opens.asked
    assert wid == 4242
    assert setup._replace(window_verbs=None) == FunestraSetup(
        channels=Channels(**channels_from_args(args)),
        playlist=resolve_playlist(args),
        audible=True,
        tiles=False,
        window_verbs=None,
    )


def test_no_audio_opens_a_silent_one(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"), no_audio=True)

    _code, opens, _fake = _run_loop(tmp_path, args)

    assert opens.asked[1].audible is False


def test_tile_opens_one_that_tiles_its_item(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"), tile=True)

    _code, opens, _fake = _run_loop(tmp_path, args)

    assert opens.asked[1].tiles is True


def test_each_pass_hands_it_the_windows_size_until_it_stops_then_closes_it(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"))

    code, opens, fake = _run_loop(tmp_path, args, passes=3)

    assert code == 0
    assert opens.funestra.ticks == [WINDOW, WINDOW, WINDOW]
    assert opens.funestra.closed
    assert fake.quit_called


def _press(pos, button=1):
    return SimpleNamespace(type=_FakePygame.MOUSEBUTTONDOWN, button=button, pos=pos)


def _motion(pos, *, held: bool):
    return SimpleNamespace(type=_FakePygame.MOUSEMOTION, pos=pos, buttons=(int(held), 0, 0))


def test_a_left_press_a_right_press_and_a_motion_reach_it_placed_in_the_window(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"))
    fake = _FakePygame(event_batches=[[_press((10, 20)), _press((11, 21), button=3),
                                       _motion((30, 40), held=True)]])

    _code, opens, _fake = _run_loop(tmp_path, args, fake=fake)

    assert opens.funestra.presses == [(10, 20, WINDOW)]
    assert opens.funestra.right_presses == [(11, 21, WINDOW)]
    assert opens.funestra.motions == [(30, 40, True, WINDOW)]


def test_the_windows_close_is_the_funestras_to_answer_and_the_loop_goes_on(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"))
    fake = _FakePygame(event_batches=[[SimpleNamespace(type=_FakePygame.QUIT)]])

    _code, opens, _fake = _run_loop(tmp_path, args, fake=fake, passes=2)

    assert opens.funestra.closes_requested == 1
    assert len(opens.funestra.ticks) == 2


def test_the_window_takes_the_size_fun_time_gives_it_from_outside(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"))

    _code, _opens, fake = _run_loop(tmp_path, args)

    assert fake.window.resizable is True


@pytest.fixture
def plays(monkeypatch):
    played = []
    monkeypatch.setattr(program_app, "set_up_logging", lambda: None)
    monkeypatch.setattr(program_app, "_run", lambda _args, _playlist, **_how: played.append("plays") or 0)
    return played


def test_the_funestra_plays_ahead_of_background_work(tmp_path, monkeypatch, plays):
    playlist = tmp_path / "playlist.tsv"
    playlist.write_text(f"{_videos(tmp_path, 'v0')[0]}\n", encoding="utf-8")

    @contextlib.contextmanager
    def ahead_on_the_processor():
        plays.append("ahead")
        yield
        plays.append("back")

    monkeypatch.setattr(program_app, "ahead_on_the_processor", ahead_on_the_processor)

    assert program_app.main([channel_flag("playlist"), str(playlist)]) == 0
    assert plays == ["ahead", "plays", "back"]


def test_a_funestra_named_no_list_ends_at_once_saying_so(plays, caplog):
    assert program_app.main([]) == 1
    assert "No videos to play" in caplog.text
    assert plays == []


def test_a_funestra_launched_on_an_empty_list_opens_and_plays_the_list_once_it_is_written(
        tmp_path):
    args = _loop_args(tmp_path, [])
    video = _videos(tmp_path, "v0")[0]
    fake = _FakePygame()
    looked = []

    def the_app_writes_the_list_after_a_while():
        looked.append("looked")
        if len(looked) == 3:
            (tmp_path / "playlist.tsv").write_text(f"{video}\n", encoding="utf-8")
        return []

    fake.event.get = the_app_writes_the_list_after_a_while

    with patch("funestra.program.app.time.sleep"):
        code, opens, _fake = _run_loop(tmp_path, args, fake=fake)

    assert code == 0
    assert [item.path for item in opens.asked[1].playlist] == [video]


def test_a_funestra_still_waiting_for_its_list_ends_when_told_to_quit(tmp_path):
    args = _loop_args(tmp_path, [])
    (tmp_path / "cmd.txt").write_text("QUIT\n", encoding="utf-8")

    code, opens, fake = _run_loop(tmp_path, args)

    assert code == 0
    assert opens.asked is None
    assert fake.quit_called


def test_a_funestra_opens_where_the_launch_placed_it(tmp_path):
    try:
        _run_loop(tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0"), x="-1200", y="40"))

        assert os.environ["SDL_VIDEO_WINDOW_POS"] == "-1200,40"
    finally:
        os.environ.pop("SDL_VIDEO_WINDOW_POS", None)


def test_a_funestra_takes_its_taskbar_identity_before_its_window_exists(tmp_path):
    order = []
    fake = _FakePygame()
    fake.init = lambda: order.append("window")

    _run_loop(tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0"), taskbar_identity="Made.Up"),
              fake=fake, claim_identity=order.append)

    assert order == ["Made.Up", "window"]


def test_a_funestras_window_wears_the_sessions_taskbar_button_once_it_exists(tmp_path):
    order = []
    fake = _FakePygame()
    fake.display.set_mode = lambda *_a, **_kw: order.append("window")

    _run_loop(tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0"), taskbar_identity="Made.Up"),
              fake=fake, claim_identity=lambda _identity: None,
              wear_button=lambda *worn: order.append(worn))

    assert order == ["window", (4242, "Made.Up")]


def test_a_refused_taskbar_identity_never_costs_the_funestra_its_start(tmp_path):
    def refuse(_identity):
        raise OSError("refused")

    code, opens, _fake = _run_loop(
        tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0"), taskbar_identity="Made.Up"),
        claim_identity=refuse)

    assert code == 0
    assert opens.asked is not None


def test_a_funestra_asked_to_open_hidden_opens_a_window_nobody_sees_yet(tmp_path):
    fake = _FakePygame()
    opened_with = []
    fake.display.set_mode = lambda _size, flags: opened_with.append(flags)

    _run_loop(tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0"), hidden=True), fake=fake)
    _run_loop(tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0")), fake=fake)

    assert opened_with == [fake.NOFRAME | fake.HIDDEN, fake.NOFRAME]


def test_the_window_answers_the_verbs_about_itself(tmp_path):
    _code, opens, _fake = _run_loop(tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0")))

    assert isinstance(opens.asked[1].window_verbs, WindowVerbs)


def _key(key, mod=0):
    return SimpleNamespace(type=_FakePygame.KEYDOWN, key=key, mod=mod)


_FakePygame.KEYDOWN = 768


def test_a_funestra_asked_for_its_keys_tells_the_app_each_one_pressed_on_it(tmp_path):
    asks = tmp_path / "asks.txt"
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"), keys=True, dashboard_cmd_file=str(asks))
    fake = _FakePygame(event_batches=[[_key(pygame.K_LEFT, pygame.KMOD_LSHIFT), _key(pygame.K_RETURN)]])

    _run_loop(tmp_path, args, fake=fake)

    assert asks.read_text(encoding="utf-8").split() == ["key|left|shift", "key|return|"]


def test_a_funestra_not_asked_for_its_keys_keeps_them_to_itself(tmp_path):
    asks = tmp_path / "asks.txt"
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"), dashboard_cmd_file=str(asks))

    _run_loop(tmp_path, args, fake=_FakePygame(event_batches=[[_key(pygame.K_LEFT)]]))

    assert not asks.exists()


def test_a_funestra_ends_once_the_app_it_was_started_for_has_gone(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"), ends_with="4321")
    asked_after = []

    def gone(pid):
        asked_after.append(pid)
        return False

    _code, opens, _fake = _run_loop(tmp_path, args, passes=50, host_is_running=gone)

    assert opens.funestra.applied == [QUIT]
    assert asked_after == [4321]


def test_a_funestra_whose_app_is_still_there_plays_on(tmp_path):
    args = _loop_args(tmp_path, _videos(tmp_path, "v0"), ends_with="4321")

    _code, opens, _fake = _run_loop(tmp_path, args, passes=3, host_is_running=lambda _pid: True)

    assert opens.funestra.applied == []
    assert len(opens.funestra.ticks) == 3


def test_a_funestra_started_for_no_app_asks_after_nobody(tmp_path):
    def never(_pid):
        raise AssertionError("asked after an app it was not started for")

    _code, opens, _fake = _run_loop(tmp_path, _loop_args(tmp_path, _videos(tmp_path, "v0")),
                                    passes=3, host_is_running=never)

    assert len(opens.funestra.ticks) == 3


def test_a_funestra_still_waiting_for_its_list_ends_once_its_app_has_gone(tmp_path):
    args = _loop_args(tmp_path, [], ends_with="4321")

    code, opens, fake = _run_loop(tmp_path, args, host_is_running=lambda _pid: False)

    assert (code, opens.asked, fake.quit_called) == (0, None, True)
