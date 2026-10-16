"""A window that plays what it is handed, draws the HUD, the scrubber and the
volume over it -- or on a screen of the window's own beside it -- answers their presses,
and is driven through files by whatever runs on it."""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol, runtime_checkable

from app_support.osr2_slot import Osr2Sender

from .console import ModeHud
from .console_overlay import ConsoleOverlay
from .control_registry import look_up
from .dashboard import ask
from .drive_gate import DriveGate
from .drive_readout import DrivePublisher
from .file_channel import consume_command_file, read_paused_state
from .flick_overlay import FlickFrame, FlickOverlay
from .funestra_controls import VERBS, FunestraControls
from .funestra_status import status_fields, volume_fields
from .funscript_jumps import FunscriptJumps
from .host_controls import HostControls
from .hud_corners import HudCorners
from .hud_minimize import NameFlash
from .hud_overlay import HudOverlay
from .hud_placement import HudEdge
from .hud_row import RowHud
from .mpv_engine import MpvEngine
from .notices import NoticeWriter
from .outside_buttons import OutsideButtons
from .play_points import PlayPoints
from .playback import Playback, funscripts_of, points_of_interest_of
from .playhead import framed_playhead, time_playhead, video_playhead
from .playlist import PlaylistItem
from .playlist_follower import PlaylistFollower
from .pointer import OMNIPAUSE_TOGGLE, Pointer
from .radio import Radio, RadioFile, Tuner, radio_file_for
from .renamed import keyword_of, method_of, old_name_getter, value_of
from .satellite_hud import HudModel
from .scrubber import HeatmapStrip, LoopThumbCapture, loop_thumbnail_xys
from .session_quit import quit_gesture
from .status import StatusWriter
from .tcode import UdpTCodeSink
from .tcode_driver import FunscriptTCodeDriver
from .volume import VolumeHud
from .volume_control import RoomVolume, VolumeControl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Channels:
    """The files a Funestra is driven through, and the inlet it drives the OSR2 from; each optional."""

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
class User(Protocol):
    """What runs on a Funestra, as the Funestra sees it."""

    def apply_command(self, command: str) -> bool: ...

    def tick(self) -> None: ...

    def status_fields(self) -> Mapping[str, str]: ...

    def top_block(self) -> ModeHud: ...

    def set_showing(self, showing: bool) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class PanelSurface(Protocol):
    """A screen of the window's own that the panel is drawn on, beside the
    item rather than over it, held to one width or sized to its contents."""

    width: int | None

    def overlay(self, ident: int, x: int, y: int, bgra) -> None: ...

    def remove_overlay(self, ident: int) -> None: ...


@runtime_checkable
class UsersFrames(Protocol):
    """Where a User's own frame goes up: over the engine's item, as
    :class:`FlickOverlay` tiles it, or wherever else the window shows one."""

    def show(self, frame: FlickFrame, window: tuple[int, int]) -> None: ...

    def hide(self) -> None: ...


class _Nobody:
    """A Funestra driven through its files alone."""

    def apply_command(self, command: str) -> bool:
        return False

    def tick(self) -> None:
        pass

    def status_fields(self) -> Mapping[str, str]:
        return {}

    def top_block(self) -> ModeHud:
        return ModeHud()

    def set_showing(self, showing: bool) -> None:
        pass

    def own_frame(self) -> FlickFrame | None:
        return None

    def close(self) -> None:
        pass


NOBODY = ""

Users = Mapping[str, Callable[[Playback], User]]


def _nothing_of_its_own(_command: str) -> bool:
    return False


def osr2_line(channels: Channels) -> FunscriptTCodeDriver | None:
    if channels.osr2_sender:
        return FunscriptTCodeDriver(Osr2Sender(channels.osr2_sender, port=channels.osr2_port))
    if not channels.tcode_host or not channels.tcode_port:
        return None
    return FunscriptTCodeDriver(UdpTCodeSink(channels.tcode_host, channels.tcode_port))


class Funestra:
    IN_FRAME_OVERLAY_ID = 8
    OUT_FRAME_OVERLAY_ID = 9

    def __init__(
        self,
        engine,
        *,
        channels: Channels,
        playlist: list[PlaylistItem],
        tcode=None,
        audible: bool = True,
        tiles: bool = False,
        locked: bool = False,
        sound_is_the_rooms: bool = False,
        users: Users | None = None,
        panel: Callable[[], HudModel | None] | None = None,
        muted: bool = True,
        panel_surface: PanelSurface | None = None,
        users_frames: UsersFrames | None = None,
        window_verbs: Callable[[str], bool] = _nothing_of_its_own,
        host_controls: HostControls | None = None,
        radio: Tuner | None = None,
        on_volume_moved: Callable[[VolumeHud], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        users_picture: UsersFrames | None = None,
    ) -> None:
        self._engine = engine
        self._clock = clock
        self._volume_moved = on_volume_moved
        self._channels = channels
        self._tiles = tiles
        self._panel_surface = panel_surface
        self._window_verbs = window_verbs
        self._host_controls = host_controls
        self._stop = threading.Event()
        start_paused = (channels.paused is not None
                        and read_paused_state(channels.paused, logger=logger))
        self._playback = Playback(
            [item.path for item in playlist], engine=engine, start_paused=start_paused,
            locked=locked, play_points=PlayPoints(channels.play_points),
            funscripts=funscripts_of(playlist), points_of_interest=points_of_interest_of(playlist),
            tcode=tcode,
        )
        self._follower = (None if channels.playlist is None
                          else PlaylistFollower(channels.playlist, take=self.take_the_list))
        self._users: dict[str, User] = (
            {NOBODY: _Nobody()} if not users
            else {name: make(self.playback) for name, make in users.items()})
        self._showing = next(iter(self._users))
        self._drive_gate = DriveGate(self.playback)
        self._strip = HeatmapStrip()
        self._volume = (
            RoomVolume(engine, dashboard_cmd_file=channels.dashboard_cmd, live=audible)
            if sound_is_the_rooms else VolumeControl(engine, live=audible, muted=muted)
        )
        self._radio = radio if radio is not None else self._radio_beside(channels, audible)
        self._panel = self._panel_for(channels, panel_surface or engine, panel)
        self._name_flash = NameFlash(clock)
        self._flash = ""
        self._users_frames = users_frames or users_picture or FlickOverlay(engine)
        self._corners = None if self._panel is None or panel_surface is not None else HudCorners(
            self._panel, engine, post=self._where_the_panel_asks(channels))
        self._pointer = Pointer(hud=self._panel, corners=self._corners,
                                item=self._press_on_the_item(channels))
        self._controls = FunestraControls(
            self.playback, stop_event=self._stop,
            reload_playlist=None if self._follower is None else self._follower.read_now,
            volume=self._volume, show=self._show,
            funscript_jumps=FunscriptJumps(self.playback, NoticeWriter(channels.notice)))
        self._status = (
            StatusWriter(channels.status, lambda _playback: self.status_fields())
            if channels.status else None
        )
        self._loop_frames = LoopThumbCapture()
        self._loop_frames_up = False
        self._short_of_memory = False
        self._front.set_showing(True)

    @property
    def playback(self) -> Playback:
        return self._playback

    def status_fields(self) -> dict[str, str]:
        return {
            **status_fields(self.playback, self._drive_gate.handoff_touch()),
            **volume_fields(self._volume.hud),
            **{key: value for user in self._users.values()
               for key, value in user.status_fields().items()}}

    @property
    def _front(self) -> User:
        return self._users[self._showing]

    def _top_block(self) -> ModeHud:
        return self._front.top_block()

    def _panel_for(self, channels: Channels, drawn_on,
                   panel: Callable[[], HudModel | None] | None) -> HudOverlay | ConsoleOverlay | None:
        """The one panel this window wears, which carries the item's row: the
        room's console on the main slot, the published HUD, or the window's
        own program's panel where no room publishes one.  Each places a press
        on the row itself, so each is handed what it asks of the window when
        one lands.
        """
        if channels.dashboard_cmd is None:
            if panel is None:
                return None
            return HudOverlay(
                panel=panel, post=self.apply, engine=drawn_on,
                minus_on_the_panel=self._panel_surface is None,
                seek=self._seek_along_the_track, seek_loop=self._seek_round_the_dial,
                **self._volume_presses(),
            )
        if channels.console is not None:
            return ConsoleOverlay(
                console_file=channels.console, drive_file=channels.drive,
                command_file=channels.dashboard_cmd, engine=drawn_on,
                drive_gate=self._drive_gate, top_block=self._top_block,
                width=None if self._panel_surface is None else self._panel_surface.width,
                minus_on_the_panel=self._panel_surface is None,
                seek=self._seek_along_the_track, seek_loop=self._seek_round_the_dial,
                **self._volume_presses(),
                host_controls=self._host_controls,
                readout=self._readout_for(channels), clock=self._clock,
            )
        if channels.hud is not None:
            return HudOverlay(
                hud_file=channels.hud, command_file=channels.dashboard_cmd, engine=drawn_on,
                drive_file=channels.drive, drive_gate=self._drive_gate,
                readout=self._readout_for(channels), clock=self._clock,
                over_the_video=self._panel_surface is None,
                minus_on_the_panel=self._panel_surface is None,
                seek=self._seek_along_the_track, seek_loop=self._seek_round_the_dial,
                **self._volume_presses(),
            )
        return None

    @staticmethod
    def _readout_for(channels: Channels) -> DrivePublisher | None:
        return None if channels.osr2_readout is None else DrivePublisher(channels.osr2_readout)

    def _volume_presses(self) -> dict[str, Callable[..., None]]:
        return {"set_volume": self._told_to_the_host(self._volume.set_level),
                "toggle_mute": self._told_to_the_host(self._volume.toggle_mute)}

    def _told_to_the_host(self, move: Callable[..., None]) -> Callable[..., None]:
        def moved(*args) -> None:
            move(*args)
            if self._volume_moved is not None:
                self._volume_moved(self._volume.hud)
        return moved

    def _seek_along_the_track(self, ms: float) -> None:
        """A press on the track names a time in the stretch the track spans,
        which is the whole clip until a loop being recorded zooms it in -- or,
        under an image, how far into its time on screen that image is."""
        frame = method_of(self._front, "own_frame", old_name="picture")()
        if frame is not None:
            frame.seek_time(ms)
            return
        if self.playback.showing_image:
            method_of(self._engine, "seek_image", old_name="seek_picture")(ms)
            return
        start_ms, _end_ms = self._strip.window
        self.playback.seek_to(start_ms + ms)

    def _seek_round_the_dial(self, turn: float) -> None:
        frame = method_of(self._front, "own_frame", old_name="picture")()
        if frame is not None:
            frame.seek_loop(turn)

    @classmethod
    def on_window(cls, wid: int, *, channels: Channels, playlist: list[PlaylistItem],
                  audible: bool = True, tiles: bool = False, locked: bool = False,
                  sound_is_the_rooms: bool = False, users: Users | None = None,
                  panel: Callable[[], HudModel | None] | None = None,
                  muted: bool = True) -> Funestra:
        return cls(
            MpvEngine(wid, muted=muted, loop_file=False, prefetch=True, audio=audible),
            channels=channels, playlist=playlist, tcode=osr2_line(channels),
            audible=audible, tiles=tiles, locked=locked, sound_is_the_rooms=sound_is_the_rooms,
            users=users, panel=panel, muted=muted,
        )

    def _where_the_panel_asks(self, channels: Channels) -> Callable[[str], None]:
        if channels.dashboard_cmd is not None:
            return partial(ask, channels.dashboard_cmd)
        return self.apply

    def _press_on_the_item(self, channels: Channels) -> Callable[[], None]:
        """What a press off the panel does: in a session it asks the room to
        pause everything; on a window with no room to ask, what runs on the
        window is asked instead."""
        if channels.dashboard_cmd is not None:
            return lambda: ask(channels.dashboard_cmd, OMNIPAUSE_TOGGLE)
        return self._ask_what_runs_here_to_pause

    def _ask_what_runs_here_to_pause(self) -> None:
        for user in self._users.values():
            if user.apply_command(OMNIPAUSE_TOGGLE):
                return

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def showing(self) -> str:
        return self._showing

    @property
    def panel_edge(self) -> HudEdge:
        return HudEdge.LOWER if self._panel is None else self._panel.edge

    @property
    def panel_minimized(self) -> bool:
        return self._panel is not None and self._panel.minimized

    @property
    def outside_buttons(self) -> OutsideButtons | None:
        place = None if self._panel_surface is None else self._panel.hud_place
        return None if place is None else OutsideButtons(place.funestra, minimized=place.minimized,
                                                         flash=self._flash)

    def set_muted(self, muted: bool) -> None:
        self._volume.set_muted(muted)

    def set_volume(self, volume: VolumeHud) -> None:
        self._volume.set(volume.volume, volume.muted)

    def close_requested(self) -> None:
        if quit_gesture(self._channels.dashboard_cmd):
            self._stop.set()

    def press(self, x: int, y: int, *, window: tuple[int, int]) -> None:
        self._pointer.press(x, y)

    def release(self) -> None:
        self._pointer.release()

    def motion(self, x: int, y: int, *, held: bool, window: tuple[int, int]) -> None:
        self._pointer.motion(x, y, held=held)

    def wheel(self, x: int, y: int, steps: int, *, window: tuple[int, int]) -> None:
        self._pointer.wheel(x, y, steps)

    def leave(self) -> None:
        self._pointer.leave()

    def tick(self, *, window: tuple[int, int]) -> None:
        channels = self._channels
        if channels.paused is not None:
            self.playback.set_paused(read_paused_state(channels.paused, logger=logger))
        if channels.command is not None:
            for command in consume_command_file(channels.command, logger=logger, uppercase=False):
                self.apply(command)
        if self._follower is not None:
            self._follower.tick()
        for user in self._users.values():
            user.tick()
        self.playback.advance()
        if self._status is not None:
            self._status.write(self.playback)
        if self._tiles:
            self._engine.tile_to_fill(*window)
        self._engine.push_still()
        self._tune_the_radio()
        self._paint_if_there_is_memory(window)

    def close(self) -> None:
        for user in self._users.values():
            user.close()
        if self._radio is not None:
            self._radio.close()
        self.playback.close()

    def _radio_beside(self, channels: Channels, audible: bool) -> Radio | None:
        if not audible or channels.playlist is None:
            return None
        return Radio(self._engine.radio_station,
                     dealt_in=RadioFile(radio_file_for(channels.playlist)))

    def _tune_the_radio(self) -> None:
        if self._radio is None:
            return
        volume = self._volume.hud
        self._radio.tick(**{keyword_of(self._radio.tick, "image", old_name="picture"): self._an_image_on_screen()},
                         level=None if volume.muted else volume.volume,
                         paused=self.playback.is_paused)

    def _an_image_on_screen(self) -> bool | None:
        """True for an image, False for a video, None between two files."""
        if self.playback.showing_image:
            return True
        return False if self._engine.showing_video else None

    def apply(self, command: str) -> None:
        self.playback.follow_a_roll()
        for user in self._users.values():
            if user.apply_command(command):
                return
        if self._window_verbs(command):
            return
        if not look_up(command, VERBS, self._controls):
            logger.warning("Unhandled command: %s", command.strip())

    def _show(self, name: str) -> bool:
        if name not in self._users:
            return False
        if name != self._showing:
            self._front.set_showing(False)
            self._showing = name
            self._front.set_showing(True)
        return True

    def take_the_list(self, items: list[PlaylistItem]) -> None:
        self.playback.follow_a_roll()
        self.playback.take_the_list(items)

    def _paint_if_there_is_memory(self, window: tuple[int, int]) -> None:
        try:
            self._paint(window)
        except MemoryError:
            if not self._short_of_memory:
                logger.warning("Out of memory drawing over the item; drawing it again on "
                               "the next frame")
            self._short_of_memory = True
        else:
            self._short_of_memory = False

    def _paint(self, window: tuple[int, int]) -> None:
        frame = method_of(self._front, "own_frame", old_name="picture")()
        if frame is None:
            self._users_frames.hide()
            self._paint_panel(window, self.item_row(), self._strip.colors, self.playback.speed)
            if self._panel_surface is None:
                self._paint_loop_frames(window)
        else:
            self._users_frames.show(frame, window)
            self._paint_panel(window, frame_row(frame, self._volume.hud), None, 1.0)
            self._take_the_loop_frames_down()
        if self._corners is not None:
            self._corners.paint(window=window)

    def item_row(self) -> RowHud:
        """Where the item on screen has got to, how long it runs, how loud it
        is and where its loop ends -- the row the panel carries at its foot.  An
        image runs for the time it holds the screen.  A video is timed
        against the stretch the track spans, which is the whole video until a
        loop being recorded zooms it in.
        """
        playback, engine = self.playback, self._engine
        self._strip.update(playback.showing, playback.current_funscript,
                           playback.duration_ms, self._track_width(),
                           mark_in_ms=playback.mark, position_ms=playback.position_ms)
        if playback.showing_image:
            elapsed_ms, pace_ms = value_of(engine, "image_time", old_name="picture_time") or (0.0, 0.0)
            return RowHud(position_ms=elapsed_ms, duration_ms=pace_ms, volume=self._volume.hud,
                          playhead=time_playhead(elapsed_ms, pace_ms))
        start_ms, end_ms = self._strip.window
        bounds = playback.ab_loop
        return RowHud(
            position_ms=playback.position_ms - start_ms,
            duration_ms=end_ms - start_ms,
            volume=self._volume.hud,
            playhead=video_playhead(playback.position_ms, playback.duration_ms,
                                    engine.frame_rate),
            loop_bounds=None if bounds is None else (bounds[0] - start_ms,
                                                     bounds[1] - start_ms),
            record_in_ms=None if playback.mark is None else playback.mark - start_ms,
        )

    def _track_width(self) -> int:
        """How wide the panel drew the track last frame, which is what the
        colors have to cover.  A panel is as wide as what is on it, so there is
        no answer until one has been drawn: 0 leaves the first row plain.
        """
        row = None if self._panel is None else self._panel.row
        return 0 if row is None else row.track[1] - row.track[0]

    def _paint_panel(self, window: tuple[int, int], row: RowHud | None, colors,
                     playback_speed: float) -> None:
        if self._panel is None:
            return
        if isinstance(self._panel, ConsoleOverlay):
            self._flash = self._name_flash.showing(self._top_block().video)
            self._panel.tick(playback_speed=playback_speed, window=window,
                             item_row=row, heatmap=colors, flash=self._flash)
        else:
            video = self._front.top_block().video or self.playback.name_on_screen
            self._flash = self._name_flash.showing(video)
            self._panel.tick(video=video, playback_speed=playback_speed, window=window,
                             item_row=row, heatmap=colors, flash=self._flash)

    def _paint_loop_frames(self, window: tuple[int, int]) -> None:
        """The loop's in and out frames, each hanging under the panel below its
        own mark on the track."""
        playback, engine, frames = self.playback, self._engine, self._loop_frames
        which = frames.needed(playback.ab_loop, playback.position_ms)
        if which is not None:
            frames.set(which, engine.screenshot_bgra())
        track = None if self._panel is None else self._panel.row_track
        if playback.ab_loop is None or track is None:
            self._take_the_loop_frames_down()
            return
        x0, x1, top = track
        in_at, out_at = loop_thumbnail_xys(
            self._strip, frames, playback.ab_loop,
            track=(x0, x1), win_w=window[0], top=top)
        if in_at is not None:
            engine.overlay(self.IN_FRAME_OVERLAY_ID, *in_at, frames.in_thumb)
            self._loop_frames_up = True
        if out_at is not None:
            engine.overlay(self.OUT_FRAME_OVERLAY_ID, *out_at, frames.out_thumb)
            self._loop_frames_up = True

    def _take_the_loop_frames_down(self) -> None:
        if not self._loop_frames_up:
            return
        self._loop_frames_up = False
        self._engine.remove_overlay(self.IN_FRAME_OVERLAY_ID)
        self._engine.remove_overlay(self.OUT_FRAME_OVERLAY_ID)


def frame_row(frame: FlickFrame, volume) -> RowHud | None:
    """The row for a frame a User put up itself: its time on screen on the
    track, its loop on the dial, and the frame and the time read out between
    them, or None while there is none up."""
    if frame.count <= 0:
        return None
    return RowHud(position_ms=frame.elapsed_ms, duration_ms=frame.interval_ms,
                  volume=volume,
                  playhead=framed_playhead(frame.played, frame.count,
                                           frame.elapsed_ms, frame.interval_ms),
                  loop=(frame.played, frame.count))


__getattr__ = old_name_getter(__name__, {"UsersPicture": "UsersFrames"})
