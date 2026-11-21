from __future__ import annotations

from pathlib import Path

import numpy as np

from funestra.flick_list import RELOAD_FLICKS
from funestra.flick_overlay import BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID
from funestra.funestra import Channels, Funestra
from funestra.funestra_setup import FunestraSetup
from funestra.genau_engine import EngineSeams
from funestra.modes import MainMode
from funestra.off_the_loop import AtOnce
from funestra.playlist import PlaylistItem, write_playlist
from funestra.program.genau_here import GenauLaunch, kino_and_genau
from funestra.testing import FakeEngine, every_thread_now_but_the_ones_that_run_for_good

VIEWPORT = (320, 240)


class Standalone:
    def __init__(self, tmp_path: Path) -> None:
        self.command = tmp_path / "cmd.txt"
        self.flicks = tmp_path / "genau_flicks.tsv"
        self.slides = [tmp_path / f"slide {index}.mp4" for index in range(3)]
        self.engine = FakeEngine()
        launch = GenauLaunch(
            command=tmp_path / "genau_cmd.txt", paused=tmp_path / "genau_paused.txt",
            status=tmp_path / "genau_status.txt", drive=tmp_path / "genau_drive.txt",
            flicks=self.flicks, beat_port=50601)
        self.funestra = Funestra(self.engine, FunestraSetup(
            channels=Channels(command=self.command),
            playlist=[PlaylistItem(slide) for slide in self.slides],
            users=kino_and_genau(launch, notice=None, seams=EngineSeams(
                decode=lambda _path: [np.zeros((8, 16, 3), dtype=np.uint8)] * 4,
                start_thread=every_thread_now_but_the_ones_that_run_for_good,
                off_the_loop=AtOnce))))

    def send(self, *lines: str) -> None:
        self.command.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        self.funestra.tick(viewport=VIEWPORT)
        self.funestra.tick(viewport=VIEWPORT)

    def write_flicks(self, *names: str) -> None:
        write_playlist(self.flicks, [PlaylistItem(Path(f"C:/example/flicks/{name}.mp4"))
                                     for name in names])

    @property
    def genaus_frame_is_up(self) -> bool:
        return FIRST_TILE_OVERLAY_ID in self.engine.overlays


def test_it_opens_on_kino_playing_its_list(tmp_path):
    standalone = Standalone(tmp_path)

    standalone.send("NEXT")

    assert standalone.funestra.showing == MainMode.KINO
    assert standalone.funestra.playback.current_video == standalone.slides[1]
    assert not standalone.genaus_frame_is_up


def test_show_genau_puts_genaus_frame_over_the_window(tmp_path):
    standalone = Standalone(tmp_path)
    standalone.write_flicks("alpha", "beta")

    standalone.send(RELOAD_FLICKS, "SHOW genau")

    assert standalone.funestra.showing == MainMode.GENAU
    assert standalone.genaus_frame_is_up


def test_show_kino_takes_genaus_frame_down_and_finds_the_list_where_it_was_left(tmp_path):
    standalone = Standalone(tmp_path)
    standalone.write_flicks("alpha", "beta")
    standalone.send("NEXT", RELOAD_FLICKS, "SHOW genau")

    standalone.send("NEXT", "SHOW kino")

    assert standalone.funestra.playback.current_video == standalone.slides[1]
    assert not standalone.genaus_frame_is_up
    assert BACKDROP_OVERLAY_ID not in standalone.engine.overlays


def test_genau_shown_before_the_app_wrote_any_flicks_covers_the_window_in_black(tmp_path):
    standalone = Standalone(tmp_path)

    standalone.send("SHOW genau")

    assert BACKDROP_OVERLAY_ID in standalone.engine.overlays
    assert not standalone.genaus_frame_is_up


def test_a_step_while_genau_shows_and_has_no_flicks_leaves_the_list_where_it_was(tmp_path):
    standalone = Standalone(tmp_path)
    standalone.send("SHOW genau")

    standalone.send("NEXT", "SHOW kino")

    assert standalone.funestra.playback.current_video == standalone.slides[0]


def test_genau_shown_with_no_flicks_puts_up_its_first_once_the_app_writes_them(tmp_path):
    standalone = Standalone(tmp_path)
    standalone.send("SHOW genau")

    standalone.write_flicks("alpha")
    standalone.send(RELOAD_FLICKS)

    assert standalone.genaus_frame_is_up
