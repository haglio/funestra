from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .flick_flip import FlipsKeptElsewhere
from .flick_folder import no_other_flicks
from .flick_overlay import FlickFrame
from .funestra_verbs import NEXT, PREV
from .genau_controls import apply_runtime_command
from .genau_engine import EngineSeams, FlickLibrary, GenauChannels, GenauHost, build_genau_engine
from .genau_settings import GenauSettings
from .main_hud import ModeHud
from .messages import MessageWriter
from .modes import MessageLevel
from .off_the_loop import BehindTheLoop

logger = logging.getLogger(__name__)

ROBOT_HAND = "robot hand"

Narrow = Callable[[str], None]


@dataclass(frozen=True)
class Opening:
    flicks: list[Path]
    none_kept: bool = False


class FlickSource(Protocol):
    metadata_root: Path | None
    flips: FlipsKeptElsewhere | None
    keep_shapes: Callable[[bool, bool], None] | None

    def opening(self, *, recent: bool, shuffled: bool) -> Opening: ...

    def listed(self, *, recent: bool, shuffled: bool) -> list[Path]: ...

    def name_of(self, flick: Path) -> str: ...

    def trash_folder_for(self, flick: Path) -> Path: ...

    def went(self, flick: Path, landed: Path) -> None: ...

    def up_next(self, *, recent: bool, showing: bool) -> list[Path]: ...

    def apply_command(self, command: str, narrow: Narrow) -> bool: ...


@dataclass(frozen=True)
class GenauOutputs:
    notifier: Any
    tcode_sink: Any
    messages: MessageWriter | None = None


STANDARD_SEAMS = EngineSeams(log=logger, off_the_loop=BehindTheLoop)


def _a_step(command: str) -> bool:
    return command.split(None, 1)[0].upper() in (NEXT, PREV) if command.strip() else False


class Genau:
    def __init__(
        self,
        source: FlickSource,
        *,
        settings: GenauSettings,
        channels: GenauChannels,
        outputs: GenauOutputs,
        start_flick: Path | None = None,
        latest: bool = False,
        seams: EngineSeams = STANDARD_SEAMS,
    ) -> None:
        self._source = source
        self._shuffled = settings.shuffle_on_load
        self._recent = latest
        self._notifier = outputs.notifier
        self._messages = outputs.messages
        self._frame = None
        self._flick: Path | None = None
        self._loading: str | None = None
        self._showing = False
        opening = source.opening(recent=latest, shuffled=self._shuffled)
        self._engine = build_genau_engine(
            settings,
            channels,
            FlickLibrary(opening.flicks, start_flick, source.metadata_root, flips=source.flips),
            GenauHost(
                notifier=outputs.notifier,
                tcode_sink=outputs.tcode_sink,
                blit_frame=self._take_frame,
                set_loading_text=self._set_loading,
                rescan=self._rescan,
                narrow=None if source.keep_shapes is None else self._kept_to_shapes,
                say_no_other_flicks=self._say_no_other_flicks,
                say=self._say,
                condemned_to=source.trash_folder_for,
                set_volume=self._the_apps_level_is_the_funestras,
                tell_where_it_went=source.went,
            ),
            seams,
        )
        if opening.none_kept:
            self._engine.narrow(list)
        self._put_up_what_arrived()

    @property
    def loading(self) -> str | None:
        return self._loading

    def apply_command(self, command: str) -> bool:
        if self._showing and _a_step(command):
            apply_runtime_command(command, self._engine.controls)
            return True
        return self._source.apply_command(command, self._narrow)

    def tick(self) -> None:
        self._put_up_what_arrived()
        self._engine.refresh()

    def status_fields(self) -> dict[str, str]:
        return {}

    def top_block(self) -> ModeHud:
        flick = self._engine.current_flick
        return ModeHud(video="" if flick is None else self._source.name_of(flick))

    def set_showing(self, showing: bool) -> None:
        self._showing = showing
        self._engine.controls.hud.on = not showing

    def own_frame(self) -> FlickFrame:
        played, count = self._engine.playhead()
        elapsed_s, interval_s = self._engine.time_on_screen
        return FlickFrame(frame=self._frame, played=played, count=count,
                          elapsed_ms=elapsed_s * 1000.0, interval_ms=interval_s * 1000.0,
                          loading=self._loading,
                          seek_time=lambda ms: self._engine.seek_the_time_on_screen(ms / 1000.0),
                          seek_loop=self._engine.seek, flick=self._flick,
                          frames=self._engine.frames_on_screen())

    def send_between_passes(self, now: float) -> None:
        self._engine.controller.send_between_passes(now)

    def close(self) -> None:
        self._engine.close()
        self._notifier.close()

    def _put_up_what_arrived(self) -> None:
        for flick in self._source.up_next(recent=self._recent, showing=self._showing):
            self._engine.play_next(flick)

    def _listed(self) -> list[Path]:
        return self._source.listed(recent=self._recent, shuffled=self._shuffled)

    def _narrow(self, says: str) -> None:
        self._engine.narrow(self._listed, says=says)

    def _rescan(self, recent: bool) -> list[Path]:
        self._recent = recent
        return self._listed()

    def _kept_to_shapes(self, plays_vr: bool, plays_flat: bool) -> list[Path]:
        self._source.keep_shapes(plays_vr, plays_flat)
        return self._listed()

    def _take_frame(self, frame, flick: Path | None) -> None:
        self._frame, self._flick = frame, flick

    def _set_loading(self, text: str | None) -> None:
        self._loading = text

    def _say_no_other_flicks(self) -> None:
        if self._messages is not None:
            self._messages.say(no_other_flicks(), level=MessageLevel.WARNING)

    def _say(self, words: str) -> None:
        if self._messages is not None:
            self._messages.say(words, level=MessageLevel.NORMAL)

    @staticmethod
    def _the_apps_level_is_the_funestras(_level: int, _muted: bool) -> None:
        pass
