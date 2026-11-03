from __future__ import annotations

import os
from pathlib import Path

from funestra import playlist_follower
from funestra.playlist import PlaylistItem
from funestra.playlist_follower import PlaylistFollower


def _write(playlist: Path, *names: str) -> None:
    playlist.write_text("".join(f"{playlist.parent / name}\n" for name in names), encoding="utf-8")


def _names(taken: list[list[PlaylistItem]]) -> list[list[str]]:
    return [[item.path.name for item in items] for items in taken]


class TestAListWrittenUnderTheWindow:
    def test_is_taken_with_no_verb_sent(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        _write(playlist, "a show.png")
        follower.tick()

        assert _names(taken) == [["a show.png"]]

    def test_is_taken_once_however_many_frames_follow(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        _write(playlist, "a show.png")
        for _ in range(5):
            follower.tick()

        assert _names(taken) == [["a show.png"]]

    def test_is_told_apart_from_the_one_before_it_by_what_it_says(self, tmp_path):
        """Not by the file's size and write time, which both lists here share: two
        names can be the same length, and Windows stamps both writes with the same
        time whenever they land inside one tick of its 15ms clock.  Read that way,
        this landed green on one machine and red on the next."""
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "v0.mp4")
        first = playlist.stat()
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        _write(playlist, "v2.mp4")
        os.utime(playlist, ns=(first.st_atime_ns, first.st_mtime_ns))
        assert playlist.stat().st_size == first.st_size
        follower.tick()

        assert _names(taken) == [["v2.mp4"]]

    def test_the_list_the_window_opened_on_is_not_taken_again(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        follower.tick()

        assert taken == []


class TestAReadThatLandsInsideTheWrite:
    """The list is published by writing a temp file and renaming it over this one,
    and on Windows a read during that rename answers a sharing violation, which
    `read_playlist` reports as no items.  Taken for the list, that would leave the
    window playing its old one and the new list would never be read again."""

    def test_is_read_again_on_the_next_frame(self, tmp_path, monkeypatch):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)
        _write(playlist, "a show.png")
        real = playlist_follower.read_playlist
        answers = [[], []]
        monkeypatch.setattr(playlist_follower, "read_playlist",
                            lambda path: answers.pop(0) if answers else real(path))

        follower.tick()
        follower.tick()
        follower.tick()

        assert _names(taken) == [["a show.png"]]


class TestAListTakenAway:
    def test_leaves_what_is_playing_alone(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        playlist.unlink()
        for _ in range(5):
            follower.tick()

        assert taken == []

    def test_an_emptied_file_leaves_it_alone_too(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        playlist.write_text("", encoding="utf-8")
        for _ in range(5):
            follower.tick()

        assert taken == []


class TestTheReloadVerb:
    def test_reads_at_once_rather_than_on_the_next_frame(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "a show.png")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        follower.read_now()

        assert _names(taken) == [["a show.png"]]
