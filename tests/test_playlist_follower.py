from __future__ import annotations

import os
from pathlib import Path

from funestra_fakes import stamped_long_ago

from funestra import playlist_follower
from funestra.playlist import PlaylistItem, write_playlist
from funestra.playlist_follower import PlaylistFollower


def _write(playlist: Path, *names: str) -> None:
    write_playlist(playlist, [PlaylistItem(playlist.parent / name) for name in names])


def _follow(follower: PlaylistFollower) -> None:
    heard = follower.look()
    if heard is not None:
        follower.take_heard(heard)


def _names(taken: list[list[PlaylistItem]]) -> list[list[str]]:
    return [[item.path.name for item in items] for items in taken]


class TestAListWrittenUnderTheWindow:
    def test_is_taken_with_no_verb_sent_since_the_reload_verb_is_dropped_when_the_command_file_is_held_too_long(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        _write(playlist, "a show.png")
        _follow(follower)

        assert _names(taken) == [["a show.png"]]

    def test_is_taken_once_however_many_frames_follow_since_taking_it_again_restarts_the_show(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        _write(playlist, "a show.png")
        for _ in range(5):
            _follow(follower)

        assert _names(taken) == [["a show.png"]]

    def test_is_told_apart_from_the_one_before_it_though_windows_stamped_both_with_one_time(
            self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "v0.mp4")
        first = playlist.stat()
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        _write(playlist, "v2.mp4")
        os.utime(playlist, ns=(first.st_atime_ns, first.st_mtime_ns))
        assert (playlist.stat().st_size, playlist.stat().st_mtime_ns) == (
            first.st_size, first.st_mtime_ns)
        _follow(follower)

        assert _names(taken) == [["v2.mp4"]]

    def test_the_list_the_window_opened_on_is_not_taken_again_which_would_restart_the_show(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        _follow(follower)

        assert taken == []


class TestAReadThatLandsInsideTheWrite:

    def test_is_read_again_on_the_next_frame(self, tmp_path, monkeypatch):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)
        _write(playlist, "a show.png")
        real = playlist_follower.playlist_text
        answers = ["", ""]
        monkeypatch.setattr(playlist_follower, "playlist_text",
                            lambda path: answers.pop(0) if answers else real(path))

        _follow(follower)
        _follow(follower)
        _follow(follower)

        assert _names(taken) == [["a show.png"]]


class TestAListTakenAway:
    def test_leaves_what_is_playing_alone(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        playlist.unlink()
        for _ in range(5):
            _follow(follower)

        assert taken == []

    def test_an_emptied_file_leaves_it_alone_too(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        playlist.write_text("", encoding="utf-8")
        for _ in range(5):
            _follow(follower)

        assert taken == []


class TestTheReloadVerb:
    def test_reads_the_list_when_asked_to_read_now(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "a show.png")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)

        follower.read_now()

        assert _names(taken) == [["a show.png"]]


class TestAListHeardBeforeTheReloadVerb:
    def test_is_not_taken_after_the_list_the_reload_read_since_that_one_is_newer(self, tmp_path):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        taken: list[list[PlaylistItem]] = []
        follower = PlaylistFollower(playlist, take=taken.append)
        _write(playlist, "a show.png")
        heard_before = follower.look()

        _write(playlist, "another show.png")
        follower.read_now()
        follower.take_heard(heard_before)

        assert _names(taken) == [["another show.png"]]


class TestAListThatHasNotChanged:
    def test_is_neither_opened_nor_parsed_again_however_many_frames_follow(
            self, tmp_path, monkeypatch):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, *(f"video {n}.mp4" for n in range(5)))
        stamped_long_ago(playlist)
        follower = PlaylistFollower(playlist, take=lambda items: None)
        opened: list[Path] = []
        parsed: list[str] = []
        monkeypatch.setattr(playlist_follower, "playlist_text", opened.append)
        monkeypatch.setattr(playlist_follower, "parse_playlist", parsed.append)

        for _ in range(60):
            _follow(follower)

        assert (opened, parsed) == ([], [])

    def test_a_list_taken_away_or_emptied_is_not_opened_either(self, tmp_path, monkeypatch):
        playlist = tmp_path / "landscape.tsv"
        _write(playlist, "its own clip.mp4")
        follower = PlaylistFollower(playlist, take=lambda items: None)
        opened: list[Path] = []
        monkeypatch.setattr(playlist_follower, "playlist_text", opened.append)

        playlist.write_text("", encoding="utf-8")
        _follow(follower)
        playlist.unlink()
        _follow(follower)

        assert opened == []
