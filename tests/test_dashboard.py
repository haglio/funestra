from __future__ import annotations

from pathlib import Path

from funestra.dashboard import ask


def test_an_ask_goes_out_on_the_dashboards_channel(tmp_path: Path):
    ask(tmp_path / "dashboard_cmd.txt", "audio_mute")

    assert (tmp_path / "dashboard_cmd.txt").read_text(encoding="utf-8").split() == ["audio_mute"]


def test_a_second_ask_joins_the_queue_rather_than_replacing_it(tmp_path: Path):
    ask(tmp_path / "dashboard_cmd.txt", "main_next")
    ask(tmp_path / "dashboard_cmd.txt", "audio_set_volume|40")

    assert (tmp_path / "dashboard_cmd.txt").read_text(encoding="utf-8").split() == [
        "main_next", "audio_set_volume|40"]


def test_with_no_channel_there_is_nobody_to_ask():
    ask(None, "audio_mute")
