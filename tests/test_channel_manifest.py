from __future__ import annotations

import argparse
from dataclasses import fields
from pathlib import Path

from funestra.channel_manifest import (
    add_channel_arguments,
    channel_argv,
    channel_flag,
    channels_from_args,
)
from funestra.funestra import Channels


def test_a_file_channel_is_named_on_the_command_line_by_its_field_and_file():
    assert channel_flag("notice") == "--notice-file"
    assert channel_flag("dashboard_cmd") == "--dashboard-cmd-file"


def test_a_channel_that_is_not_a_file_is_named_by_its_field_alone():
    assert channel_flag("osr2_port") == "--osr2-port"
    assert channel_flag("osr2_sender") == "--osr2-sender"


def test_every_channel_has_a_flag_and_no_two_share_one():
    flags = [channel_flag(field.name) for field in fields(Channels)]

    assert len(set(flags)) == len(flags)


def test_the_channels_a_launcher_writes_are_the_channels_the_funestra_reads_back():
    sent = Channels(notice=Path("C:/example/state/notice.txt"), hud=Path("C:/example/state/hud.json"),
                    osr2_sender="portrait", osr2_port=5005)
    parser = argparse.ArgumentParser()
    add_channel_arguments(parser)

    read = Channels(**channels_from_args(parser.parse_args(channel_argv(sent))))

    assert read == sent


def test_a_launcher_can_name_only_the_channels_its_funestra_takes():
    parser = argparse.ArgumentParser()
    add_channel_arguments(parser, ("notice", "hud"))

    args = parser.parse_args(["--hud-file", "C:/example/state/hud.json"])

    assert channels_from_args(args, ("notice", "hud")) == {
        "notice": None, "hud": Path("C:/example/state/hud.json")}
