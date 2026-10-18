"""libmpv-backed playback engine, shared by every Funestra in this family.

mpv hardware-decodes on the GPU end to end (d3d11va), owns audio and so gets A/V
sync for free, seeks precisely enough to click on a timeline, and loops A-B
natively.  ``MpvEngine`` renders into a window the caller owns (via ``wid``) --
a pygame window, or a Qt widget's native one; its offscreen twin
(:mod:`funestra.render_engine`) renders into a framebuffer the caller
supplies.  Both drive the ``_MpvControl`` surface below, and both put overlays
on top through ``overlay_add``.

The interface is a superset of what any one Funestra needs, because the two use it
differently: the Main Funestra opens one file at a time (``loop_file="inf"``) and navigates
explicitly, while a satellite opens letting end-of-file walk a prefetched
playlist.  Either can be told to behave like the other — that is what a lock is
on either — so a constructor option is a *default* and never a rule.

Every method below that touches mpv holds :mod:`funestra.mpv_gate` open for
its whole body, because a host drives one engine from more than one thread and
closing it from any of them would otherwise free the handle under the others.

``_MpvControl`` is driven against a fake in ``tests/test_mpv_control.py``.  What
needs the DLL and a real window is constructing an ``MpvEngine``, and Fun Time's
hidden-desktop integration suite is what exercises that.
"""
from __future__ import annotations

import ctypes
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
from .ken_burns import KenBurns, Moves, View
from .libmpv_loader import add_libmpv_to_path, libmpv_dirs
from .lost_gpu import LostGpu
from .mpv_gate import CallGate, mpv_call

logger = logging.getLogger(__name__)

# Every Lua script mpv loads for itself, the on-screen controller among them.  An
# engine here is driven through the client API, so the scripting layer has
# nothing to do but cost, and one of those scripts erroring on the way out takes
# a host process down — see tests/test_mpv_control.py for the mechanism.
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

# mpv's severities onto Python's.  Only warnings and worse are asked for below,
# so anything that arrives belongs in the host's log at face value.
_MPV_LEVELS = {"fatal": logging.CRITICAL, "error": logging.ERROR, "warn": logging.WARNING}


def _log_mpv(level: str, prefix: str, text: str) -> None:
    """Write one of mpv's own messages to the host's log.

    Failures inside the engine are otherwise invisible from Python: a clip mpv
    cannot open, a codec it cannot initialize, a hardware decoder it cannot
    create — none of them raise, and playback carries on with an empty video
    output.  What the host is left with is a black window over a healthy process
    and nothing written down anywhere, which is the one state that cannot be
    diagnosed afterwards.  mpv says why at the moment it happens; this keeps the
    sentence, in the log file the host already writes.
    """
    logger.log(_MPV_LEVELS.get(level, logging.WARNING), "mpv %s: %s", prefix, text.strip())


# How many times the engine is asked for before the folder it lives in is
# declared genuinely empty.  Each attempt puts the folder back on PATH first,
# and the window another thread can take it out in is one import long.
_TRIES_AT_THE_ENGINE = 5


def _import_mpv():
    return _import_the_engine(importlib.import_module)


def _import_the_engine(load, tries: int = _TRIES_AT_THE_ENGINE):
    """Put the engine's folder on PATH and load python-mpv, more than once if
    something takes the folder off again.

    python-mpv finds libmpv by walking ``%PATH%``, and PATH is shared: other
    libraries put themselves on it with a read and then a write, so a write
    built from a read taken before ours lands afterwards and puts PATH back
    without our folder in it.  vosk does exactly that, in its module body, on
    the thread a voice application listens on -- and a host that opened an
    engine at that moment was told the engine could not be found while it sat
    in the folder the line before had just named.

    Asked again, the folder goes back and the import takes.  What survives all
    of them is a folder that really is empty, and the refusal says which ones
    were looked in rather than leaving that to the reader.
    """
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
    """What each folder answered, and where PATH actually starts.

    The two halves settle between the two ways this fails.  A folder that says
    it holds the DLL while the import cannot find it means PATH is not what we
    left it -- something rewrote it between the two lines.  A folder that
    cannot answer at all names the error it got, which is the other half.
    """
    answers = []
    for folder in libmpv_dirs():
        try:
            answers.append(f"{folder} ({'holds libmpv-2.dll' if (folder / 'libmpv-2.dll').is_file() else 'no libmpv-2.dll in it'})")
        except OSError as refused:
            answers.append(f"{folder} (could not be looked in: {refused})")
    front = os.environ.get("PATH", "").split(os.pathsep)[:3]
    return f"Looked in: {', '.join(answers)}. PATH starts: {front}"


def _shared_options(*, muted: bool, loop_file: bool, prefetch: bool, audio: bool = True) -> dict:
    """The mpv options every engine in this family shares, however it renders.

    The windowed engine adds its ``wid``/``vo=gpu`` pair on top, and a log handler
    that also tells its :class:`~funestra.lost_gpu.LostGpu` what mpv said; the offscreen
    one (:mod:`funestra.render_engine`) adds ``vo=libmpv`` instead.

    ``log_handler`` and ``loglevel`` are python-mpv's own constructor keywords
    rather than mpv options; they ride here because both engines want them for
    the same reason (:func:`_log_mpv`) and both hand this dict straight to
    ``MPV()``.
    """
    options = dict(
        log_handler=_log_mpv,
        # Warnings and worse only.  At "info" mpv narrates every file it opens,
        # which for a satellite walking a playlist is a line every few seconds —
        # noise that would bury the one line that matters.
        loglevel="warn",
        hwdec="auto-safe",
        # loop-1: the current file repeats, so a video never ends on its own;
        # [ ] navigates.  The Main Funestra opens on this; a satellite constructs with
        # loop_file=False ("no") so end-of-file advances its playlist.  Both
        # toggle it at runtime (see set_loop_file).
        loop_file="inf" if loop_file else "no",
        keep_open="yes",
        mute="yes" if muted else "no",
        # An audio device that cannot be opened must never stop the video:
        # mpv's default clock follows audio, so a failed output would freeze
        # every frame while the file "plays".  Null-audio playback keeps the
        # clock running and the session alive (a headset sink that is not
        # accepting streams yet is the case that found this).
        audio_fallback_to_null="yes",
        **_MPV_SCRIPTS_OFF,
        input_default_bindings=False,
        image_display_duration="inf",
        # Leaning a still (video-align) moves it only along a side it
        # overhangs the window on: along one it fits inside, it stays centered.
        video_recenter="yes",
    )
    if prefetch:
        # Open and demux the *next* playlist entry during the tail of the
        # current one, so a satellite's end-of-file auto-advance cuts to an
        # already-loaded clip instead of cold-opening it on screen.  Only
        # satellites pass this; the Main Funestra plays one file at a time (loop_file=inf,
        # explicit [ ] nav) and has no next entry to prefetch.
        options["prefetch_playlist"] = "yes"
    if not audio:
        options["aid"] = "no"
    return options


TILES_SHADER = Path(__file__).with_name("tiles.glsl")

# How a still's view reaches mpv: its zoom, and how far it leans each way
# between the picture's two edges (video/out/aspect.c places a picture that
# overhangs the window from flush with one edge at -1 to flush with the other
# at +1, so every lean keeps it covering the window).
_PLACING = ("video_zoom", "video_align_x", "video_align_y")


def tiles_across(source: tuple[int, int], window: tuple[int, int]) -> int:
    source_width, source_height = source
    window_width, window_height = window
    if source_width >= source_height or window_width <= window_height:
        return 1
    return window_width * source_height // (window_height * source_width)


# How long close() waits for calls already inside mpv before giving up on
# freeing the handle at all.  Generous because it is only ever spent on calls
# that are genuinely in flight: the gate turns every *later* call into a no-op
# the instant close() starts, so a worker looping on mpv does not extend this.
# A single property read waiting on the core lock of a file being opened
# measured 72-492ms in the shutdown probe, and a cold clip off the network
# drive is slower again.
CLOSE_DRAIN_TIMEOUT_S = 10.0


_APTTYPEQUALIFIER_IMPLICIT_MTA = 1


def _holds_a_com_apartment() -> bool:
    kind, qualifier = ctypes.c_int(), ctypes.c_int()
    hr = ctypes.windll.ole32.CoGetApartmentType(ctypes.byref(kind), ctypes.byref(qualifier))
    return hr == 0 and qualifier.value != _APTTYPEQUALIFIER_IMPLICIT_MTA


def _terminate_outside_the_callers_apartment(handle) -> None:
    # libmpv destroys its core on the thread that terminates it, and its WASAPI
    # output ends with a CoUninitialize it never paired with an init there --
    # which takes the calling thread's apartment, and a Qt GUI thread's drag
    # and drop with it.
    def terminate() -> None:
        try:
            handle.terminate()
        except Exception:
            pass

    if not _holds_a_com_apartment():
        terminate()
        return
    teardown = threading.Thread(target=terminate, name="mpv-teardown")
    teardown.start()
    teardown.join()


class _MpvControl:
    """The control surface shared by the windowed and offscreen engines.

    Subclasses call ``super().__init__()`` and hand the handle they construct to
    ``_adopt``; every method here only drives it, so a Funestra can hold either
    engine without knowing which rendering path is backing it.

    Each of those methods runs under :class:`funestra.mpv_gate.CallGate`,
    which is what makes an engine safe to close from a thread other than the one
    driving it — and, after :meth:`close`, turns every straggler into a no-op
    instead of a dereference of a freed handle.
    """

    _mpv: object

    def __init__(self, moves: Moves | None = None, *, looping: bool = False) -> None:
        self._gate = CallGate()
        self._frame_rate = 0.0
        # mpv's word on the file's video track: an image, a clip, or None
        # while it has none -- between two files, before the next one's tracks.
        self._image_track: bool | None = None
        self._overlays: dict[int, np.ndarray] = {}
        # A still runs on a clock of its own, which moves it and ends it: mpv
        # leaves a still's playhead at nought (verified against libmpv,
        # 2026-09-19), so nothing of mpv's can say how far into its pace it is.
        self._ken_burns = KenBurns(moves, looping=looping)
        self._placed = (0.0, 0.0, 0.0)
        self._path: str | None = None
        self._swapped_in: set[str] = set()
        self._moving_on = False
        self._picture_time = (0.0, 0.0)
        self._audio_device: str | None = None
        self._staged: str | None = None
        # Read off an observation rather than asked for: a property read takes
        # the core's lock, which a file being opened holds for long stretches,
        # and a frame loop asking mid-open measured hundreds of milliseconds
        # blocked on it.  video-out-params (not dwidth/dheight) so both numbers
        # land in one event and a reader can never see half a size.
        self._video_dims = (0, 0)
        self._source_dims = (0, 0)
        self._tiling = (1, "no")

    def _adopt(self, handle) -> None:
        self._mpv = handle
        handle.observe_property("container-fps", self._note_frame_rate)
        handle.observe_property("current-tracks/video/image", self._note_image_track)
        handle.observe_property("path", self._note_file)
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
    def tile_to_fill(self, window_width: int, window_height: int) -> None:
        tiles = tiles_across(self._source_dims, (window_width, window_height))
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
        """The picture's shape as mpv puts it out, tiles included -- (0, 0)
        until it knows, and between files.

        What a host measures its own chrome against: where to float the stills
        either side of the picture, where to seat a panel under it.  Callers
        keep their last size through the gap between files, which is what keeps
        the previous clip's final frame on screen during a transition instead
        of a teardown flicker.
        """
        return self._video_dims

    def _now(self) -> float:
        """The clock a still's move is paced by, in one call a test can wind on
        by hand -- mpv leaves a picture's own playhead at nought."""
        return time.monotonic()

    @property
    def frame_rate(self) -> float:
        return self._frame_rate

    @property
    def showing_picture(self) -> bool:
        return self._image_track is True

    @property
    def showing_video(self) -> bool:
        return self._image_track is False

    @mpv_call()
    def load(self, path: Path) -> None:
        self._staged = None
        self._begin_the_new_clip()
        self._mpv.play(str(path))
        # Reset to just this file: drop any entry the previous clip had staged as
        # its prefetched next, so the caller stages a fresh one from a clean base.
        # A no-op for the Main Funestra (single-file playlist); the reset is what a satellite's
        # jump/discard/filter navigation needs.
        self._mpv.playlist_clear()

    @mpv_call()
    def swap_still(self, path: Path) -> None:
        self._swapped_in.add(str(path))
        self._mpv.play(str(path))
        self._mpv.playlist_clear()
        if self._staged is not None:
            self._mpv.loadfile(self._staged, "append")

    # Everything below trims mpv's playlist down to the clip on screen, and each
    # does it with ``playlist-clear`` — "clear the playlist, except the currently
    # played file" — rather than by removing computed indices.
    #
    # Which entry is current is mpv's to know, and it changes underneath us: with
    # prefetch on, mpv rolls onto the staged entry by itself at end-of-file, so an
    # index read a moment earlier can already name the clip now playing.  Removing
    # by that index takes the playing entry out from under mpv, which leaves it on
    # an empty playlist — a black window for the rest of the session, with a
    # healthy process, a running loop and nothing raised anywhere.  There is no
    # window to lose here: ``playlist-clear`` resolves "current" inside mpv.

    @mpv_call()
    def stop(self) -> None:
        """Let go of the file on screen, playing nothing.

        A host that is about to move or delete what it was showing has to: the
        engine holds an open handle on it, and Windows refuses to move a file
        out from under one.
        """
        self._staged = None
        self._mpv.command("stop")

    @mpv_call()
    def stage_next(self, path: Path) -> None:
        """Make *path* the single entry queued after the current clip.

        With ``prefetch-playlist`` on, mpv opens and demuxes this entry before the
        current clip ends, so the end-of-file auto-advance onto it is seamless.
        Any previously-staged entry is replaced.
        """
        self._mpv.playlist_clear()
        self._mpv.loadfile(str(path), "append")
        self._staged = str(path)

    @mpv_call()
    def clear_next(self) -> None:
        """Drop the staged next entry (used when a lock pins the current clip)."""
        self._staged = None
        self._mpv.playlist_clear()

    @property
    @mpv_call(False)
    def advanced_to_next(self) -> bool:
        """True once mpv has reached end-of-file and auto-advanced off the current
        clip onto the staged next one (its playlist position moved past the head).

        -1 is mpv's "no entry playing", which is not past the head.
        """
        pos = self._mpv.playlist_pos
        return pos is not None and pos >= 1

    @mpv_call()
    def settle_on_the_next(self) -> None:
        """After an auto-advance the spent clip still occupies index 0; clearing
        around the current entry shifts it back to the head (mpv keeps playing it
        uninterrupted), restoring the [current, next] window.
        """
        self._staged = None
        self._mpv.playlist_clear()
        self._begin_the_new_clip()

    def _begin_the_new_clip(self) -> None:
        self._swapped_in.clear()
        self._moving_on = False
        self._ken_burns.new_picture(self._now())

    @property
    @mpv_call(False)
    def idle(self) -> bool:
        """Whether the engine has nothing up at all.

        True between a file that would not open and the next one asked for:
        mpv does not raise for a file it cannot demux, it simply ends up with
        nothing playing (verified -- a text file named .mp4 leaves idle-active
        true, path None and eof-reached unset).  A host that has asked for a
        file and finds this reads it as the file's refusal.
        """
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

    @mpv_call()
    def push_still(self) -> None:
        """Carry the picture on screen one frame further along its move; a video
        is drawn as it comes.  Called once a frame by whichever loop is driving
        this engine."""
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
        self._picture_time = (min(self._ken_burns.progress(now) * self._ken_burns.pace_s * 1000.0,
                                  holds_for_ms), holds_for_ms)
        if self._image_track and not self._moving_on and self._ken_burns.ran_out(now):
            self._move_on_from_the_still()

    @property
    def picture_time(self) -> tuple[float, float] | None:
        """How far the picture on screen is into the time it holds the screen,
        and how long that is, in milliseconds -- None on a video."""
        return self._picture_time if self._image_track else None

    def hold_picture_for(self, seconds: float | None) -> None:
        self._ken_burns.hold_for(seconds)

    def seek_picture(self, ms: float) -> None:
        pace_s = self._ken_burns.pace_s
        if pace_s:
            self._ken_burns.seek(ms / 1000.0 / pace_s, self._now())

    def _move_on_from_the_still(self) -> None:
        self._swapped_in.clear()
        if self._staged is not None:
            self._moving_on = True
            self._mpv.command("playlist-next")

    @mpv_call()
    def set_loop_file(self, loop: bool) -> None:
        """Toggle infinite single-file looping at runtime.

        This is what a lock is on every Funestra here: unlocked plays through and
        lets end-of-file walk the playlist (``no``); locked, the file repeats
        seamlessly in place (``inf``).  Which end each opens on differs — a
        satellite starts unlocked, the Main Funestra starts locked — but the switch is the same
        one, so "locked" means the same thing wherever it is said.
        """
        self._ken_burns.set_looping(loop, self._now())
        self._mpv.loop_file = "inf" if loop else "no"

    @mpv_call()
    def set_speed(self, speed: float) -> None:
        """Set the playback rate (1.0 = normal). mpv retimes video and audio,
        and its ``time_pos`` clock advances at this rate — so the session's
        funscript sync, which reads that clock, follows the new speed for free
        (the T-Code driver only rescales its move durations)."""
        self._mpv.speed = speed

    @mpv_call()
    def set_volume(self, volume: int) -> None:
        """Set the audio volume (0-100, a percentage of the source's own level).

        ``volume`` and ``mute`` are independent mpv properties, so an engine
        constructed muted (``--no-audio`` / ``FUN_TIME_MUTE_AUDIO``, which the
        hidden-desktop integration runs rely on) stays silent whatever is set here.
        """
        self._mpv.volume = volume

    @mpv_call()
    def set_muted(self, muted: bool) -> None:
        """Silence or unsilence the engine at runtime, leaving the volume alone
        (so unmuting restores whatever level was set — the mixer convention)."""
        self._mpv.mute = muted

    @mpv_call()
    def set_audio_device_matching(self, substring: str) -> str | None:
        """Route audio to the output device named *substring*, by the rule
        :mod:`funestra.audio_outputs` states.

        Returns the picked device's description, or None — with the device
        untouched — when nothing matches, so a headset that is off falls back
        to the system default rather than to silence.
        """
        outputs = [Output(str(device.get("description") or device["name"]), device["name"])
                   for device in self._mpv.audio_device_list or []]
        picked = pick_output(outputs, substring)
        if picked is None:
            return None
        self._mpv.audio_device = self._audio_device = picked.handle
        return picked.label

    def radio_station(self, clips: Sequence[Path]) -> MpvStation | None:
        """A station of *clips*, sounding wherever this engine's own sound goes."""
        return MpvStation.opened(clips, audio_device=self._audio_device)

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
        """Current displayed frame, resized to *height*, as a BGRA array.

        Captures loop in/out thumbnails on demand (a few times per loop)
        without disturbing playback — mpv renders the video itself.  None when
        no frame is available yet.
        """
        try:
            img = self._mpv.screenshot_raw()  # PIL Image
        except SystemError:  # python-mpv's word for a command mpv refused: no frame to take
            return None
        if img is None or img.height == 0:
            return None
        w = max(1, round(height * img.width / img.height))
        arr = np.asarray(img.convert("RGBA").resize((w, height)))
        return np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]], dtype=np.uint8)

    @mpv_call()
    def overlay(self, ident: int, x: int, y: int, rgba) -> None:
        """Composite an (H, W, 4) BGRA uint8 array at (x, y) over the video."""
        arr = np.ascontiguousarray(rgba, dtype=np.uint8)
        h, w = arr.shape[:2]
        self._mpv.overlay_add(
            ident, x, y, "&" + str(arr.ctypes.data), 0, "bgra", w, h, w * 4,
        )
        # hold a reference so the buffer isn't freed while mpv reads it
        self._overlays[ident] = arr

    @mpv_call()
    def remove_overlay(self, ident: int) -> None:
        self._mpv.overlay_remove(ident)
        self._overlays.pop(ident, None)

    def close(self) -> None:
        """Free this engine's mpv, once no thread is inside a call on it.

        The only method here that does NOT take a lease — it is what closes the
        gate — and the only one that can decline to do its job: a call that has
        not come back within :data:`CLOSE_DRAIN_TIMEOUT_S` leaves the handle
        alive and the process to reap it, because destroying mpv underneath a
        live call is an access violation and a leaked handle on the way out is
        not.  Calling this twice frees nothing twice.
        """
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
        """Hand mpv's own resources back.  Subclasses free theirs first.

        Reached only through :meth:`close`, and only once, so an override needs
        no guard of its own.
        """
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
    """One of a radio's stations: its clips' sound alone, round and round in a
    fresh order each time round (mpv reshuffles a looped list as it comes round,
    and gives up on one whose every clip fails, both probed against libmpv on
    2026-10-16), playing on whether or not it is heard."""

    def __init__(self, handle, clips: Sequence[Path]) -> None:
        self._mpv = handle
        self._heard_at: int | None = None
        self._paused = False
        first, *rest = clips
        handle.loadfile(str(first), "replace")
        for clip in rest:
            handle.loadfile(str(clip), "append")

    @classmethod
    def opened(cls, clips: Sequence[Path], *, audio_device: str | None = None) -> MpvStation:
        return cls(_import_mpv().MPV(**_station_options(audio_device)), clips)

    def tune(self, level: int | None) -> None:
        """Be heard at *level*, or not at all for None."""
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
