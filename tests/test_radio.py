"""A Funestra's radio: stations of sound playing out of sight, one tuned in while a picture is up."""
from __future__ import annotations

from pathlib import Path

from funestra_fakes import FakeStation

from funestra.radio import Radio, RadioFile, radio_file_for, read_radio, write_radio


def test_a_radio_file_reads_back_the_stations_written_to_it(tmp_path):
    stations = [[tmp_path / "alpha one.mp4", tmp_path / "alpha two.mp4"], [tmp_path / "beta.mp4"]]

    write_radio(tmp_path / "portrait_playlist.radio.tsv", stations)

    assert read_radio(tmp_path / "portrait_playlist.radio.tsv") == stations


def test_a_funestras_radio_file_sits_beside_its_playlist():
    playlist = Path("state") / "portrait_playlist.tsv"

    assert radio_file_for(playlist) == Path("state") / "portrait_playlist.radio.tsv"


def test_a_radio_file_that_is_not_there_is_no_stations(tmp_path):
    assert read_radio(tmp_path / "landscape_playlist.radio.tsv") == []


def test_a_line_that_names_no_station_and_clip_is_passed_over(tmp_path):
    radio = tmp_path / "portrait_playlist.radio.tsv"
    radio.write_text("0\tone.mp4\n\nnot a station\n1\t\n1\ttwo.mp4\n", encoding="utf-8")

    assert read_radio(radio) == [[Path("one.mp4")], [Path("two.mp4")]]


def a_radio(stations=(["a.mp4"], ["b.mp4"], ["c.mp4"])):
    opened: list[FakeStation] = []

    def open_station(clips):
        opened.append(FakeStation(clips))
        return opened[-1]

    radio = Radio(open_station)
    radio.take([[Path(clip) for clip in clips] for clips in stations])
    radio.tick(picture=None, level=None, paused=False)
    return radio, opened


PICTURE, VIDEO, BETWEEN = True, False, None


def heard(opened: list[FakeStation]) -> list[int | None]:
    return [station.heard_at for station in opened]


def test_a_picture_coming_up_tunes_the_first_station_in_at_the_funestras_level():
    radio, opened = a_radio()

    radio.tick(picture=PICTURE, level=70, paused=False)

    assert heard(opened) == [70, None, None]


def ticked(radio: Radio, *showing: bool | None, level: int | None = 70) -> None:
    for kind in showing:
        radio.tick(picture=kind, level=level, paused=False)


def test_the_radio_is_out_of_earshot_while_a_video_plays():
    radio, opened = a_radio()

    ticked(radio, PICTURE, VIDEO)

    assert heard(opened) == [None, None, None]


def test_a_picture_after_a_video_tunes_the_next_station_in_and_the_last_comes_round_to_the_first():
    radio, opened = a_radio()

    tuned = []
    for _ in range(4):
        ticked(radio, PICTURE)
        tuned.append(heard(opened))
        ticked(radio, VIDEO)

    assert tuned == [[70, None, None], [None, 70, None], [None, None, 70], [70, None, None]]


def test_pictures_one_after_another_stay_on_the_one_station_through_the_gap_between_them():
    radio, opened = a_radio()
    ticked(radio, PICTURE, VIDEO)

    for kind in (PICTURE, BETWEEN, PICTURE, BETWEEN, PICTURE):
        ticked(radio, kind)
        assert heard(opened) == [None, 70, None]


def test_a_muted_funestra_hears_no_station():
    radio, opened = a_radio()

    ticked(radio, PICTURE, level=None)

    assert heard(opened) == [None, None, None]


def test_every_station_holds_still_with_the_room_and_goes_on_after():
    radio, opened = a_radio()

    radio.tick(picture=VIDEO, level=70, paused=True)
    assert [station.paused for station in opened] == [True, True, True]
    radio.tick(picture=VIDEO, level=70, paused=False)
    assert [station.paused for station in opened] == [False, False, False]


def test_stations_dealt_anew_take_the_old_ones_place():
    radio, opened = a_radio()

    radio.take([[Path("d.mp4")], [Path("e.mp4")], [Path("f.mp4")]])
    ticked(radio, VIDEO)

    assert [station.closed for station in opened] == [True, True, True, False, False, False]
    assert [station.clips for station in opened[3:]] == [[Path("d.mp4")], [Path("e.mp4")],
                                                        [Path("f.mp4")]]


def test_a_radio_closed_lets_every_station_go():
    radio, opened = a_radio()

    radio.close()

    assert [station.closed for station in opened] == [True, True, True]


def test_stations_that_cannot_be_opened_yet_open_once_they_can():
    sound = {"live": False}
    opened: list[FakeStation] = []

    def open_station(clips):
        if not sound["live"]:
            return None
        opened.append(FakeStation(clips))
        return opened[-1]

    radio = Radio(open_station)
    radio.take([[Path("a.mp4")], [Path("b.mp4")]])
    ticked(radio, PICTURE)
    assert opened == []

    sound["live"] = True
    ticked(radio, PICTURE)

    assert heard(opened) == [70, None]


def test_a_station_that_will_not_open_leaves_the_radio_quiet_and_is_asked_for_once(caplog):
    asked: list[list[Path]] = []

    def open_station(clips):
        asked.append(clips)
        raise OSError("The engine (libmpv) could not be loaded.")

    radio = Radio(open_station)
    radio.take([[Path("a.mp4")], [Path("b.mp4")]])

    ticked(radio, PICTURE, VIDEO, PICTURE)

    assert asked == [[Path("a.mp4")]]
    assert "could not be loaded" in caplog.text


def test_a_radio_file_hands_on_its_stations_when_it_appears_changes_and_goes(tmp_path):
    path = tmp_path / "portrait_playlist.radio.tsv"
    radio_file = RadioFile(path)
    assert radio_file.changed() is None

    write_radio(path, [[tmp_path / "a.mp4"]])
    assert radio_file.changed() == [[tmp_path / "a.mp4"]]
    assert radio_file.changed() is None

    write_radio(path, [[tmp_path / "a.mp4"], [tmp_path / "bb.mp4"]])
    assert radio_file.changed() == [[tmp_path / "a.mp4"], [tmp_path / "bb.mp4"]]

    path.unlink()
    assert radio_file.changed() == []


def test_the_stations_that_did_open_beside_one_that_would_not_are_let_go():
    opened: list[FakeStation] = []

    def open_station(clips):
        if clips == [Path("b.mp4")]:
            raise OSError("The engine (libmpv) could not be loaded.")
        opened.append(FakeStation(clips))
        return opened[-1]

    radio = Radio(open_station)
    radio.take([[Path("a.mp4")], [Path("b.mp4")]])

    ticked(radio, PICTURE)

    assert [station.closed for station in opened] == [True]
