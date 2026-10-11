"""A window of Fun Time: it plays what it is handed, draws the HUD, the scrubber and the
volume over it -- or on a screen of the window's own beside it -- answers their presses,
and is driven through files by whatever runs on it."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol, runtime_checkable

from .console import ModeHud
from .console_overlay import ConsoleOverlay, HostBlock
from .control_registry import look_up
from .dashboard import ask
from .drive_gate import DriveGate
from .file_channel import consume_command_file, read_paused_state
from .flick_picture import FlickPicture, Picture
from .funestra_controls import VERBS, FunestraControls
from .funestra_status import status_fields
from .hud_corners import CORNER_PLUS_OVERLAY_ID, HudCorners
from .hud_overlay import HUD_OVERLAY_ID, HudOverlay
from .hud_placement import HudEdge
from .hud_row import RowHud
from .mpv_engine import MpvEngine
from .outside_buttons import OutsideButtons
from .play_points import PlayPoints
from .playback import Playback, funscripts_of
from .playhead import framed_playhead, video_playhead
from .playlist import PlaylistItem
from .playlist_follower import PlaylistFollower
from .pointer import OMNIPAUSE_TOGGLE, Pointer
from .satellite_hud import HudModel
from .scrubber import HeatmapStrip, LoopThumbCapture, loop_thumbnail_xys
from .session_quit import quit_gesture
from .status import StatusWriter
from .tcode import UdpTCodeSink
from .tcode_driver import FunscriptTCodeDriver
from .volume_control import RoomVolume, VolumeControl

__all__ = [
    "Channels",
    "Funestra",
    "PanelSurface",
    "User",
    "UsersPicture",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Channels:
    """The files a Funestra is driven through, and the inlet it drives the OSR2 from; each optional."""

    playlist: Path | None = None
    command: Path | None = None
    paused: Path | None = None
    status: Path | None = None
    play_points: Path | None = None
    hud: Path | None = None
    console: Path | None = None
    dashboard_cmd: Path | None = None
    drive: Path | None = None
    tcode_host: str | None = None
    tcode_port: int | None = None


@runtime_checkable
class User(Protocol):
    """What runs on a Funestra, as the Funestra sees it."""

    def apply_command(self, command: str) -> bool: ...

    def tick(self) -> None: ...

    def status_fields(self) -> Mapping[str, str]: ...

    def top_block(self) -> ModeHud: ...

    def set_showing(self, showing: bool) -> None: ...

    def picture(self) -> Picture | None: ...

    def close(self) -> None: ...


@runtime_checkable
class PanelSurface(Protocol):
    """A screen of the window's own that the panel is drawn on, beside the
    picture rather than over it, held to one width or sized to its contents."""

    width: int | None

    def overlay(self, ident: int, x: int, y: int, bgra) -> None: ...

    def remove_overlay(self, ident: int) -> None: ...


@runtime_checkable
class UsersPicture(Protocol):
    """Where a User's own picture goes up: over the engine's picture, as
    :class:`FlickPicture` tiles it, or wherever else the window shows one."""

    def show(self, picture: Picture, window: tuple[int, int]) -> None: ...

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

    def picture(self) -> Picture | None:
        return None

    def close(self) -> None:
        pass


NOBODY = ""

Users = Mapping[str, Callable[[Playback], User]]


def _nothing_of_its_own(_command: str) -> bool:
    return False


def osr2_line(channels: Channels) -> FunscriptTCodeDriver | None:
    if not channels.tcode_host or not channels.tcode_port:
        return None
    return FunscriptTCodeDriver(UdpTCodeSink(channels.tcode_host, channels.tcode_port))


class Funestra:
    IN_FRAME_OVERLAY_ID = 8
    OUT_FRAME_OVERLAY_ID = 9
    PANEL_OVERLAY_ID = HUD_OVERLAY_ID
    OVERLAY_IDS = (IN_FRAME_OVERLAY_ID, OUT_FRAME_OVERLAY_ID, PANEL_OVERLAY_ID,
                   CORNER_PLUS_OVERLAY_ID)

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
        users_picture: UsersPicture | None = None,
        window_verbs: Callable[[str], bool] = _nothing_of_its_own,
        host_block: HostBlock | None = None,
    ) -> None:
        self._engine = engine
        self._channels = channels
        self._tiles = tiles
        self._panel_surface = panel_surface
        self._window_verbs = window_verbs
        self._host_block = host_block
        self._stop = threading.Event()
        start_paused = (channels.paused is not None
                        and read_paused_state(channels.paused, logger=logger))
        self._playback = Playback(
            [item.path for item in playlist], engine=engine, start_paused=start_paused,
            locked=locked, play_points=PlayPoints(channels.play_points),
            funscripts=funscripts_of(playlist), tcode=tcode,
        )
        self._follower = (None if channels.playlist is None
                          else PlaylistFollower(channels.playlist, take=self._take_the_list))
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
        self._panel = self._panel_for(channels, panel_surface or engine, panel)
        self._users_picture = users_picture or FlickPicture(engine)
        self._corners = None if self._panel is None or panel_surface is not None else HudCorners(
            self._panel, engine, post=self._where_the_panel_asks(channels))
        self._pointer = Pointer(hud=self._panel, corners=self._corners,
                                picture=self._press_on_the_picture(channels))
        self._controls = FunestraControls(
            self.playback, stop_event=self._stop,
            reload_playlist=None if self._follower is None else self._follower.read_now,
            room_volume=self._volume if sound_is_the_rooms else None, show=self._show)
        self._status = (
            StatusWriter(channels.status, lambda playback: {
                **status_fields(playback, self._drive_gate.handoff_touch()),
                **{key: value for user in self._users.values()
                   for key, value in user.status_fields().items()}})
            if channels.status else None
        )
        self._loop_frames = LoopThumbCapture()
        self._loop_frames_up = False
        self._front.set_showing(True)

    @property
    def playback(self) -> Playback:
        return self._playback

    @property
    def _front(self) -> User:
        return self._users[self._showing]

    def _top_block(self) -> ModeHud:
        return self._front.top_block()

    def _panel_for(self, channels: Channels, drawn_on,
                   panel: Callable[[], HudModel | None] | None) -> HudOverlay | ConsoleOverlay | None:
        """The one panel this window wears, which carries the clip's row: the
        room's console on the main slot, the published HUD, or the window's
        own program's panel where no room publishes one.  Each places a press
        on the row itself, so each is handed what it asks of the window when
        one lands.
        """
        if channels.dashboard_cmd is None:
            if panel is None:
                return None
            return HudOverlay(
                panel=panel, post=self._apply, engine=drawn_on,
                minus_on_the_panel=self._panel_surface is None,
                seek=self._seek_along_the_track, seek_loop=self._seek_round_the_dial,
                set_volume=self._volume.set_level, toggle_mute=self._volume.toggle_mute,
            )
        if channels.console is not None:
            return ConsoleOverlay(
                console_file=channels.console, drive_file=channels.drive,
                command_file=channels.dashboard_cmd, engine=drawn_on,
                drive_gate=self._drive_gate, top_block=self._top_block,
                width=None if self._panel_surface is None else self._panel_surface.width,
                minus_on_the_panel=self._panel_surface is None,
                seek=self._seek_along_the_track, seek_loop=self._seek_round_the_dial,
                set_volume=self._volume.set_level, toggle_mute=self._volume.toggle_mute,
                host_block=self._host_block,
            )
        if channels.hud is not None:
            return HudOverlay(
                hud_file=channels.hud, command_file=channels.dashboard_cmd, engine=drawn_on,
                drive_file=channels.drive, drive_gate=self._drive_gate,
                over_the_video=self._panel_surface is None,
                minus_on_the_panel=self._panel_surface is None,
                seek=self._seek_along_the_track, seek_loop=self._seek_round_the_dial,
                set_volume=self._volume.set_level, toggle_mute=self._volume.toggle_mute,
            )
        return None

    def _seek_along_the_track(self, ms: float) -> None:
        """A press on the track names a time in the stretch the track spans,
        which is the whole clip until a loop being recorded zooms it in -- or,
        under a picture the User put up itself, how far into its time on
        screen that picture is."""
        picture = self._front.picture()
        if picture is not None:
            picture.seek_time(ms)
            return
        start_ms, _end_ms = self._strip.window
        self.playback.seek_to(start_ms + ms)

    def _seek_round_the_dial(self, turn: float) -> None:
        picture = self._front.picture()
        if picture is not None:
            picture.seek_loop(turn)

    @classmethod
    def on_window(cls, wid: int, *, channels: Channels, playlist: list[PlaylistItem],
                  audible: bool = True, tiles: bool = False, locked: bool = False,
                  sound_is_the_rooms: bool = False, users: Users | None = None,
                  panel: Callable[[], HudModel | None] | None = None,
                  muted: bool = True) -> Funestra:
        return cls(
            MpvEngine(wid, muted=muted, loop_file=False, prefetch=True),
            channels=channels, playlist=playlist, tcode=osr2_line(channels),
            audible=audible, tiles=tiles, locked=locked, sound_is_the_rooms=sound_is_the_rooms,
            users=users, panel=panel, muted=muted,
        )

    def _where_the_panel_asks(self, channels: Channels) -> Callable[[str], None]:
        if channels.dashboard_cmd is not None:
            return partial(ask, channels.dashboard_cmd)
        return self._apply

    def _press_on_the_picture(self, channels: Channels) -> Callable[[], None]:
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
        return None if place is None else OutsideButtons(place.funestra, minimized=place.minimized)

    def set_muted(self, muted: bool) -> None:
        self._volume.set_muted(muted)

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
                self._apply(command)
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
        self._paint(window)

    def close(self) -> None:
        for user in self._users.values():
            user.close()
        self.playback.close()

    def _apply(self, command: str) -> None:
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

    def _take_the_list(self, items: list[PlaylistItem]) -> None:
        self.playback.replace_playlist([item.path for item in items], funscripts_of(items))

    def _paint(self, window: tuple[int, int]) -> None:
        picture = self._front.picture()
        if picture is None:
            self._users_picture.hide()
            row = self.clip_row()
            self._paint_panel(window, row, self._strip.colors if row is not None else None,
                              self.playback.speed)
            if self._panel_surface is None:
                self._paint_loop_frames(window)
        else:
            self._users_picture.show(picture, window)
            self._paint_panel(window, picture_row(picture, self._volume.hud), None, 1.0)
            self._take_the_loop_frames_down()
        if self._corners is not None:
            self._corners.paint(window=window)

    def clip_row(self) -> RowHud | None:
        """Where the clip has got to, how long it runs, how loud it is and where
        its loop ends -- the row the panel carries at its foot, or None on a
        picture, which has nothing to run through.  Timed against the stretch
        the track spans, which is the whole clip until a loop being recorded
        zooms it in.
        """
        playback, engine = self.playback, self._engine
        self._strip.update(playback.showing, playback.current_funscript,
                           playback.duration_ms, self._track_width(),
                           mark_in_ms=playback.mark, position_ms=playback.position_ms)
        if playback.showing_picture:
            return None
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
            self._panel.tick(playback_speed=playback_speed, window=window,
                             clip_row=row, heatmap=colors)
        else:
            self._panel.tick(video=self._front.top_block().video or self.playback.name_on_screen,
                             playback_speed=playback_speed, window=window,
                             clip_row=row, heatmap=colors)

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


def picture_row(picture: Picture, volume) -> RowHud | None:
    """The row for a picture a User put up itself: its time on screen on the
    track, its loop on the dial, and the frame and the time read out between
    them, or None while there is none up."""
    if picture.count <= 0:
        return None
    return RowHud(position_ms=picture.elapsed_ms, duration_ms=picture.interval_ms,
                  volume=volume,
                  playhead=framed_playhead(picture.played, picture.count,
                                           picture.elapsed_ms, picture.interval_ms),
                  loop=(picture.played, picture.count))
