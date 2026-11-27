from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app_support.threading_utils import start_daemon_thread

from .broker_feed import BrokerFeed, UdpListener, udp_reader
from .cloud_playback import on_this_disk
from .flag import Flag
from .flick_advance import FlickAdvanceState
from .flick_cache import DecodeRequestState, FlickCacheStore
from .flick_decode import load_flick_frames, read_frames_per_second
from .flick_flip import FlickFlip, FlipsKeptElsewhere
from .flick_folder import move_to_trash
from .flick_frame_rates import FlickFrameRates
from .flick_loader import FlickLoadController, FlickLoadParts
from .flick_renderer import FlickRenderController
from .flick_selection import FlickSelectionController, FlickSelectionParts
from .flick_sequence import FlickSequenceController
from .flicks_on_screen import FlicksOnScreen
from .funestra_verbs import LOCK_ON
from .genau_controls import GenauControls, apply_runtime_command
from .genau_files import GenauFiles
from .genau_refresh import GenauRefreshController
from .genau_settings import GenauSettings
from .inclusion_pair import PROJECTION
from .learned_motion import LearnedMotionState, load_default_model
from .off_the_loop import AtOnce, OffTheLoop
from .robot_hand import RobotHandState, bpm_for_speed
from .robot_hand_beat import BeatEngine, BeatTuning
from .robot_hand_driver import RobotHandTCodeDriver

logger = logging.getLogger(__name__)

CONDEMN_RETRY_S = 0.25
CONDEMN_PATIENCE_S = 30.0
UDP_READER_THREAD = "genau-udp"

Rescan = Callable[[bool], list[Path]]
Narrow = Callable[[bool, bool], list[Path]]


@dataclass(frozen=True)
class GenauEngine:
    controls: GenauControls
    controller: GenauRefreshController
    renderer: FlickRenderController
    driver: RobotHandTCodeDriver
    narrow: Callable[[Callable[[], list[Path]]], None]
    play_next: Callable[[Path], None]
    behind: OffTheLoop

    @property
    def current_flick(self) -> Path | None:
        return self.renderer.current_flick_path

    def frames_on_screen(self) -> Sequence:
        entry = self.renderer.current_flick_entry()
        return (entry.get("frames") if entry else None) or ()

    def playhead(self) -> tuple[int, int]:
        count = len(self.frames_on_screen())
        index = self.renderer.current_frame_index
        return (0 if index is None else max(0, count - 1 - index), count)

    @property
    def time_on_screen(self) -> tuple[float, float]:
        advance = self.controls.flick_advance_state
        return advance.elapsed, float(advance.interval)

    def refresh(self) -> None:
        self.controller.refresh()

    def seek(self, fraction: float) -> None:
        self.controller.seek_the_flick(fraction)

    def seek_the_time_on_screen(self, seconds: float) -> None:
        self.controller.seek_the_time_on_screen(seconds)

    def close(self) -> None:
        self.driver.close()
        self.behind.close()


@dataclass(frozen=True)
class GenauChannels:
    command: Path
    paused: Path
    status: Path
    drive: Path


@dataclass(frozen=True)
class FlickLibrary:
    flicks: list[Path]
    start_flick: Path | None = None
    metadata_root: Path | None = None
    flips: FlipsKeptElsewhere | None = None


class FlickTrash(Protocol):
    def folder_for(self, flick: Path) -> Path: ...

    def went(self, flick: Path, landed: Path) -> None: ...


@dataclass(frozen=True)
class GenauHost:
    notifier: object
    tcode_sink: object
    blit_frame: Callable[[object, Path | None], None]
    set_loading_text: Callable[[str | None], None]
    rescan: Rescan
    trash: FlickTrash | None = None
    narrow: Narrow | None = None
    say_no_other_flicks: Callable[[], None] = lambda: None
    say: Callable[[str], None] = lambda _words: None
    set_volume: Callable[[int, bool], None] | None = None


@dataclass(frozen=True)
class EngineSeams:
    stop_event: threading.Event | None = None
    decode: Callable[[Path], list] = lambda path: load_flick_frames(on_this_disk(path))
    frame_rate: Callable[[Path], float] = lambda path: read_frames_per_second(on_this_disk(path))
    start_thread: Callable = start_daemon_thread
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    log: logging.Logger = logger
    off_the_loop: Callable[[], OffTheLoop] = AtOnce


def build_genau_engine(
    settings: GenauSettings,
    channels: GenauChannels,
    library: FlickLibrary,
    host: GenauHost,
    seams: EngineSeams | None = None,
) -> GenauEngine:
    seams = seams or EngineSeams()
    behind = seams.off_the_loop()
    stop_event, decode, start_thread, clock, log = (
        seams.stop_event, seams.decode, seams.start_thread, seams.clock, seams.log)
    sequence = FlickSequenceController(library.flicks, start_at=library.start_flick)
    flick_store = FlickCacheStore(limit=settings.flick_cache_size)
    renderer = FlickRenderController(
        flick_store=flick_store,
        blit_frame=lambda frame: host.blit_frame(frame, renderer.current_flick_path))
    loader = FlickLoadController(FlickLoadParts(
        flick_store=flick_store,
        load_state=DecodeRequestState(),
        prefetch_state=DecodeRequestState(),
        current_flick_path_getter=lambda: renderer.current_flick_path,
        decode_flick=decode,
        start_thread=start_thread,
        logger=log,
        on_active_flick_loaded=renderer.prepare_active_flick_for_current_size,
    ))
    selection = FlickSelectionController(FlickSelectionParts(
        sequence=sequence,
        flick_store=flick_store,
        loader=loader,
        renderer=renderer,
        notifier=host.notifier,
        condemn_flick=lambda flick: _condemn(
            _Condemning(flick, host.trash, log, clock=clock, sleep=seams.sleep), start_thread),
        clock=clock,
    ))
    robot_hand = RobotHandState(playing=False, speed=50, bpm=bpm_for_speed(50))
    learned = LearnedMotionState(model=load_default_model())
    driver = RobotHandTCodeDriver(host.tcode_sink, robot_hand=robot_hand, learned=learned)
    broker = BrokerFeed()
    start_thread(
        target=udp_reader,
        args=(UdpListener(settings.udp_host, settings.udp_port, broker,
                          stop_event or threading.Event(), log),),
        name=UDP_READER_THREAD,
    )
    controls = GenauControls(
        engine=BeatEngine(last_tick=clock()),
        paused=Flag(),
        step_flick=selection.step,
        condemn_flick=None if host.trash is None else selection.condemn,
        robot_hand=robot_hand,
        learned_motion_state=learned,
        flick_advance_state=FlickAdvanceState(),
        stop_event=stop_event,
        hud=Flag(),
        set_volume=host.set_volume,
        reorder_flicks=lambda recent: _reorder(selection, host.rescan, recent, log),
        keep_shapes=None if host.narrow is None else (
            lambda plays_vr, plays_flat: narrow_to(
                lambda: host.narrow(plays_vr, plays_flat),
                says=PROJECTION.flash((plays_flat, plays_vr)))),
        play_file=selection.play,
        flick_flip=FlickFlip(library.metadata_root, kept_elsewhere=library.flips),
        flick_frame_rates=FlickFrameRates(read=seams.frame_rate),
    )
    controller = GenauRefreshController(
        controls,
        FlicksOnScreen(loader, renderer, selection, host.notifier, host.set_loading_text),
        broker=broker,
        files=GenauFiles(Path(channels.command), Path(channels.paused), channels.status,
                         Path(channels.drive)),
        tuning=BeatTuning(settings.beats_per_loop, settings.bpm_smoothing,
                          settings.sync_strength),
        tcode_sender=driver,
        logger=log,
        now_source=clock,
        start_thread=start_thread,
        publish=behind.publish,
    )

    def holding_what_is_on_screen() -> None:
        apply_runtime_command(LOCK_ON, controls)
        host.say_no_other_flicks()

    def narrow_to(scan: Callable[[], list[Path]], *, says: str = "") -> None:
        _narrow(selection, scan, log, nothing_left=holding_what_is_on_screen,
                kept=lambda: host.say(says) if says else None)

    selection.set_current_flick(selection.current_path)
    return GenauEngine(controls=controls, controller=controller, renderer=renderer,
                       driver=driver, narrow=narrow_to, play_next=selection.play_next,
                       behind=behind)


def _rescanned(rescan: Callable[[], list[Path]], log: logging.Logger) -> list[Path] | None:
    try:
        return rescan()
    except (OSError, RuntimeError):
        log.warning("Could not rescan Genau's folder; keeping the sequence", exc_info=True)
        return None


def _reorder(selection: FlickSelectionController, rescan: Rescan, recent: bool,
             log: logging.Logger) -> None:
    if flicks := _rescanned(lambda: rescan(recent), log):
        selection.reorder(flicks)
        log.info("Browsing %s (%d in all)", "newest-first" if recent else "reshuffled", len(flicks))


def _narrow(selection: FlickSelectionController, scan: Callable[[], list[Path]],
            log: logging.Logger, *, nothing_left: Callable[[], None],
            kept: Callable[[], object]) -> None:
    flicks = _rescanned(scan, log)
    if flicks:
        selection.narrow(flicks)
        kept()
    elif flicks is not None:
        nothing_left()


@dataclass(frozen=True)
class _Condemning:
    flick: Path
    trash: FlickTrash
    log: logging.Logger
    clock: Callable[[], float]
    sleep: Callable[[float], None]


def _condemn(condemning: _Condemning, start_thread) -> None:
    start_thread(target=_condemn_once_let_go, args=(condemning,), name="genau-condemn")


def _condemn_once_let_go(condemning: _Condemning) -> None:
    if not _still_open_after_trying(condemning):
        return
    condemning.log.info("%s is still open; condemning it once it is let go", condemning.flick.name)
    give_up_at = condemning.clock() + CONDEMN_PATIENCE_S
    while condemning.clock() < give_up_at:
        condemning.sleep(CONDEMN_RETRY_S)
        if not _still_open_after_trying(condemning):
            return
    condemning.log.error("%s was still open after %gs, so it was not condemned",
                         condemning.flick.name, CONDEMN_PATIENCE_S)


def _still_open_after_trying(condemning: _Condemning) -> bool:
    flick, log = condemning.flick, condemning.log
    trash_dir = condemning.trash.folder_for(flick)
    try:
        landed = move_to_trash(flick, trash_dir)
    except PermissionError:
        return True
    except OSError:
        log.error("Could not move %s to %s", flick.name, trash_dir, exc_info=True)
        return False
    if landed is None:
        log.info("%s was already gone; nothing to condemn", flick.name)
    else:
        log.info("Condemned %s to %s", flick.name, trash_dir)
        condemning.trash.went(flick, landed)
    return False
