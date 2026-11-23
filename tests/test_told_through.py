from __future__ import annotations

from pathlib import Path

from funestra.paused_flag import PausedFlag
from funestra.playlist import PlaylistItem, write_playlist
from funestra.playlist_follower import PlaylistFollower
from funestra.told_through import FilesItIsToldThrough


def _list(playlist: Path, *names: str) -> None:
    write_playlist(playlist, [PlaylistItem(playlist.parent / name) for name in names])


def test_a_list_written_before_a_command_is_heard_with_it_or_before_it(tmp_path):
    playlist, paused = tmp_path / "playlist.tsv", tmp_path / "paused.txt"
    _list(playlist, "a0.mp4")

    def commands_written_after_the_list_and_the_flag() -> list[str]:
        _list(playlist, "b0.mp4")
        paused.write_text("1", encoding="utf-8")
        return ["NEXT"]

    told = FilesItIsToldThrough(
        commands=commands_written_after_the_list_and_the_flag, paused=PausedFlag(paused),
        playlist=PlaylistFollower(playlist, take=lambda _items: None),
        paused_at_the_start=False).read()

    assert (told.paused, [item.path.name for item in told.playlist.items], told.commands) == (
        True, ["b0.mp4"], ["NEXT"])


def test_nothing_is_heard_while_nothing_has_changed(tmp_path):
    playlist, paused = tmp_path / "playlist.tsv", tmp_path / "paused.txt"
    _list(playlist, "a0.mp4")
    paused.write_text("1", encoding="utf-8")
    told_through = FilesItIsToldThrough(
        commands=list, paused=PausedFlag(paused),
        playlist=PlaylistFollower(playlist, take=lambda _items: None), paused_at_the_start=True)

    assert told_through.read() is None
