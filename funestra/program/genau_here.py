from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ..channel_manifest import ChannelManifest
from ..flick_list import FlickList, GenauOnAList
from ..funestra import Users
from ..genau import STANDARD_SEAMS, Genau, GenauOutputs
from ..genau_engine import EngineSeams, GenauChannels
from ..genau_notifier import TellsNobody
from ..genau_settings import GenauSettings
from ..messages import MessageWriter
from ..modes import MainMode
from ..runs_here import AddsNothing
from ..tcode import SendsNowhere


@dataclass(frozen=True)
class GenauLaunch:
    command: Path
    paused: Path
    status: Path
    drive: Path
    flicks: Path
    beat_port: int

    @property
    def channels(self) -> GenauChannels:
        return GenauChannels(command=self.command, paused=self.paused, status=self.status,
                             drive=self.drive)


_MANIFEST = ChannelManifest(GenauLaunch, prefix="genau")


def add_genau_arguments(parser: argparse.ArgumentParser) -> None:
    _MANIFEST.add_arguments(parser)


def genau_argv(launch: GenauLaunch | None) -> list[str]:
    return [] if launch is None else _MANIFEST.argv(launch)


def genau_from_args(args: argparse.Namespace) -> GenauLaunch | None:
    given = _MANIFEST.from_args(args)
    return None if None in given.values() else GenauLaunch(**given)


def kino_and_genau(launch: GenauLaunch | None, *, notice: Path | None,
                   seams: EngineSeams = STANDARD_SEAMS) -> Users | None:
    if launch is None:
        return None
    start = partial(_genau, launch, MessageWriter(notice), seams)
    return {MainMode.KINO: lambda _playback: AddsNothing(),
            MainMode.GENAU: lambda _playback: GenauOnAList(FlickList(launch.flicks), start)}


def _genau(launch: GenauLaunch, messages: MessageWriter, seams: EngineSeams,
           flicks: FlickList) -> Genau:
    return Genau(flicks, settings=GenauSettings(udp_port=launch.beat_port),
                 channels=launch.channels,
                 outputs=GenauOutputs(notifier=TellsNobody(), tcode_sink=SendsNowhere(),
                                      messages=messages),
                 seams=seams)
