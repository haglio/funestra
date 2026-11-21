from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path

from .funestra import Channels

_TYPES = {"Path | None": Path, "str | None": str, "int | None": int}


class ChannelManifest:
    def __init__(self, of: type, *, prefix: str = "") -> None:
        self._kinds = {field.name: _TYPES[field.type] for field in fields(of)}
        self._prefix = prefix
        self.every = tuple(self._kinds)

    def flag(self, name: str) -> str:
        flag = f"--{self._dest(name).replace('_', '-')}"
        return f"{flag}-file" if self._kinds[name] is Path else flag

    def add_arguments(self, parser: argparse.ArgumentParser,
                      names: Sequence[str] | None = None) -> None:
        for name in self._named(names):
            parser.add_argument(self.flag(name), dest=self._dest(name), type=self._kinds[name],
                                default=None)

    def from_args(self, args: argparse.Namespace,
                  names: Sequence[str] | None = None) -> dict[str, object]:
        return {name: getattr(args, self._dest(name)) for name in self._named(names)}

    def argv(self, value: object, names: Sequence[str] | None = None) -> list[str]:
        words: list[str] = []
        for name in self._named(names):
            given = getattr(value, name)
            if given is not None:
                words += [self.flag(name), str(given)]
        return words

    def _named(self, names: Sequence[str] | None) -> Sequence[str]:
        return self.every if names is None else names

    def _dest(self, name: str) -> str:
        return f"{self._prefix}_{name}" if self._prefix else name


CHANNELS = ChannelManifest(Channels)
EVERY_CHANNEL = CHANNELS.every
channel_flag = CHANNELS.flag
add_channel_arguments = CHANNELS.add_arguments
channels_from_args = CHANNELS.from_args
channel_argv = CHANNELS.argv
