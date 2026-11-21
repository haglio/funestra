from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from ..channel_manifest import ChannelManifest


@dataclass(frozen=True)
class GenauLaunch:
    command: Path
    paused: Path
    status: Path
    drive: Path
    flicks: Path
    beat_port: int


_MANIFEST = ChannelManifest(GenauLaunch, prefix="genau")


def add_genau_arguments(parser: argparse.ArgumentParser) -> None:
    _MANIFEST.add_arguments(parser)


def genau_argv(launch: GenauLaunch | None) -> list[str]:
    return [] if launch is None else _MANIFEST.argv(launch)


def genau_from_args(args: argparse.Namespace) -> GenauLaunch | None:
    given = _MANIFEST.from_args(args)
    return None if None in given.values() else GenauLaunch(**given)
