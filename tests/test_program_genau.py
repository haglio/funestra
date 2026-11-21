from __future__ import annotations

from pathlib import Path

import numpy as np

from funestra.flick_list import RELOAD_FLICKS
from funestra.flick_overlay import BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID
from funestra.funestra import Channels, Funestra
from funestra.funestra_setup import FunestraSetup
from funestra.funestra_verbs import RELOAD_PLAYLIST
from funestra.genau_engine import EngineSeams
from funestra.hud_kinds import HudFacts, HudKind
from funestra.modes import MainMode
from funestra.off_the_loop import AtOnce
from funestra.playlist import PlaylistItem, read_playlist, write_playlist
from funestra.program.genau_here import kino_and_genau
from funestra.program.genau_launch import GenauLaunch
from funestra.satellite_hud import HudModel, hud_text
from funestra.testing import FakeEngine, every_thread_now_but_the_ones_that_run_for_good

VIEWPORT = (320, 240)


class Standalone:
    def __init__(self, tmp_path: Path, *, hud: bool = False, playing: int = 3) -> None:
        self.command = tmp_path / "cmd.txt"
        self.playlist = tmp_path / "playlist.tsv"
        self.status = tmp_path / "status.txt"
        self.flicks = tmp_path / "genau_flicks.tsv"
        self.slides = [tmp_path / f"slide {index}.mp4" for index in range(3)]
        write_playlist(self.playlist, [PlaylistItem(slide) for slide in self.slides[:playing]])
        self.engine = FakeEngine()
        launch = GenauLaunch(
            command=tmp_path / "genau_cmd.txt", paused=tmp_path / "genau_paused.txt",
            status=tmp_path / "genau_status.txt", drive=tmp_path / "genau_drive.txt",
            flicks=self.flicks, beat_port=50601)
        self.funestra = Funestra(self.engine, FunestraSetup(
            channels=Channels(command=self.command, playlist=self.playlist, status=self.status,
                              **self._huds(tmp_path) if hud else {}),
            playlist=read_playlist(self.playlist),
            users=kino_and_genau(launch, notice=None, seams=EngineSeams(
                decode=lambda _path: [np.zeros((8, 16, 3), dtype=np.uint8)] * 4,
                start_thread=every_thread_now_but_the_ones_that_run_for_good,
                off_the_loop=AtOnce))))

    @staticmethod
    def _huds(tmp_path: Path) -> dict[str, Path]:
        hud = tmp_path / "hud.json"
        hud.write_text(hud_text(HudModel(funestra="portrait", kind=HudKind.SLIDESHOW,
                                         facts=HudFacts(funestra="portrait",
                                                        main_mode=MainMode.GENAU))),
                       encoding="utf-8")
        return {"hud": hud, "dashboard_cmd": tmp_path / "asks.txt"}

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


def test_with_genau_shown_the_huds_row_runs_through_genaus_flick(tmp_path):
    standalone = Standalone(tmp_path, hud=True)
    standalone.write_flicks("alpha")

    standalone.send(RELOAD_FLICKS, "SHOW genau")

    assert standalone.funestra.hud.scrubber_row.loop[1] == 4


def test_back_in_kino_the_huds_row_runs_through_the_item_again(tmp_path):
    standalone = Standalone(tmp_path, hud=True)
    standalone.write_flicks("alpha")
    standalone.send(RELOAD_FLICKS, "SHOW genau")

    standalone.send("SHOW kino")

    assert standalone.funestra.hud.scrubber_row == standalone.funestra.scrubber_row()


class TestStartedOnNoPlaylist:
    def test_kino_plays_nothing_and_covers_the_window_in_black(self, tmp_path):
        standalone = Standalone(tmp_path, hud=True, playing=0)

        standalone.send("NEXT", "PREV")

        assert standalone.engine.opened == []
        assert BACKDROP_OVERLAY_ID in standalone.engine.overlays

    def test_it_says_nothing_of_an_item_while_it_has_none(self, tmp_path):
        standalone = Standalone(tmp_path, playing=0)

        standalone.send("NEXT")

        assert not standalone.status.exists()

    def test_kino_plays_the_list_once_the_app_writes_it_and_reloads(self, tmp_path):
        standalone = Standalone(tmp_path, hud=True, playing=0)
        standalone.send("NEXT")

        write_playlist(standalone.playlist, [PlaylistItem(slide) for slide in standalone.slides])
        standalone.send(RELOAD_PLAYLIST)

        assert standalone.engine.opened == [standalone.slides[0]]
        assert BACKDROP_OVERLAY_ID not in standalone.engine.overlays
        assert standalone.status.exists()

    def test_genau_plays_its_flicks_over_it(self, tmp_path):
        standalone = Standalone(tmp_path, hud=True, playing=0)
        standalone.write_flicks("alpha")

        standalone.send(RELOAD_FLICKS, "SHOW genau")

        assert standalone.genaus_frame_is_up
