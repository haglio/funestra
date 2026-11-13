from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol, runtime_checkable

from app_support.osr2_slot import Osr2Sender

from .control_registry import look_up
from .dashboard import ask
from .drive_gate import DriveGate
from .file_channel import consume_command_file, read_paused_state
from .flick_overlay import FlickFrame, FlickOverlay
from .funestra_controls import VERBS, FunestraControls
from .funestra_setup import FunestraSetup
from .funestra_status import status_fields, volume_fields
from .funscript_jumps import FunscriptJumps
from .hud_corners import HudCorners
from .hud_minimize import NameFlash
from .hud_overlay import DrawnOn, DriveFeed, HudOverlay, PublishedHud, WindowsOwnHud
from .hud_placement import HudEdge
from .hud_row import ItemRowDraw, RowHud, RowPress
from .items_row import ItemsRow, frame_row
from .loop_frames import IN_FRAME_OVERLAY_ID, OUT_FRAME_OVERLAY_ID, LoopFrames
from .main_hud import ModeHud
from .main_hud_overlay import MainHudFiles, MainHudHost, MainHudOverlay
from .messages import MessageWriter
from .mpv_engine import MpvEngine
from .osr2_visualizer import DrivePublisher
from .outside_buttons import OutsideButtons
from .playback import Playback
from .playlist import PlaylistItem
from .playlist_follower import PlaylistFollower
from .pointer import OMNIPAUSE_TOGGLE, Pointer
from .radio import Radio, RadioFile, radio_file_for
from .runs_here import RunsHere, User
from .satellite_hud import HudModel
from .scrubber import Heatmap
from .session_quit import quit_gesture
from .status import StatusWriter
from .tcode import UdpTCodeSink
from .tcode_driver import FunscriptTCodeDriver
from .volume import VolumeHud
from .volume_control import told_to_the_host

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Channels:
    playlist: Path | None = None
    command: Path | None = None
    paused: Path | None = None
    status: Path | None = None
    notice: Path | None = None
    play_points: Path | None = None
    hud: Path | None = None
    console: Path | None = None
    dashboard_cmd: Path | None = None
    drive: Path | None = None
    tcode_host: str | None = None
    tcode_port: int | None = None
    osr2_sender: str | None = None
    osr2_port: int | None = None
    osr2_readout: Path | None = None


@runtime_checkable
class HudSurface(Protocol):
    width: int | None

    def overlay(self, ident: int, x: int, y: int, bgra) -> None: ...

    def remove_overlay(self, ident: int) -> None: ...


@runtime_checkable
class UsersFrames(Protocol):
    def show(self, frame: FlickFrame, viewport: tuple[int, int]) -> None: ...

    def hide(self) -> None: ...


Users = Mapping[str, Callable[[Playback], User]]


def osr2_line(channels: Channels) -> FunscriptTCodeDriver | None:
    if channels.osr2_sender:
        return FunscriptTCodeDriver(Osr2Sender(channels.osr2_sender, port=channels.osr2_port))
    if not channels.tcode_host or not channels.tcode_port:
        return None
    return FunscriptTCodeDriver(UdpTCodeSink(channels.tcode_host, channels.tcode_port))


class Funestra:
    IN_FRAME_OVERLAY_ID = IN_FRAME_OVERLAY_ID
    OUT_FRAME_OVERLAY_ID = OUT_FRAME_OVERLAY_ID

    def __init__(self, engine, setup: FunestraSetup) -> None:
        channels = setup.channels
        self._engine = engine
        self._setup = setup
        self._channels = channels
        self._hud_surface = setup.hud_surface
        self._stop = threading.Event()
        self._playback = Playback(
            [item.path for item in setup.playlist], engine=engine,
            setup=setup.playback_setup(start_paused=(
                channels.paused is not None
                and read_paused_state(channels.paused, logger=logger))))
        self._follower = (None if channels.playlist is None
                          else PlaylistFollower(channels.playlist, take=self.take_the_list))
        self._drive_gate = DriveGate(self.playback)
        self._row = ItemsRow(self.playback, engine)
        self._volume = setup.volume_on(engine)
        self._radio = setup.radio if setup.radio is not None else self._radio_beside(channels)
        self._hud = self._hud_for(channels, setup.hud_surface or engine, setup.hud)
        self._name_flash = NameFlash(setup.clock)
        self._flash = ""
        self._users_frames = setup.users_frames or FlickOverlay(engine)
        self._corners = None if self._hud is None or setup.hud_surface is not None else HudCorners(
            self._hud, engine, post=self._where_the_hud_asks(channels))
        self._pointer = Pointer(hud=self._hud, corners=self._corners,
                                item=self._press_on_the_item(channels))
        self._runs_here = RunsHere(
            {name: make(self.playback) for name, make in (setup.users or {}).items()})
        self._controls = FunestraControls(
            self.playback, stop_event=self._stop,
            reload_playlist=None if self._follower is None else self._follower.read_now,
            volume=self._volume, show=self._runs_here.show,
            funscript_jumps=FunscriptJumps(self.playback, MessageWriter(channels.notice)))
        self._status = (
            StatusWriter(channels.status, lambda _playback: self.status_fields())
            if channels.status else None
        )
        self._loop_frames = LoopFrames(engine)
        self._short_of_memory = False

    @property
    def playback(self) -> Playback:
        return self._playback

    def status_fields(self) -> dict[str, str]:
        return {
            **status_fields(self.playback, self._drive_gate.handoff_touch()),
            **volume_fields(self._volume.hud),
            **self._runs_here.status_fields()}

    @property
    def runs_here(self) -> RunsHere:
        return self._runs_here

    @property
    def hud(self) -> HudOverlay | MainHudOverlay | None:
        return self._hud

    @property
    def volume(self) -> VolumeHud:
        return self._volume.hud

    @property
    def strip(self) -> Heatmap:
        return self._row.strip

    @property
    def _front(self) -> User:
        return self._runs_here.front

    def _top_block(self) -> ModeHud:
        return self._front.top_block()

    def _hud_for(self, channels: Channels, drawn_on,
                 hud: Callable[[], HudModel | None] | None) -> HudOverlay | MainHudOverlay | None:
        if channels.dashboard_cmd is None:
            if hud is None:
                return None
            return HudOverlay(
                source=WindowsOwnHud(hud, self.apply),
                drawn_on=DrawnOn(drawn_on, minus_on_the_hud=self._hud_surface is None),
                row=self._row_press(),
            )
        if channels.console is not None:
            return MainHudOverlay(
                files=MainHudFiles(channels.console, channels.dashboard_cmd),
                drawn_on=DrawnOn(
                    drawn_on, minus_on_the_hud=self._hud_surface is None,
                    width=None if self._hud_surface is None else self._hud_surface.width),
                host=MainHudHost(self._top_block, self._row_press(), self._setup.host_controls),
                drive=DriveFeed(channels.drive, self._drive_gate, self._visualizer_for(channels)),
                clock=self._setup.clock,
            )
        if channels.hud is not None:
            return HudOverlay(
                source=PublishedHud(channels.hud, channels.dashboard_cmd),
                drawn_on=DrawnOn(drawn_on, over_the_video=self._hud_surface is None,
                                 minus_on_the_hud=self._hud_surface is None),
                drive=DriveFeed(channels.drive, self._drive_gate, self._visualizer_for(channels)),
                row=self._row_press(), clock=self._setup.clock,
            )
        return None

    @staticmethod
    def _visualizer_for(channels: Channels) -> DrivePublisher | None:
        return None if channels.osr2_readout is None else DrivePublisher(channels.osr2_readout)

    def _row_press(self) -> RowPress:
        moved = self._setup.on_volume_moved
        return RowPress(seek=self._seek_along_the_track, seek_loop=self._seek_round_the_dial,
                        set_volume=told_to_the_host(self._volume.set_level, self._volume, moved),
                        toggle_mute=told_to_the_host(
                            self._volume.toggle_mute, self._volume, moved))

    def _seek_along_the_track(self, ms: float) -> None:
        frame = self._front.own_frame()
        if frame is not None:
            frame.seek_time(ms)
            return
        self._row.seek_along_the_track(ms)

    def _seek_round_the_dial(self, turn: float) -> None:
        frame = self._front.own_frame()
        if frame is not None:
            frame.seek_loop(turn)

    @classmethod
    def on_window(cls, wid: int, setup: FunestraSetup) -> Funestra:
        return cls(
            MpvEngine(wid, muted=setup.muted, loop_file=False, prefetch=True, audio=setup.audible),
            setup._replace(tcode=osr2_line(setup.channels)))

    def _where_the_hud_asks(self, channels: Channels) -> Callable[[str], None]:
        if channels.dashboard_cmd is not None:
            return partial(ask, channels.dashboard_cmd)
        return self.apply

    def _press_on_the_item(self, channels: Channels) -> Callable[[], None]:
        if channels.dashboard_cmd is not None:
            return lambda: ask(channels.dashboard_cmd, OMNIPAUSE_TOGGLE)
        return self._ask_what_runs_here_to_pause

    def _ask_what_runs_here_to_pause(self) -> None:
        self._runs_here.ask_to_pause()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def showing(self) -> str:
        return self._runs_here.showing

    @property
    def hud_edge(self) -> HudEdge:
        return HudEdge.LOWER if self._hud is None else self._hud.edge

    @property
    def hud_minimized(self) -> bool:
        return self._hud is not None and self._hud.minimized

    @property
    def outside_buttons(self) -> OutsideButtons | None:
        place = None if self._hud_surface is None else self._hud.hud_place
        return None if place is None else OutsideButtons(place.funestra, minimized=place.minimized,
                                                         flash=self._flash)

    def set_muted(self, muted: bool) -> None:
        self._volume.set_muted(muted)

    def set_volume(self, volume: VolumeHud) -> None:
        self._volume.set(volume.volume, volume.muted)

    def close_requested(self) -> None:
        if quit_gesture(self._channels.dashboard_cmd):
            self._stop.set()

    def press(self, x: int, y: int, *, viewport: tuple[int, int]) -> None:
        self._pointer.press(x, y)

    def release(self) -> None:
        self._pointer.release()

    def motion(self, x: int, y: int, *, held: bool, viewport: tuple[int, int]) -> None:
        self._pointer.motion(x, y, held=held)

    def wheel(self, x: int, y: int, steps: int, *, viewport: tuple[int, int]) -> None:
        self._pointer.wheel(x, y, steps)

    def leave(self) -> None:
        self._pointer.leave()

    def tick(self, *, viewport: tuple[int, int]) -> None:
        channels = self._channels
        if channels.paused is not None:
            self.playback.set_paused(read_paused_state(channels.paused, logger=logger))
        if channels.command is not None:
            for command in consume_command_file(channels.command, logger=logger, uppercase=False):
                self.apply(command)
        if self._follower is not None:
            self._follower.tick()
        self._runs_here.tick()
        self.playback.advance()
        if self._status is not None:
            self._status.write(self.playback)
        if self._setup.tiles:
            self._engine.tile_to_fill(*viewport)
        self._engine.push_still()
        self._tune_the_radio()
        self._paint_if_there_is_memory(viewport)

    def close(self) -> None:
        self._runs_here.close()
        if self._radio is not None:
            self._radio.close()
        self.playback.close()

    def _radio_beside(self, channels: Channels) -> Radio | None:
        if not self._setup.audible or channels.playlist is None:
            return None
        return Radio(self._engine.radio_station,
                     dealt_in=RadioFile(radio_file_for(channels.playlist)))

    def _tune_the_radio(self) -> None:
        if self._radio is None:
            return
        volume = self._volume.hud
        self._radio.tick(image=self._an_image_on_screen(),
                         level=None if volume.muted else volume.volume,
                         paused=self.playback.is_paused)

    def _an_image_on_screen(self) -> bool | None:
        if self.playback.showing_image:
            return True
        return False if self._engine.showing_video else None

    def apply(self, command: str) -> None:
        self.playback.follow_a_roll()
        if self._runs_here.apply(command) or self._setup.window_verbs(command):
            return
        if not look_up(command, VERBS, self._controls):
            logger.warning("Unhandled command: %s", command.strip())

    def take_the_list(self, items: list[PlaylistItem]) -> None:
        self.playback.follow_a_roll()
        self.playback.take_the_list(items)

    def _paint_if_there_is_memory(self, viewport: tuple[int, int]) -> None:
        try:
            self._paint(viewport)
        except MemoryError:
            if not self._short_of_memory:
                logger.warning("Out of memory drawing over the item; drawing it again on "
                               "the next frame")
            self._short_of_memory = True
        else:
            self._short_of_memory = False

    def _paint(self, viewport: tuple[int, int]) -> None:
        frame = self._front.own_frame()
        if frame is None:
            self._users_frames.hide()
            self._paint_hud(viewport, self.item_row(), self.strip.colors, self.playback.speed)
            if self._hud_surface is None:
                self._loop_frames.paint(
                    self.playback, self.strip,
                    None if self._hud is None else self._hud.row_track, viewport[0])
        else:
            self._users_frames.show(frame, viewport)
            self._paint_hud(viewport, frame_row(frame, self._volume.hud), None, 1.0)
            self._loop_frames.take_down()
        if self._corners is not None:
            self._corners.paint(viewport=viewport)

    def item_row(self) -> RowHud:
        return self._row.row(self._volume.hud, self._track_width())

    def _track_width(self) -> int:
        row = None if self._hud is None else self._hud.row
        return 0 if row is None else row.track[1] - row.track[0]

    def _paint_hud(self, viewport: tuple[int, int], row: RowHud | None, colors,
                   playback_speed: float) -> None:
        if self._hud is None:
            return
        item_row = None if row is None else ItemRowDraw(row, colors)
        if isinstance(self._hud, MainHudOverlay):
            self._flash = self._name_flash.showing(self._top_block().video)
            self._hud.tick(playback_speed=playback_speed, viewport=viewport,
                           item_row=item_row, flash=self._flash)
        else:
            video = self._front.top_block().video or self.playback.name_on_screen
            self._flash = self._name_flash.showing(video)
            self._hud.tick(video=video, playback_speed=playback_speed, viewport=viewport,
                           item_row=item_row, flash=self._flash)

