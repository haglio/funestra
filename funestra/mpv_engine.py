from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes
import functools
import importlib
import logging
import math
import os
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .audio_outputs import Output, pick_output
from .ken_burns import Fit, KenBurns, Moves, View
from .libmpv_loader import add_libmpv_to_path, libmpv_dirs
from .lost_gpu import LostGpu
from .mpv_gate import CallGate, mpv_call

logger = logging.getLogger(__name__)

# mpv's Lua scripts are off: one erroring on the way out takes a host process down.
_MPV_SCRIPTS_OFF = {
    "osc": "no",
    "load_scripts": "no",
    "load_stats_overlay": "no",
    "load_osd_console": "no",
    "load_auto_profiles": "no",
    "load_select": "no",
    "load_positioning": "no",
    "load_commands": "no",
    "ytdl": "no",
}

# mpv fails without raising: a file it cannot open leaves a black window over a healthy process.
# Its own messages are logged, warnings and worse only; at info mpv narrates every file it opens.
_MPV_LEVELS = {"fatal": logging.CRITICAL, "error": logging.ERROR, "warn": logging.WARNING}


_RIDDEN_OUT_BY_MPV = frozenset({
    "Audio device underrun detected.",
    "Audio/Video desynchronisation detected! Possible reasons include too slow",
    "hardware, temporary CPU spikes, broken drivers, and broken files. Audio",
    "position will not match to the video (see A-V status field).",
    "Consider trying `--profile=fast` and/or `--hwdec=auto` as they may help.",
})


def _log_mpv(level: str, prefix: str, text: str) -> None:
    said = text.strip()
    if not said:
        return
    at =logging.INFO if said in _RIDDEN_OUT_BY_MPV else _MPV_LEVELS.get(level, logging.WARNING)
    logger.log(at, "mpv %s: %s", prefix, said)


_TRIES_AT_THE_ENGINE = 5


def _import_mpv():
    return _import_the_engine(importlib.import_module)


def _import_the_engine(load, tries: int = _TRIES_AT_THE_ENGINE):
    # vosk rewrites PATH from a read taken before ours, which drops libmpv's folder; ask again.
    last = None
    for attempt in range(1, tries + 1):
        add_libmpv_to_path()
        try:
            return load("mpv")
        except OSError as refused:
            last = refused
            if attempt == tries:
                break
    raise OSError(f"The engine (libmpv) could not be loaded. {_where_it_looked()}") from last


def _where_it_looked() -> str:
    answers = []
    for folder in libmpv_dirs():
        try:
            answers.append(f"{folder} ({'holds libmpv-2.dll' if (folder / 'libmpv-2.dll').is_file() else 'no libmpv-2.dll in it'})")
        except OSError as refused:
            answers.append(f"{folder} (could not be looked in: {refused})")
    front = os.environ.get("PATH", "").split(os.pathsep)[:3]
    return f"Looked in: {', '.join(answers)}. PATH starts: {front}"


def _shared_options(*, muted: bool, loop_file: bool, prefetch: bool, audio: bool = True) -> dict:
    options = dict(
        # python-mpv's own two keywords, not mpv options.
        log_handler=_log_mpv,
        loglevel="warn",
        hwdec="auto-safe",
        loop_file="inf" if loop_file else "no",
        keep_open="yes",
        mute="yes" if muted else "no",
        # mpv's clock follows audio, so an audio device that cannot open would freeze the video.
        audio_fallback_to_null="yes",
        **_MPV_SCRIPTS_OFF,
        input_default_bindings=False,
        image_display_duration="inf",
        video_recenter="yes",
    )
    if prefetch:
        options["prefetch_playlist"] = "yes"
    if not audio:
        options["aid"] = "no"
    return options


TILES_SHADER = Path(__file__).with_name("tiles.glsl")

# mpv's video/out/aspect.c places an overhanging image from -1 (flush with one edge) to +1.
_PLACING = ("video_zoom", "video_align_x", "video_align_y")


def tiles_across(source: tuple[int, int], viewport: tuple[int, int]) -> int:
    source_width, source_height = source
    viewport_width, viewport_height = viewport
    if source_width >= source_height or viewport_width <= viewport_height:
        return 1
    return viewport_width * source_height // (viewport_height * source_width)


# A property read can wait on mpv's core lock for hundreds of milliseconds while a file opens.
CLOSE_DRAIN_TIMEOUT_S = 10.0


_APTTYPEQUALIFIER_IMPLICIT_MTA = 1

_Corners = ctypes.wintypes.LONG * 4


@functools.cache
def _user32():
    user32 = ctypes.WinDLL("user32")
    user32.GetClientRect.argtypes = (ctypes.wintypes.HWND, ctypes.POINTER(_Corners))
    user32.GetClientRect.restype = ctypes.wintypes.BOOL
    return user32


def _client_size(hwnd: int) -> tuple[int, int]:
    corners = _Corners()
    if not _user32().GetClientRect(hwnd, ctypes.byref(corners)):
        return 0, 0
    x0, y0, x1, y1 = corners
    return x1 - x0, y1 - y0


def _holds_a_com_apartment() -> bool:
    kind, qualifier = ctypes.c_int(), ctypes.c_int()
    hr = ctypes.windll.ole32.CoGetApartmentType(ctypes.byref(kind), ctypes.byref(qualifier))
    return hr == 0 and qualifier.value != _APTTYPEQUALIFIER_IMPLICIT_MTA


def _terminate_outside_the_callers_apartment(handle) -> None:
    # libmpv's WASAPI output ends with an unpaired CoUninitialize on the terminating thread,
    # which takes a Qt GUI thread's drag and drop with it.
    def terminate() -> None:
        with contextlib.suppress(Exception):
            handle.terminate()

    if not _holds_a_com_apartment():
        terminate()
        return
    teardown = threading.Thread(target=terminate, name="mpv-teardown")
    teardown.start()
    teardown.join()


class _MpvControl:
    _mpv: object

    def __init__(self, moves: Moves | None = None, *, looping: bool = False) -> None:
        self._gate = CallGate()
        self._frame_rate = 0.0
        self._image_track: bool | None = None
        self._overlays: dict[int, np.ndarray] = {}
        # mpv leaves an image's playhead at 0, so a clock of our own paces it.
        self._ken_burns = KenBurns(moves, looping=looping, fit=self._fit)
        self._viewport = (0, 0)
        self._placed = (0.0, 0.0, 0.0)
        self._path: str | None = None
        self._on_the_clock: str | None = None
        self._image_time = (0.0, 0.0)
        self._audio_device: str | None = None
        self._staged: str | None = None
        self._video_dims = (0, 0)
        self._source_dims = (0, 0)
        self._tiling = (1, "no")

    def _adopt(self, handle) -> None:
        self._mpv = handle
        handle.observe_property("container-fps", self._note_frame_rate)
        handle.observe_property("current-tracks/video/image", self._note_image_track)
        handle.observe_property("path", self._note_file)
        # mpv's video-out-params, not dwidth and dheight, so both numbers land in one event; watched,
# not read, since a property read waits on mpv's core lock, which a file being opened holds for
# hundreds of milliseconds.
        handle.observe_property("video-out-params", self._note_video_dims)
        handle.observe_property("video-dec-params", self._note_source_dims)

    def _note_frame_rate(self, _name: str, value) -> None:
        self._frame_rate = value or 0.0

    def _note_image_track(self, _name: str, value) -> None:
        self._image_track = value

    def _note_file(self, _name: str, path) -> None:
        self._path = path

    def _note_video_dims(self, _name: str, value) -> None:
        if isinstance(value, dict):
            self._video_dims = (int(value.get("dw") or 0), int(value.get("dh") or 0))
        else:
            self._video_dims = (0, 0)

    def _note_source_dims(self, _name: str, value) -> None:
        if isinstance(value, dict) and value.get("dw") and value.get("dh"):
            self._source_dims = (int(value["dw"]), int(value["dh"]))

    @property
    def source_dims(self) -> tuple[int, int]:
        return self._source_dims

    @mpv_call()
    def tile_to_fill(self, viewport_width: int, viewport_height: int) -> None:
        tiles = tiles_across(self._source_dims, (viewport_width, viewport_height))
        tiling = (tiles, self._tiled_aspect(tiles))
        if tiling == self._tiling:
            return
        if tiles > 1:
            self._mpv.command("change-list", "glsl-shaders", "set", str(TILES_SHADER))
            self._mpv.command("change-list", "glsl-shader-opts", "set", f"tiles={tiles}")
        else:
            self._mpv.command("change-list", "glsl-shaders", "clr", "")
        self._mpv.video_aspect_override = tiling[1]
        self._tiling = tiling

    def _tiled_aspect(self, tiles: int) -> str:
        if tiles == 1:
            return "no"
        source_width, source_height = self._source_dims
        common = math.gcd(tiles * source_width, source_height)
        return f"{tiles * source_width // common}:{source_height // common}"

    @property
    def video_dims(self) -> tuple[int, int]:
        return self._video_dims

    def _now(self) -> float:
        return time.monotonic()

    @property
    def frame_rate(self) -> float:
        return self._frame_rate

    @property
    def showing_image(self) -> bool:
        return self._image_track is True

    @property
    def showing_video(self) -> bool:
        return self._image_track is False

    @mpv_call()
    def load(self, path: Path) -> None:
        self._staged = None
        self._begin_the_new_clip(str(path))
        self._mpv.play(str(path))
        self._mpv.playlist_clear()

    @mpv_call()
    def swap_image(self, path: Path) -> None:
        self._on_the_clock = str(path)
        self._mpv.play(str(path))
        self._mpv.playlist_clear()
        if self._staged is not None:
            self._mpv.loadfile(self._staged, "append")

    # mpv's playlist-clear resolves "current" itself; removing by an index read earlier
    # can take the playing entry out from under it.
    @mpv_call()
    def stop(self) -> None:
        # Windows refuses to move a file the engine still holds open.
        self._staged = None
        self._mpv.command("stop")

    @mpv_call()
    def stage_next(self, path: Path) -> None:
        if str(path) == self._staged:
            return
        self._mpv.playlist_clear()
        self._mpv.loadfile(str(path), "append")
        self._staged = str(path)

    @mpv_call()
    def clear_next(self) -> None:
        self._staged = None
        self._mpv.playlist_clear()

    @property
    @mpv_call(False)
    def advanced_to_next(self) -> bool:
        pos = self._mpv.playlist_pos
        return pos is not None and pos >= 1

    @mpv_call()
    def settle_on_the_next(self) -> None:
        # mpv leaves the spent entry first in its playlist after rolling onto the next one;
        # clearing drops it and the current one plays on.
        rolled_onto, self._staged = self._staged, None
        self._mpv.playlist_clear()
        self._begin_the_new_clip(rolled_onto)

    def _begin_the_new_clip(self, path: str | None) -> None:
        self._on_the_clock = path
        self._ken_burns.new_image(self._now())

    @property
    @mpv_call(False)
    def idle(self) -> bool:
        # mpv raises nothing for a file it cannot demux; it ends up with nothing playing.
        return bool(self._mpv.idle_active)

    @property
    @mpv_call(0.0)
    def position_ms(self) -> float:
        return (self._mpv.time_pos or 0.0) * 1000.0

    @property
    @mpv_call(0.0)
    def duration_ms(self) -> float:
        return (self._mpv.duration or 0.0) * 1000.0

    @mpv_call()
    def set_paused(self, paused: bool) -> None:
        self._ken_burns.set_paused(paused, self._now())
        self._mpv.pause = paused

    def set_pace(self, seconds: float) -> None:
        self._ken_burns.set_pace(seconds or 0.0, self._now())

    def set_points_of_interest(self, places: tuple) -> None:
        self._ken_burns.set_points_of_interest(places, self._now())

    def _fit(self) -> Fit:
        return Fit(self._viewport_size(), self._video_dims, self._tiling[0])

    def _viewport_size(self) -> tuple[int, int]:
        return self._viewport

    @mpv_call()
    def push_still(self) -> None:
        if self._image_track is None:
            return
        now = self._now()
        view = self._ken_burns.view(now) if self._image_track else View()
        placed = view.placement()
        for name, value, was in zip(_PLACING, placed, self._placed, strict=True):
            if value != was:
                setattr(self._mpv, name, value)
        self._placed = placed
        holds_for_ms = self._ken_burns.holds_for_s * 1000.0
        self._image_time = (min(self._ken_burns.progress(now) * self._ken_burns.pace_s * 1000.0,
                                holds_for_ms), holds_for_ms)
        if self._image_track and self._path == self._on_the_clock and self._ken_burns.ran_out(now):
            self._move_on_from_the_image()

    @property
    def image_time(self) -> tuple[float, float] | None:
        return self._image_time if self._image_track else None

    def hold_image_for(self, seconds: float | None) -> None:
        self._ken_burns.hold_for(seconds)

    def seek_image(self, ms: float) -> None:
        pace_s = self._ken_burns.pace_s
        if pace_s:
            self._ken_burns.seek(ms / 1000.0 / pace_s, self._now())

    def _move_on_from_the_image(self) -> None:
        if self._staged is not None:
            self._on_the_clock = None
            self._mpv.command("playlist-next")

    @mpv_call()
    def set_loop_file(self, loop: bool) -> None:
        self._ken_burns.set_looping(loop, self._now())
        self._mpv.loop_file = "inf" if loop else "no"

    @mpv_call()
    def set_speed(self, speed: float) -> None:
        # mpv's time_pos clock advances at this rate, so a funscript read off it keeps step.
        self._mpv.speed = speed

    @mpv_call()
    def set_volume(self, volume: int) -> None:
        # mpv's volume and mute are separate properties, so this never unmutes a muted engine.
        self._mpv.volume = volume

    @mpv_call()
    def set_muted(self, muted: bool) -> None:
        self._mpv.mute = muted

    @mpv_call()
    def set_audio_device_matching(self, substring: str) -> str | None:
        outputs = [Output(str(device.get("description") or device["name"]), device["name"])
                   for device in self._mpv.audio_device_list or []]
        picked = pick_output(outputs, substring)
        if picked is None:
            return None
        self._mpv.audio_device = self._audio_device = picked.handle
        return picked.label

    def radio_station(self, videos: Sequence[Path]) -> MpvStation | None:
        return MpvStation.opened(videos, audio_device=self._audio_device)

    @mpv_call()
    def seek_ms(self, ms: float) -> None:
        self._mpv.command("seek", max(0.0, ms) / 1000.0, "absolute", "exact")

    @mpv_call()
    def set_ab_loop(self, in_ms: float, out_ms: float) -> None:
        self._mpv.ab_loop_a = in_ms / 1000.0
        self._mpv.ab_loop_b = out_ms / 1000.0

    @mpv_call()
    def clear_ab_loop(self) -> None:
        self._mpv.ab_loop_a = "no"
        self._mpv.ab_loop_b = "no"

    @mpv_call()
    def screenshot_bgra(self, height: int = 64):
        try:
            img = self._mpv.screenshot_raw()
        except SystemError:  # python-mpv's word for a command mpv refused: no frame to take
            return None
        if img is None or img.height == 0:
            return None
        w = max(1, round(height * img.width / img.height))
        arr = np.asarray(img.convert("RGBA").resize((w, height)))
        return np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]], dtype=np.uint8)

    @mpv_call()
    def overlay(self, ident: int, x: int, y: int, bgra) -> None:
        arr = np.ascontiguousarray(bgra, dtype=np.uint8)
        h, w = arr.shape[:2]
        try:
            self._mpv.overlay_add(
                ident, x, y, "&" + str(arr.ctypes.data), 0, "bgra", w, h, w * 4,
            )
        except SystemError as refused:
            raise MemoryError("mpv had no memory for a copy of the overlay") from refused
        # hold a reference so the buffer isn't freed while mpv reads it
        self._overlays[ident] = arr

    @mpv_call()
    def remove_overlay(self, ident: int) -> None:
        self._mpv.overlay_remove(ident)
        self._overlays.pop(ident, None)

    def close(self) -> None:
        # Destroying mpv under a call still inside it is an access violation; a leaked handle at exit is not.
        started = time.monotonic()
        if not self._gate.close(CLOSE_DRAIN_TIMEOUT_S):
            if self._gate.inside:
                logger.error(
                    "Leaving this engine's mpv alive: %d call(s) still inside it after "
                    "%.1fs.  Freeing it now would crash the process.",
                    self._gate.inside, CLOSE_DRAIN_TIMEOUT_S,
                )
            return
        waited_ms = (time.monotonic() - started) * 1e3
        if waited_ms >= 1.0:
            logger.info("Waited %.0fms for mpv calls to return before closing", waited_ms)
        self._release()

    def _release(self) -> None:
        _terminate_outside_the_callers_apartment(self._mpv)


class MpvEngine(_MpvControl):
    def __init__(
        self, wid: int, *, muted: bool = False, loop_file: bool = True, prefetch: bool = False,
        audio: bool = True,
    ) -> None:
        super().__init__(looping=loop_file)
        mpv = _import_mpv()
        self._lost_gpu = LostGpu(self._build_a_new_video_output)
        options = _shared_options(muted=muted, loop_file=loop_file, prefetch=prefetch, audio=audio)
        options.update(
            wid=str(int(wid)),
            vo="gpu",
            input_vo_keyboard=False,
            log_handler=self._hear,
        )
        self._wid = int(wid)
        self._adopt(mpv.MPV(**options))

    def _hear(self, level: str, prefix: str, text: str) -> None:
        _log_mpv(level, prefix, text)
        self._lost_gpu.heard(text)

    @mpv_call(False)
    def _build_a_new_video_output(self) -> bool:
        # mpv builds a new output only when the option changes, so it passes through null.
        self._mpv.vo = "null"
        self._mpv.vo = "gpu"
        if self._mpv.vid in (False, "no"):
            self._mpv.vid = "auto"
        return self._mpv.current_vo == "gpu"

    def close(self) -> None:
        self._lost_gpu.stop()
        super().close()

    def _viewport_size(self) -> tuple[int, int]:
        return _client_size(self._wid)


def _station_options(audio_device: str | None) -> dict:
    options = dict(
        log_handler=_log_mpv,
        loglevel="warn",
        vid="no",
        vo="null",
        audio_display="no",
        mute="yes",
        loop_playlist="inf",
        shuffle="yes",
        idle="yes",
        audio_fallback_to_null="yes",
        input_default_bindings=False,
        **_MPV_SCRIPTS_OFF,
    )
    if audio_device:
        options["audio_device"] = audio_device
    return options


class MpvStation:
    # mpv reshuffles a looped list as it comes round, and gives up on one whose every video fails.

    def __init__(self, handle, videos: Sequence[Path]) -> None:
        self._mpv = handle
        self._heard_at: int | None = None
        self._paused = False
        first, *rest = videos
        handle.loadfile(str(first), "replace")
        for video in rest:
            handle.loadfile(str(video), "append")

    @classmethod
    def opened(cls, videos: Sequence[Path], *, audio_device: str | None = None) -> MpvStation:
        return cls(_import_mpv().MPV(**_station_options(audio_device)), videos)

    def tune(self, level: int | None) -> None:
        if level == self._heard_at:
            return
        self._heard_at = level
        if level is not None:
            self._mpv.volume = level
        self._mpv.mute = level is None

    def set_paused(self, paused: bool) -> None:
        if paused != self._paused:
            self._paused = paused
            self._mpv.pause = paused

    def close(self) -> None:
        _terminate_outside_the_callers_apartment(self._mpv)
