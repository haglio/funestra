from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path

from .funestra import Channels

_TYPES = {"Path | None": Path, "str | None": str, "int | None": int}
_KINDS = {field.name: _TYPES[field.type] for field in fields(Channels)}
EVERY_CHANNEL = tuple(_KINDS)


def channel_flag(name: str) -> str:
    flag = f"--{name.replace('_', '-')}"
    return f"{flag}-file" if _KINDS[name] is Path else flag


def add_channel_arguments(parser: argparse.ArgumentParser,
                          names: Sequence[str] = EVERY_CHANNEL) -> None:
    for name in names:
        parser.add_argument(channel_flag(name), dest=name, type=_KINDS[name], default=None)


def channels_from_args(args: argparse.Namespace,
                       names: Sequence[str] = EVERY_CHANNEL) -> dict[str, object]:
    return {name: getattr(args, name) for name in names}


def channel_argv(channels: Channels, names: Sequence[str] = EVERY_CHANNEL) -> list[str]:
    words: list[str] = []
    for name in names:
        value = getattr(channels, name)
        if value is not None:
            words += [channel_flag(name), str(value)]
    return words
