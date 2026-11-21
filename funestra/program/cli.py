from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from ..channel_manifest import EVERY_CHANNEL, add_channel_arguments
from ..playlist import PlaylistItem, read_playlist
from .genau_launch import add_genau_arguments
from .placement import add_placement_arguments


def build_parser(channels: Sequence[str] = EVERY_CHANNEL) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A Funestra: a window that plays what an app hands it")
    add_channel_arguments(parser, channels)
    add_placement_arguments(parser)
    add_genau_arguments(parser)
    parser.add_argument("--no-audio", action="store_true", default=False,
                        help="Never play audio, and leave the volume control a read-only "
                             "indicator; without it a Funestra still opens muted, but "
                             "its chip can unmute it")
    parser.add_argument("--hidden", action="store_true", default=False,
                        help="Open a window nobody sees until it is told WINDOW_SHOW")
    parser.add_argument("--keys", action="store_true", default=False,
                        help="Tell the app, in the dashboard command file, each key pressed on "
                             "this window (key|name|held), when the window takes the keyboard "
                             "(focused) and when a press on the item is made again (pressed_again)")
    parser.add_argument("--ends-with", type=int, default=None,
                        help="The process id of the app this was started for; "
                             "the Funestra ends once that process has gone")
    return parser


def resolve_playlist(args) -> list[PlaylistItem]:
    if args.playlist is None:
        return []
    return read_playlist(Path(args.playlist))
