"""The playlist file: one item per line, written and read back through one module."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

import funestra.playlist
from funestra.playlist import (
    PlaylistItem,
    item_from_line,
    item_line,
    read_playlist,
    write_playlist,
)


class TestReadPlaylist:
    def test_parses_video_and_funscript_pairs(self, tmp_path):
        playlist = tmp_path / "main_player_playlist.tsv"
        playlist.write_text(
            "C:/vids/a.mp4\tC:/scripts/a.funscript\n"
            "C:/vids/b.mp4\t\n"
            "C:/vids/c.mp4\n",
            encoding="utf-8",
        )

        result = read_playlist(playlist)

        assert [item.path for item in result] == [
            Path("C:/vids/a.mp4"), Path("C:/vids/b.mp4"), Path("C:/vids/c.mp4"),
        ]
        assert result[0].funscript == Path("C:/scripts/a.funscript")
        assert result[1].funscript is None
        assert result[2].funscript is None

    def test_skips_blank_and_comment_lines(self, tmp_path):
        playlist = tmp_path / "main_player_playlist.tsv"
        playlist.write_text(
            "# header comment\n"
            "\n"
            "C:/vids/a.mp4\tC:/scripts/a.funscript\n",
            encoding="utf-8",
        )

        result = read_playlist(playlist)

        assert len(result) == 1

    def test_a_playlist_that_is_not_there_plays_nothing(self, tmp_path):
        assert read_playlist(tmp_path / "nope.tsv") == []


class TestAnItemIsAlsoThePairItWas:
    """Every reader in the family unpacked ``(video, funscript)`` before the item
    had a name, and a reader on a checkout that has not moved yet still does."""

    def test_unpacks_and_indexes_as_the_pair(self):
        item = PlaylistItem(Path("C:/vids/a.mp4"), Path("C:/scripts/a.funscript"))

        video, funscript = item

        assert (video, funscript) == (item.path, item.funscript)
        assert item[0] == item.path
        assert item == (Path("C:/vids/a.mp4"), Path("C:/scripts/a.funscript"))

    def test_the_funscript_is_optional(self):
        assert PlaylistItem(Path("C:/vids/a.mp4")).funscript is None

    def test_a_picture_with_places_still_unpacks_as_its_pair(self):
        item = PlaylistItem(Path("C:/out/a.png"), points_of_interest=((0.1, 0.2, 0.3, 0.4),))

        video, funscript = item

        assert (video, funscript) == (Path("C:/out/a.png"), None)
        assert item == (Path("C:/out/a.png"), None)

    def test_two_pictures_whose_only_difference_is_their_places_are_two_items(self):
        bare = PlaylistItem(Path("C:/out/a.png"))
        placed = PlaylistItem(Path("C:/out/a.png"), points_of_interest=((0.1, 0.2, 0.3, 0.4),))

        assert bare != placed
        assert placed == PlaylistItem(Path("C:/out/a.png"), points_of_interest=[[0.1, 0.2, 0.3, 0.4]])


class TestOneLineOneItem:
    """The line grammar is the file's and PLAY_FILE's alike, so both are read
    and written here and cannot say the same item two ways."""

    def test_a_scripted_item_carries_its_script_after_a_tab(self):
        item = PlaylistItem(Path("C:/vids/a.mp4"), Path("C:/scripts/a.funscript"))

        assert item_line(item) == f"{Path('C:/vids/a.mp4')}\t{Path('C:/scripts/a.funscript')}"
        assert item_from_line(item_line(item)) == item

    def test_an_unscripted_item_is_the_path_alone(self):
        item = PlaylistItem(Path("C:/vids/My Clip.mp4"))

        assert item_line(item) == str(Path("C:/vids/My Clip.mp4"))
        assert item_from_line(item_line(item)) == item

    def test_a_trailing_tab_is_no_script(self):
        assert item_from_line("C:/vids/a.mp4\t  ") == PlaylistItem(Path("C:/vids/a.mp4"))

    def test_a_line_naming_nothing_is_no_item(self):
        assert item_from_line("") is None
        assert item_from_line("\tC:/scripts/a.funscript") is None

    def test_a_picture_carries_the_places_it_punches_in_on_after_a_second_tab(self):
        item = PlaylistItem(Path("C:/out/a.png"),
                            points_of_interest=((0.1, 0.2, 0.3, 0.4), (0.5, 0.25, 0.75, 1.0)))

        assert item_line(item) == f"{Path('C:/out/a.png')}\t\t0.1,0.2,0.3,0.4;0.5,0.25,0.75,1"
        assert item_from_line(item_line(item)).points_of_interest == item.points_of_interest


class TestWritePlaylist:
    def test_what_is_written_is_what_is_read_back(self, tmp_path):
        items = [
            PlaylistItem(tmp_path / "a.mp4", tmp_path / "a.funscript"),
            PlaylistItem(tmp_path / "b.mp4"),
        ]
        playlist = tmp_path / "state" / "portrait_playlist.tsv"

        write_playlist(playlist, items)

        assert read_playlist(playlist) == items

    def test_the_file_is_one_item_per_line_with_no_column_for_a_missing_script(self, tmp_path):
        playlist = tmp_path / "playlist.tsv"

        write_playlist(playlist, [PlaylistItem(Path("C:/vids/a.mp4")),
                                  PlaylistItem(Path("C:/vids/b.mp4"), Path("C:/s/b.funscript"))])

        assert playlist.read_text(encoding="utf-8") == (
            f"{Path('C:/vids/a.mp4')}\n{Path('C:/vids/b.mp4')}\t{Path('C:/s/b.funscript')}\n")

    def test_rewriting_replaces_the_whole_list(self, tmp_path):
        playlist = tmp_path / "playlist.tsv"
        write_playlist(playlist, [PlaylistItem(Path("C:/vids/a.mp4")), PlaylistItem(Path("C:/vids/b.mp4"))])

        write_playlist(playlist, [PlaylistItem(Path("C:/vids/c.mp4"))])

        assert [item.path for item in read_playlist(playlist)] == [Path("C:/vids/c.mp4")]
        assert not (tmp_path / "playlist.tmp").exists()

    def test_a_playlist_lands_though_a_funestra_is_partway_through_reading_it(self, tmp_path):
        playlist = tmp_path / "portrait_playlist.tsv"
        write_playlist(playlist, [PlaylistItem(Path("C:/vids/before.mp4"))])

        with _held_open_for(playlist, 0.1):
            write_playlist(playlist, [PlaylistItem(Path("C:/vids/after.mp4"))])

        assert [item.path for item in read_playlist(playlist)] == [Path("C:/vids/after.mp4")]

    def test_a_playlist_a_funestra_keeps_open_past_the_budget_is_refused_out_loud(
            self, tmp_path, monkeypatch):
        playlist = tmp_path / "portrait_playlist.tsv"
        write_playlist(playlist, [PlaylistItem(Path("C:/vids/before.mp4"))])
        monkeypatch.setattr(funestra.playlist, "READER_HOLD_BUDGET_S", 0.05)

        with _held_open_for(playlist, 0.5), pytest.raises(OSError, match="portrait_playlist"):
            write_playlist(playlist, [PlaylistItem(Path("C:/vids/after.mp4"))])


@contextmanager
def _held_open_for(path: Path, seconds: float):
    reader = path.open(encoding="utf-8")
    release = threading.Timer(seconds, reader.close)
    release.start()
    try:
        yield
    finally:
        release.join()
