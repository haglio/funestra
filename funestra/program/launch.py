from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..channel_manifest import channel_argv
from ..funestra import Channels
from .placement import WindowPlacement

PROGRAM_MODULE = "funestra.program"


@dataclass(frozen=True)
class Asked:
    hidden: bool = False
    keys: bool = False
    ends_with: int | None = None
    no_audio: bool = False

    def to_argv(self) -> list[str]:
        words = [flag for flag, on in (("--hidden", self.hidden), ("--keys", self.keys),
                                       ("--no-audio", self.no_audio)) if on]
        if self.ends_with is not None:
            words += ["--ends-with", str(self.ends_with)]
        return words


NOTHING_ELSE = Asked()


def launch_command(python_exe: Path | str, channels: Channels, placement: WindowPlacement,
                   asked: Asked = NOTHING_ELSE, *, module: str = PROGRAM_MODULE) -> list[str]:
    return [str(python_exe), "-m", module, *placement.to_argv(), *channel_argv(channels),
            *asked.to_argv()]
