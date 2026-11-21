from __future__ import annotations

from functools import partial
from pathlib import Path

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
from .genau_launch import GenauLaunch


def kino_and_genau(launch: GenauLaunch, *, notice: Path | None,
                   seams: EngineSeams = STANDARD_SEAMS) -> Users:
    start = partial(_genau, launch, MessageWriter(notice), seams)
    return {MainMode.KINO: lambda _playback: AddsNothing(),
            MainMode.GENAU: lambda _playback: GenauOnAList(FlickList(launch.flicks), start)}


def _genau(launch: GenauLaunch, messages: MessageWriter, seams: EngineSeams,
           flicks: FlickList) -> Genau:
    return Genau(flicks, settings=GenauSettings(udp_port=launch.beat_port),
                 channels=GenauChannels(command=launch.command, paused=launch.paused,
                                        status=launch.status, drive=launch.drive),
                 outputs=GenauOutputs(notifier=TellsNobody(), tcode_sink=SendsNowhere(),
                                      messages=messages),
                 seams=seams)
