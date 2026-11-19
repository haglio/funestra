from __future__ import annotations

from pathlib import Path

from funestra.channel_manifest import channel_flag
from funestra.playlist import PlaylistItem
from funestra.program.cli import build_parser, resolve_playlist
from funestra.program.placement import WindowPlacement


def test_resolve_playlist_reads_each_video_with_its_funscript(tmp_path):
    pl = tmp_path / "portrait.tsv"
    pl.write_text("a.mp4\nb.mp4\tb.funscript\n", encoding="utf-8")
    args = build_parser().parse_args([channel_flag("playlist"), str(pl)])

    assert resolve_playlist(args) == [
        PlaylistItem(Path("a.mp4")), PlaylistItem(Path("b.mp4"), Path("b.funscript"))]


def test_resolve_playlist_without_a_file_is_empty():
    args = build_parser().parse_args([])
    assert resolve_playlist(args) == []


def test_parser_accepts_the_file_quartet_and_geometry(tmp_path):
    args = build_parser().parse_args([
        channel_flag("playlist"), str(tmp_path / "p.tsv"),
        channel_flag("command"), str(tmp_path / "cmd.txt"),
        channel_flag("paused"), str(tmp_path / "paused.txt"),
        channel_flag("status"), str(tmp_path / "status.txt"),
        channel_flag("notice"), str(tmp_path / "notice.txt"),
        channel_flag("play_points"), str(tmp_path / "points.json"),
        "--x", "2560", "--y", "0", "--width", "1440", "--height", "2500",
    ])
    assert args.command == tmp_path / "cmd.txt"
    assert args.paused == tmp_path / "paused.txt"
    assert args.status == tmp_path / "status.txt"
    assert args.notice == tmp_path / "notice.txt"
    assert args.play_points == tmp_path / "points.json"
    assert (args.x, args.y, args.width, args.height) == (2560, 0, 1440, 2500)


def test_a_parser_told_which_channels_it_has_refuses_the_others():
    parser = build_parser(("playlist",))

    assert parser.parse_known_args([channel_flag("console"), "console.json"])[1] == [
        channel_flag("console"), "console.json"]


def test_an_app_titles_a_funestra_through_the_flag():
    assert build_parser().parse_args([]).title == "Funestra"
    assert build_parser().parse_args(["--title", "Portrait AI Funestra"]).title == (
        "Portrait AI Funestra")


def test_parser_takes_the_hud_and_command_files():
    args = build_parser().parse_args(
        [channel_flag("hud"), "state/portrait_hud.json",
         channel_flag("dashboard_cmd"), "state/dashboard_cmd.txt"]
    )

    assert args.hud == Path("state/portrait_hud.json")
    assert args.dashboard_cmd == Path("state/dashboard_cmd.txt")


def test_the_hud_files_are_optional():
    args = build_parser().parse_args([])

    assert args.hud is None
    assert args.dashboard_cmd is None


def test_a_placement_written_as_arguments_reads_back_as_itself(tmp_path):
    placement = WindowPlacement(x=-1200, y=40, width=1080, height=1920, title="Made Up Funestra",
                                taskbar_identity="Made.Up", icon=tmp_path / "icon.ico", tiles=True)

    assert WindowPlacement.from_args(build_parser().parse_args(placement.to_argv())) == placement


def test_a_placement_left_as_it_comes_asks_for_nothing_but_its_size_and_title():
    assert WindowPlacement().to_argv() == ["--width", "1200", "--height", "900",
                                           "--title", "Funestra"]
