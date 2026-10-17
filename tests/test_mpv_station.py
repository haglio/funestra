"""A radio station: library clips' sound alone, round and round, heard only while it is tuned in."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from funestra import mpv_engine
from funestra.mpv_engine import MpvStation


class FakeStationMpv:
    def __init__(self, **options) -> None:
        self.options = options
        self.loaded: list[tuple[str, str]] = []
        self.set: list[tuple[str, object]] = []
        self.terminated = 0

    def loadfile(self, path: str, mode: str) -> None:
        self.loaded.append((path, mode))

    def terminate(self) -> None:
        self.terminated += 1

    def __setattr__(self, name: str, value) -> None:
        if name not in {"options", "loaded", "set", "terminated"}:
            self.set.append((name, value))
        super().__setattr__(name, value)


CLIPS = [Path("alpha one.mp4"), Path("alpha two.mp4"), Path("beta.mp4")]


def opened(monkeypatch, clips=CLIPS, **station_args) -> tuple[MpvStation, FakeStationMpv]:
    handles: list[FakeStationMpv] = []

    def open_mpv(**options):
        handles.append(FakeStationMpv(**options))
        return handles[-1]

    monkeypatch.setattr(mpv_engine, "_import_mpv", lambda: SimpleNamespace(MPV=open_mpv))
    station = MpvStation.opened(clips, **station_args)
    return station, handles[0]


def test_a_station_opens_mpv_for_sound_alone_round_and_round_in_a_fresh_order(monkeypatch):
    _station, mpv = opened(monkeypatch)

    assert {name: mpv.options[name] for name in (
        "vid", "vo", "audio_display", "loop_playlist", "shuffle", "mute")} == {
        "vid": "no", "vo": "null", "audio_display": "no", "loop_playlist": "inf",
        "shuffle": "yes", "mute": "yes"}


def test_a_station_puts_its_clips_up_as_one_list_from_the_first(monkeypatch):
    _station, mpv = opened(monkeypatch)

    assert mpv.loaded == [("alpha one.mp4", "replace"), ("alpha two.mp4", "append"),
                          ("beta.mp4", "append")]


def test_a_station_tuned_in_is_heard_at_the_level_it_is_handed_and_tuned_out_is_not(monkeypatch):
    station, mpv = opened(monkeypatch)

    station.tune(60)
    assert mpv.set == [("volume", 60), ("mute", False)]
    station.tune(None)
    assert mpv.set[-1] == ("mute", True)


def test_a_station_tuned_to_where_it_already_is_asks_mpv_for_nothing(monkeypatch):
    station, mpv = opened(monkeypatch)
    station.tune(60)
    asked = list(mpv.set)

    station.tune(60)

    assert mpv.set == asked


def test_a_station_out_of_earshot_from_the_start_asks_mpv_for_nothing_to_stay_there(monkeypatch):
    station, mpv = opened(monkeypatch)

    station.tune(None)

    assert mpv.set == []


def test_a_station_holds_still_with_the_room_and_goes_on_after(monkeypatch):
    station, mpv = opened(monkeypatch)

    station.set_paused(True)
    station.set_paused(True)
    station.set_paused(False)

    assert mpv.set == [("pause", True), ("pause", False)]


def test_a_closed_station_lets_mpv_go(monkeypatch):
    station, mpv = opened(monkeypatch)

    station.close()

    assert mpv.terminated == 1
