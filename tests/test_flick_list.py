from __future__ import annotations

from pathlib import Path

import numpy as np

from funestra.flick_list import RELOAD_FLICKS, FlickList, GenauOnAList
from funestra.genau import Genau, GenauOutputs, Opening
from funestra.genau_engine import EngineSeams, GenauChannels
from funestra.genau_settings import GenauSettings
from funestra.main_hud import ModeHud
from funestra.off_the_loop import AtOnce
from funestra.playlist import PlaylistItem, write_playlist
from funestra.runs_here import User
from funestra.testing import FakeNotifier, FakeSink, every_thread_now_but_the_ones_that_run_for_good

ALPHA, BETA, GAMMA = (Path(f"C:/example/flicks/{name}.mp4") for name in ("alpha", "beta", "gamma"))


def _write(file: Path, *flicks: Path) -> None:
    write_playlist(file, [PlaylistItem(flick) for flick in flicks])


def _listed(file: Path, *, recent: bool = True, shuffled: bool = False) -> list[Path]:
    return FlickList(file, shuffle=list.reverse).listed(recent=recent, shuffled=shuffled)


class TestTheFlicksOnItsFile:
    def test_newest_first_they_come_in_the_order_the_app_wrote_them(self, tmp_path):
        _write(tmp_path / "flicks.tsv", BETA, ALPHA, GAMMA)

        assert _listed(tmp_path / "flicks.tsv") == [BETA, ALPHA, GAMMA]

    def test_shuffled_they_come_in_the_order_its_shuffle_leaves(self, tmp_path):
        _write(tmp_path / "flicks.tsv", BETA, ALPHA, GAMMA)

        assert _listed(tmp_path / "flicks.tsv", recent=False, shuffled=True) == [GAMMA, ALPHA, BETA]

    def test_neither_newest_first_nor_shuffled_they_keep_the_order_the_app_wrote(self, tmp_path):
        _write(tmp_path / "flicks.tsv", BETA, ALPHA)

        assert _listed(tmp_path / "flicks.tsv", recent=False) == [BETA, ALPHA]

    def test_a_file_not_written_yet_lists_none(self, tmp_path):
        assert _listed(tmp_path / "flicks.tsv") == []

    def test_it_opens_on_what_it_lists_with_nothing_narrowed_away(self, tmp_path):
        _write(tmp_path / "flicks.tsv", ALPHA)

        assert FlickList(tmp_path / "flicks.tsv").opening(recent=True, shuffled=False) == Opening(
            [ALPHA])

    def test_a_flick_is_named_by_its_file(self, tmp_path):
        assert FlickList(tmp_path / "flicks.tsv").name_of(ALPHA) == "alpha"


class TestItsVerb:
    def test_reloading_narrows_to_the_file_as_rewritten_saying_what_the_app_asked(self, tmp_path):
        narrowed = []

        answered = FlickList(tmp_path / "flicks.tsv").apply_command(
            f"{RELOAD_FLICKS} Portrait only", narrowed.append)

        assert (answered, narrowed) == (True, ["Portrait only"])

    def test_a_verb_of_anything_else_is_not_its(self, tmp_path):
        narrowed = []

        answered = FlickList(tmp_path / "flicks.tsv").apply_command("NEXT", narrowed.append)

        assert (answered, narrowed) == (False, [])


def _frames() -> list[np.ndarray]:
    return [np.zeros((8, 16, 3), dtype=np.uint8) for _ in range(4)]


class Room:
    def __init__(self, tmp_path: Path) -> None:
        self.file = tmp_path / "flicks.tsv"
        self.channels = GenauChannels(
            command=tmp_path / "genau_cmd.txt", paused=tmp_path / "genau_paused.txt",
            status=tmp_path / "genau_status.txt", drive=tmp_path / "genau_drive.txt")
        self.started = 0

    def start(self, flicks: FlickList) -> Genau:
        self.started += 1
        return Genau(flicks, settings=GenauSettings(shuffle_on_load=False), channels=self.channels,
                     outputs=GenauOutputs(notifier=FakeNotifier(), tcode_sink=FakeSink()),
                     latest=True,
                     seams=EngineSeams(decode=lambda _path: _frames(),
                                       start_thread=every_thread_now_but_the_ones_that_run_for_good,
                                       off_the_loop=AtOnce))

    def genau(self) -> GenauOnAList:
        return GenauOnAList(FlickList(self.file), self.start)


class TestGenauOnAList:
    def test_it_is_a_thing_a_funestra_runs(self, tmp_path):
        assert isinstance(Room(tmp_path).genau(), User)

    def test_with_its_list_already_written_it_starts_on_the_first_flick(self, tmp_path):
        room = Room(tmp_path)
        _write(room.file, BETA, ALPHA)

        assert room.genau().top_block() == ModeHud(video="beta")

    def test_with_nothing_listed_it_starts_no_genau_and_shows_no_flick(self, tmp_path):
        room = Room(tmp_path)

        genau = room.genau()
        genau.tick()

        assert (room.started, genau.top_block(), genau.own_frame().frame) == (0, ModeHud(), None)

    def test_a_reload_once_the_list_is_written_starts_genau_on_its_first_flick(self, tmp_path):
        room = Room(tmp_path)
        genau = room.genau()

        _write(room.file, GAMMA, ALPHA)
        answered = genau.apply_command(RELOAD_FLICKS)

        assert (answered, room.started, genau.top_block()) == (True, 1, ModeHud(video="gamma"))

    def test_a_reload_with_the_list_still_empty_starts_nothing(self, tmp_path):
        room = Room(tmp_path)
        genau = room.genau()

        genau.apply_command(RELOAD_FLICKS)

        assert room.started == 0

    def test_shown_before_it_started_genau_starts_with_the_window(self, tmp_path):
        room = Room(tmp_path)
        genau = room.genau()
        genau.set_showing(True)

        _write(room.file, ALPHA, BETA)
        genau.apply_command(RELOAD_FLICKS)
        genau.apply_command("NEXT")
        genau.tick()

        assert genau.top_block() == ModeHud(video="beta")

    def test_once_started_a_reload_narrows_genau_to_the_list_as_rewritten(self, tmp_path):
        room = Room(tmp_path)
        _write(room.file, ALPHA, BETA)
        genau = room.genau()
        genau.set_showing(True)

        _write(room.file, GAMMA)
        genau.apply_command(RELOAD_FLICKS)
        genau.tick()

        assert (room.started, genau.top_block()) == (1, ModeHud(video="gamma"))
