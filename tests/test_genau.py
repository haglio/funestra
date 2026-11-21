from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pytest
from app_support import haglio_settings

from funestra import genau_engine
from funestra.flick_folder import scan_flicks
from funestra.genau import Genau, GenauOutputs, Narrow, Opening
from funestra.genau_engine import EngineSeams, GenauChannels
from funestra.genau_refresh import SEND_THREAD
from funestra.genau_settings import GenauSettings
from funestra.main_hud import ModeHud
from funestra.modes import MessageLevel
from funestra.off_the_loop import AtOnce
from funestra.runs_here import User
from funestra.testing import (
    FakeNotifier,
    FakeSink,
    HeldDecodes,
    ThreadsAsked,
    every_thread_now_but_the_ones_that_run_for_good,
)

KEEP_ONLY = "KEEP_ONLY"


class FolderTrash:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.went_to: list[tuple[Path, Path]] = []

    def folder_for(self, _flick: Path) -> Path:
        return self.folder

    def went(self, flick: Path, landed: Path) -> None:
        self.went_to.append((flick, landed))


class ListedFlicks:
    metadata_root = None
    flips = None
    keep_shapes = None

    def __init__(self, folder: Path, trash: Path) -> None:
        self.folder = folder
        self.trash: FolderTrash | None = FolderTrash(trash)
        self.kept: str | None = None
        self.arriving: list[Path] = []
        self.asked_for_arrivals: list[tuple[bool, bool]] = []

    def opening(self, *, recent: bool, shuffled: bool) -> Opening:
        listed = self.listed(recent=recent, shuffled=shuffled)
        return Opening(listed or scan_flicks(self.folder, shuffle_on_load=shuffled, recent=recent),
                       none_kept=not listed)

    def listed(self, *, recent: bool, shuffled: bool) -> list[Path]:
        every = scan_flicks(self.folder, shuffle_on_load=shuffled, recent=recent)
        return [flick for flick in every if self.kept is None or flick.stem.startswith(self.kept)]

    def name_of(self, flick: Path) -> str:
        return flick.stem.title()

    def up_next(self, *, recent: bool, showing: bool) -> list[Path]:
        self.asked_for_arrivals.append((recent, showing))
        arrived, self.arriving = self.arriving, []
        return arrived

    def apply_command(self, command: str, narrow: Narrow) -> bool:
        verb, _, kept = command.partition(" ")
        if verb != KEEP_ONLY:
            return False
        self.kept = kept
        narrow(f"Only {kept}")
        return True


class ShapedFlicks(ListedFlicks):
    def __init__(self, folder: Path, trash: Path) -> None:
        super().__init__(folder, trash)
        self.shapes: list[tuple[bool, bool]] = []

    def keep_shapes(self, plays_vr: bool, plays_flat: bool) -> None:
        self.shapes.append((plays_vr, plays_flat))
        self.kept = "gamma" if plays_flat else None


class FakeMessages:
    def __init__(self) -> None:
        self.said: list[tuple[str, MessageLevel]] = []

    def say(self, message: str, *, level: MessageLevel) -> None:
        self.said.append((message, level))


class Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _frames(count: int = 8, width: int = 16, height: int = 8) -> list[np.ndarray]:
    return [np.full((height, width, 3), i, dtype=np.uint8) for i in range(count)]


class _CondemningInTheBackground:
    def __init__(self) -> None:
        self.threads: list[threading.Thread] = []

    def __call__(self, *, target, args=(), name=""):
        if name != "genau-condemn":
            every_thread_now_but_the_ones_that_run_for_good(target=target, args=args, name=name)
            return
        thread = threading.Thread(target=target, args=args, name=name)
        self.threads.append(thread)
        thread.start()


class _CondemningWhenTold:
    def __init__(self) -> None:
        self.waiting: list = []

    def __call__(self, *, target, args=(), name=""):
        if name != "genau-condemn":
            every_thread_now_but_the_ones_that_run_for_good(target=target, args=args, name=name)
            return
        self.waiting.append(lambda: target(*args))


@dataclass(frozen=True)
class WorldSetup:
    flicks: tuple = ("alpha one.mp4", "beta two.mp4", "gamma three.mp4")
    kept: str | None = None
    start_flick: str | None = None
    latest: bool = False
    shapes: bool = False
    has_trash: bool = True
    has_arrivals: bool = True
    sleeps_on_its_own_clock: bool = False
    start_thread: Callable = every_thread_now_but_the_ones_that_run_for_good
    off_the_loop: Callable = AtOnce


class World:
    def __init__(self, tmp_path: Path, setup: WorldSetup | None = None) -> None:
        setup = setup or WorldSetup()
        self.folder = tmp_path / "flicks"
        self.folder.mkdir()
        for arrived, name in enumerate(setup.flicks, start=1):
            flick = self.folder / name
            flick.write_bytes(b"flick")
            os.utime(flick, (1_000_000_000 + arrived, 1_000_000_000 + arrived))
        self.trash = tmp_path / "trash"
        self.source = (ShapedFlicks if setup.shapes else ListedFlicks)(self.folder, self.trash)
        self.source.kept = setup.kept
        if not setup.has_trash:
            self.source.trash = None
        if not setup.has_arrivals:
            self.source.up_next = None
        state = tmp_path / "state"
        state.mkdir()
        self.channels = GenauChannels(
            command=state / "genau_cmd.txt", paused=state / "genau_paused.txt",
            status=state / "genau_status.txt", drive=state / "genau_drive.txt")
        self.sink = FakeSink()
        self.notifier = FakeNotifier()
        self.messages = FakeMessages()
        self.clock = Clock()
        seams = EngineSeams(
            decode=lambda _path: _frames(),
            start_thread=setup.start_thread,
            clock=self.clock,
            log=logging.getLogger("test.genau"),
            off_the_loop=setup.off_the_loop,
        )
        self.genau = Genau(
            self.source,
            settings=GenauSettings(shuffle_on_load=False),
            channels=self.channels,
            outputs=GenauOutputs(notifier=self.notifier, tcode_sink=self.sink,
                                 messages=self.messages),
            start_flick=None if setup.start_flick is None else self.folder / setup.start_flick,
            latest=setup.latest,
            seams=replace(seams, sleep=self.clock.sleep) if setup.sleeps_on_its_own_clock else seams,
        )

    def send(self, line: str) -> None:
        self.channels.command.write_text(line + "\n", encoding="utf-8")
        self.genau.tick()
        self.genau.tick()

    def tick(self, seconds: float = 0.05) -> None:
        self.clock.now += seconds
        self.genau.tick()

    def beat_of_the_send_clock(self, seconds: float = 1 / 30) -> None:
        self.clock.now += seconds
        self.genau.send_between_passes(self.clock.now)

    def status(self) -> dict[str, str]:
        lines = self.channels.status.read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines if "=" in line)

    def shown(self, steps: int = 3) -> list[str]:
        shown = []
        for _step in range(steps):
            shown.append(self.genau.top_block().video)
            self.send("NEXT")
        return shown


@pytest.fixture
def the_rooms_word_is_pips(tmp_path_factory, monkeypatch):
    settings = tmp_path_factory.mktemp("haglio") / "settings.json"
    settings.write_text(json.dumps({"genau_flick_words": {"one": "pip", "many": "pips"}}),
                        encoding="utf-8")
    monkeypatch.setenv(haglio_settings.SETTINGS_ENV, str(settings))


def test_genau_is_a_thing_a_funestra_runs(tmp_path):
    assert isinstance(World(tmp_path).genau, User)


class HandsWritesOn(AtOnce):
    def __init__(self) -> None:
        self.published: list[Path] = []
        self.closed = False

    def publish(self, path: Path, text: str) -> bool:
        self.published.append(path)
        return super().publish(path, text)

    def close(self) -> None:
        self.closed = True


def test_genaus_drive_file_is_written_by_the_worker_behind_the_loop(tmp_path):
    worker = HandsWritesOn()
    world = World(tmp_path, WorldSetup(off_the_loop=lambda: worker))

    world.tick()
    world.genau.close()

    assert world.channels.drive in worker.published
    assert worker.closed


class TestTheFlickOnScreen:
    def test_it_opens_on_the_first_flick_its_source_lists_and_tells_the_audio_companion(
            self, tmp_path):
        world = World(tmp_path)

        assert world.genau.top_block() == ModeHud(video="Alpha One")
        assert world.notifier.flicks == [world.folder / "alpha one.mp4"]

    def test_it_opens_on_the_flick_it_is_asked_to_start_at(self, tmp_path):
        world = World(tmp_path, WorldSetup(start_flick="beta two.mp4"))

        assert world.genau.top_block() == ModeHud(video="Beta Two")

    def test_its_verbs_arrive_on_its_own_channel_and_never_on_the_funestras(self, tmp_path):
        world = World(tmp_path)

        assert world.genau.apply_command("NEXT") is False
        world.send("NEXT")

        assert world.genau.top_block() == ModeHud(video="Beta Two")

    def test_while_it_has_the_window_a_step_on_the_funestras_channel_steps_its_flicks(
            self, tmp_path):
        world = World(tmp_path)
        world.genau.set_showing(True)

        assert world.genau.apply_command("NEXT 12.500") is True
        world.tick()

        assert world.genau.top_block() == ModeHud(video="Beta Two")

    def test_it_publishes_its_own_status_and_adds_no_line_to_the_funestras(self, tmp_path):
        world = World(tmp_path)

        world.tick()

        assert world.status()["flick"] == str(world.folder / "alpha one.mp4")
        assert world.genau.status_fields() == {}

    def test_its_status_says_when_human_inspired_motion_has_the_hand_and_nothing_of_cruise(
            self, tmp_path):
        world = World(tmp_path)

        world.send("LEARNED_ON")

        assert world.status()["learned"] == "1"
        assert "cruise" not in world.status()

    def test_latest_asks_its_source_for_the_flicks_newest_first(self, tmp_path):
        world = World(tmp_path)
        newest = world.folder / "delta four.mp4"
        newest.write_bytes(b"flick")
        os.utime(newest, (4_000_000_000, 4_000_000_000))

        world.send("LATEST")

        assert world.genau.top_block() == ModeHud(video="Delta Four")


class TestTrash:
    def test_trash_moves_the_flick_where_its_source_says_and_shows_the_next(self, tmp_path):
        world = World(tmp_path)

        world.send("TRASH")

        assert (world.trash / "alpha one.mp4").is_file()
        assert world.genau.top_block() == ModeHud(video="Beta Two")

    def test_trash_moves_the_file_off_the_window_s_pass_since_a_move_in_the_library_can_take_long(
            self, tmp_path):
        condemning = _CondemningWhenTold()
        world = World(tmp_path, WorldSetup(start_thread=condemning))
        flick = world.folder / "alpha one.mp4"

        world.send("TRASH")
        up_next, still_there = world.genau.top_block(), flick.is_file()
        for job in condemning.waiting:
            job()

        assert (up_next, still_there) == (ModeHud(video="Beta Two"), True)
        assert len(condemning.waiting) == 1
        assert (world.trash / "alpha one.mp4").is_file()

    def test_trash_moves_a_flick_still_being_read_once_it_is_let_go(self, tmp_path):
        condemning = _CondemningInTheBackground()
        world = World(tmp_path, WorldSetup(start_thread=condemning))
        flick = world.folder / "alpha one.mp4"

        with flick.open("rb"):
            world.send("TRASH")
            assert flick.is_file()
        for thread in condemning.threads:
            thread.join()

        assert (world.trash / "alpha one.mp4").is_file()
        assert not flick.exists()

    def test_trash_tells_its_source_where_the_flick_went(self, tmp_path):
        world = World(tmp_path)

        world.send("TRASH")

        assert world.source.trash.went_to == [(world.folder / "alpha one.mp4",
                                         world.trash / "alpha one.mp4")]

    def test_trash_tells_its_source_of_a_flick_still_being_read_once_it_is_let_go(self, tmp_path):
        condemning = _CondemningInTheBackground()
        world = World(tmp_path, WorldSetup(start_thread=condemning))

        with (world.folder / "alpha one.mp4").open("rb"):
            world.send("TRASH")
            told_while_open = list(world.source.trash.went_to)
        for thread in condemning.threads:
            thread.join()

        assert told_while_open == []
        assert len(world.source.trash.went_to) == 1

    def test_trash_gives_up_on_a_flick_that_stays_open_and_says_so(self, tmp_path, caplog):
        condemning = _CondemningInTheBackground()
        world = World(tmp_path, WorldSetup(start_thread=condemning, sleeps_on_its_own_clock=True))
        flick = world.folder / "alpha one.mp4"

        with flick.open("rb"), caplog.at_level(logging.ERROR, logger="test.genau"):
            world.send("TRASH")
            for thread in condemning.threads:
                thread.join()

        assert flick.is_file()
        assert f"alpha one.mp4 was still open after {genau_engine.CONDEMN_PATIENCE_S:g}s" in caplog.text


    def test_from_a_source_with_no_trash_the_flick_stays_where_it_is(self, tmp_path):
        world = World(tmp_path, WorldSetup(has_trash=False))

        world.send("TRASH")

        assert (world.folder / "alpha one.mp4").is_file()
        assert world.genau.top_block() == ModeHud(video="Alpha One")


class TestWhatItsSourcePutsUpNext:
    def test_from_a_source_where_nothing_arrives_it_steps_through_what_the_source_lists(
            self, tmp_path):
        world = World(tmp_path, WorldSetup(has_arrivals=False))
        world.genau.set_showing(True)

        world.tick()
        world.send("NEXT")

        assert world.genau.top_block().video == "Beta Two"

    def test_it_comes_up_after_the_flick_on_screen(self, tmp_path):
        world = World(tmp_path)
        world.genau.set_showing(True)

        world.source.arriving = [world.folder / "gamma three.mp4"]
        world.tick()
        world.send("NEXT")

        assert world.genau.top_block().video == "Gamma Three"

    def test_its_source_is_asked_at_once_and_on_every_pass_whether_it_browses_latest_and_has_the_window(
            self, tmp_path):
        world = World(tmp_path, WorldSetup(latest=True))
        world.genau.set_showing(True)

        world.tick()

        assert world.source.asked_for_arrivals == [(True, False), (True, True)]


class TestItsSourcesOwnVerbs:
    def test_a_verb_its_source_answers_narrows_to_what_the_source_lists_then(self, tmp_path):
        world = World(tmp_path)

        assert world.genau.apply_command(f"{KEEP_ONLY} gamma") is True

        assert set(world.shown()) == {"Gamma Three"}
        assert world.messages.said[-1] == ("Only gamma", MessageLevel.NORMAL)

    def test_a_verb_no_one_answers_is_not_answered(self, tmp_path):
        assert World(tmp_path).genau.apply_command("SOMETHING_ELSE") is False

    def test_a_narrowing_that_leaves_none_holds_the_flick_on_screen_and_says_so(
            self, tmp_path, the_rooms_word_is_pips):
        world = World(tmp_path)
        world.send("LOCK_OFF")

        world.genau.apply_command(f"{KEEP_ONLY} omega")
        world.tick()

        assert world.genau.top_block().video == "Alpha One"
        assert world.status()["locked"] == "1"
        assert world.messages.said == [("Including no other pips", MessageLevel.WARNING)]

    def test_opening_with_none_kept_holds_the_first_flick_and_says_so(
            self, tmp_path, the_rooms_word_is_pips):
        world = World(tmp_path, WorldSetup(kept="omega"))
        world.tick()

        assert world.genau.top_block().video == "Alpha One"
        assert world.status()["locked"] == "1"
        assert world.messages.said == [("Including no other pips", MessageLevel.WARNING)]


class TestShapes:
    def test_a_source_that_keeps_shapes_is_told_the_shape_kept_and_narrowed_to_it(self, tmp_path):
        world = World(tmp_path, WorldSetup(shapes=True))

        world.send("SHAPES flat")

        assert world.source.shapes == [(False, True)]
        assert set(world.shown()) == {"Gamma Three"}
        assert world.messages.said[-1] == ("2D only", MessageLevel.NORMAL)

    def test_a_source_that_keeps_no_shapes_leaves_the_flicks_as_they_are(self, tmp_path):
        world = World(tmp_path)

        world.send("SHAPES flat")

        assert world.shown() == ["Alpha One", "Beta Two", "Gamma Three"]


class TestItsFrame:
    def test_the_frame_the_motion_chose_is_the_frame_counted_up(self, tmp_path):
        world = World(tmp_path)
        world.send("RESUME")
        shown = set()
        for _ in range(40):
            world.tick(0.05)
            flick_frame = world.genau.own_frame()
            if flick_frame.frame is not None:
                shown.add(int(flick_frame.frame[0, 0, 0]))
                assert flick_frame.count == 8
                assert 0 <= flick_frame.played < 8

        assert len(shown) > 1

    def test_a_press_on_its_dial_moves_the_device(self, tmp_path):
        world = World(tmp_path)
        world.send("RESUME")
        world.tick(0.05)
        sent_before = len(world.sink.sent)

        world.genau.own_frame().seek_loop(0.5)
        world.tick(0.05)
        world.beat_of_the_send_clock()

        assert len(world.sink.sent) > sent_before

    def test_the_osr2_s_positions_go_out_on_a_thread_of_their_own_and_no_pass_of_the_window_sends_one(
            self, tmp_path):
        threads = ThreadsAsked()
        world = World(tmp_path, WorldSetup(start_thread=threads))
        world.send("RESUME")

        for _pass in range(4):
            world.tick(0.016)
        sent_by_the_passes = list(world.sink.sent)
        for _beat in range(3):
            world.beat_of_the_send_clock()

        assert threads.named.count(SEND_THREAD) == 1
        assert sent_by_the_passes == []
        assert len(world.sink.sent) == 3

    def test_the_frame_carries_every_frame_of_its_flick_so_the_window_can_scale_them_ahead(
            self, tmp_path):
        world = World(tmp_path)
        world.tick(0.05)

        first, again = world.genau.own_frame(), world.genau.own_frame()

        assert len(first.frames) == 8
        assert any(frame is first.frame for frame in first.frames)
        assert again.frames is first.frames

    def test_the_frame_carries_the_flicks_time_on_screen(self, tmp_path):
        world = World(tmp_path)
        world.tick(0.05)

        flick_frame = world.genau.own_frame()

        assert (flick_frame.elapsed_ms, flick_frame.interval_ms) == (0.0, 10_000.0)

    def test_a_press_along_its_track_puts_the_flick_that_far_into_its_time(self, tmp_path):
        world = World(tmp_path)
        world.tick(0.05)

        world.genau.own_frame().seek_time(7_000.0)

        assert world.genau.own_frame().elapsed_ms == 7_000.0

    def test_nothing_still_decoding_is_said_on_the_frame_once_it_has_decoded(self, tmp_path):
        world = World(tmp_path)

        assert world.genau.own_frame().loading is None
        assert world.genau.loading is None

    def test_the_flick_still_decoding_is_named_while_the_last_stays_up(self, tmp_path):
        decodes = HeldDecodes()
        world = World(tmp_path, WorldSetup(start_thread=decodes))
        world.tick()
        decodes.holding = True
        world.send("NEXT")

        world.send("NEXT")

        assert world.genau.top_block() == ModeHud(video="Beta Two")
        assert world.genau.loading == world.genau.own_frame().loading == "Loading gamma three.mp4"


class TestWhoHasTheWindow:
    def test_shown_it_tells_the_audio_companion_it_is_visible_and_hidden_that_it_is_not(
            self, tmp_path):
        world = World(tmp_path)

        world.genau.set_showing(True)
        world.tick()
        world.genau.set_showing(False)
        world.tick()

        assert world.notifier.visible[-2:] == [True, False]


def test_closing_it_closes_the_device_line_and_the_audio_companion(tmp_path):
    world = World(tmp_path)

    world.genau.close()

    assert (world.sink.closed, world.notifier.closed) == (True, True)


def test_it_answers_the_apps_volume_though_it_draws_no_volume_control_since_an_unanswered_verb_is_logged_each_time_the_volume_moves(
        tmp_path, caplog):
    world = World(tmp_path)

    with caplog.at_level(logging.WARNING):
        world.send("SET_VOLUME 70 1")

    assert [record.getMessage() for record in caplog.records
            if record.levelno >= logging.WARNING] == []
