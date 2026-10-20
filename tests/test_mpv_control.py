"""The shared mpv control surface: how it trims mpv's playlist.

``_MpvControl`` is the half of the engine that needs no window and no DLL — it
only drives an mpv handle — so the playlist bookkeeping every Funestra depends on
is testable against a fake handle here, rather than only through an app's
integration suite.
"""
from __future__ import annotations

import ctypes
import logging
import math
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from dealt_moves import DRIFT, Deals

from funestra import audio_outputs, mpv_engine
from funestra.ken_burns import Move, zoom_in
from funestra.mpv_engine import (
    TILES_SHADER,
    MpvEngine,
    _MpvControl,
    _shared_options,
    tiles_across,
)


class FakeMpv:
    """An mpv handle that records what was asked of it.

    ``playlist_pos`` is settable so a test can put the handle in the states the
    real one reaches: on the head, rolled onto a prefetched entry, or holding no
    entry at all (-1, mpv's "nothing is playing").
    """

    def __init__(self, *, pos: int = 0, count: int = 2) -> None:
        self.playlist_pos = pos
        self.playlist_count = count
        self.calls: list[tuple] = []
        self.observers: dict[str, object] = {}
        self.heard: dict[str, object] = {}
        self.audio_device_list: list[dict] = []
        self.audio_device = "auto"
        self.__dict__.update(dict.fromkeys(PLACING, 0.0))

    def observe_property(self, name: str, handler) -> None:
        self.observers[name] = handler

    def report(self, name: str, value) -> None:
        if name in self.heard and self.heard[name] == value:
            return
        self.heard[name] = value
        self.observers[name](name, value)

    def playlist_clear(self) -> None:
        self.calls.append(("clear",))

    def playlist_remove(self, index: int) -> None:
        self.calls.append(("remove", index))

    def loadfile(self, path: str, mode: str) -> None:
        self.calls.append(("loadfile", path, mode))

    def play(self, path: str) -> None:
        self.calls.append(("play", path))

    def command(self, name: str, *args) -> None:
        self.calls.append(("command", name, *args))

    def __setattr__(self, name: str, value) -> None:
        if name in PLACING:
            self.calls.append(("set", name, value))
        super().__setattr__(name, value)


PLACING = {"video_zoom", "video_align_x", "video_align_y"}


CREEP = zoom_in(0.0, 0.0)


class Control(_MpvControl):
    """A control surface whose clock a test moves by hand.

    A still's move is paced by a clock rather than by a playhead -- mpv
    leaves a picture's at nought -- so ``now`` is what a test winds on to say
    how far into the hold the picture has got.
    """

    def __init__(self, mpv, now: float = 0.0, move: Move = CREEP,
                 deals: Deals | None = None,
                 looping: bool = False) -> None:
        # the call gate every method here runs under
        super().__init__(deals or Deals(move), looping=looping)
        self.now = now
        self._adopt(mpv)

    def _now(self) -> float:
        return self.now


WIDE = (1920, 1080)


def show_a_picture(control: Control, mpv: FakeMpv, shape: tuple[int, int] = WIDE) -> None:
    control.load(Path("made-up-scene.png"))
    mpv.report("path", "made-up-scene.png")
    mpv.report("current-tracks/video/image", True)
    mpv.report("video-out-params", {"dw": shape[0], "dh": shape[1]})


def test_the_frame_rate_is_the_one_mpv_reported_for_the_file_on_screen():
    mpv = FakeMpv()
    control = Control(mpv)

    mpv.report("container-fps", 29.970029830932617)

    assert control.frame_rate == 29.970029830932617


def test_between_files_there_is_no_frame_rate():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("container-fps", 60.0)

    mpv.report("container-fps", None)

    assert control.frame_rate == 0.0


def test_a_picture_holds_the_screen_for_the_pace_it_was_given():
    mpv = FakeMpv()

    Control(mpv).set_pace(2.5)

    assert mpv.image_display_duration == 2.5


def test_a_pace_of_nought_holds_the_picture_until_something_moves_it():
    mpv = FakeMpv()

    Control(mpv).set_pace(0)

    assert mpv.image_display_duration == "inf"


def test_the_engine_shows_a_picture_when_mpv_says_its_video_track_is_an_image():
    mpv = FakeMpv()
    control = Control(mpv)

    mpv.report("current-tracks/video/image", True)
    assert control.showing_picture is True

    mpv.report("current-tracks/video/image", None)
    assert control.showing_picture is False


def test_a_engine_holds_a_picture_four_seconds_until_a_source_sets_a_pace():
    options = _shared_options(muted=False, loop_file=False, prefetch=True)

    assert options["image_display_duration"] == 4.0


# Every Lua script mpv loads for itself, by the option that keeps it out.
MPVS_OWN_SCRIPTS = (
    "osc", "load_scripts", "load_stats_overlay", "load_osd_console",
    "load_auto_profiles", "load_select", "load_positioning", "load_commands",
    "ytdl",
)


def test_a_engine_runs_none_of_mpvs_lua_scripts():
    """All of them, not just the on-screen controller.

    An engine here is driven through the client API alone, so mpv's scripting
    layer can only cost.  What it costs is a crash: these scripts error on the
    way out often enough to matter, LuaJIT unwinds a Lua error through a Windows
    structured exception, and a process with faulthandler armed answers every one
    by dumping all threads' Python frames without the GIL -- while python-mpv's
    event thread is exiting, so the walk reaches a thread state being freed and
    faults.  Measured on this family's options: 22 of 40 core teardowns raised
    one with these left on, none of 60 with them off.
    """
    options = _shared_options(muted=False, loop_file=True, prefetch=False)

    assert {name: options.get(name) for name in MPVS_OWN_SCRIPTS} == dict.fromkeys(
        MPVS_OWN_SCRIPTS, "no")


class GpuWatch:
    """Stands in for a window's watch on its graphics card: what it heard, and what it builds with."""

    def __init__(self, rebuild) -> None:
        self.rebuild = rebuild
        self.lines: list[str] = []
        self.stopped = False

    def heard(self, text: str) -> None:
        self.lines.append(text)

    def stop(self) -> None:
        self.stopped = True


def a_window(monkeypatch, mpv: FakeMpv | None = None, **engine_args) -> SimpleNamespace:
    window = SimpleNamespace(mpv=mpv or FakeMpv(), options={})

    def open_mpv(**options):
        window.options.update(options)
        return window.mpv

    def watch(rebuild) -> GpuWatch:
        window.watch = GpuWatch(rebuild)
        return window.watch

    monkeypatch.setattr(mpv_engine, "_import_mpv", lambda: SimpleNamespace(MPV=open_mpv))
    monkeypatch.setattr(mpv_engine, "LostGpu", watch)
    window.engine = MpvEngine(4242, **engine_args)
    return window


def _options_mpv_opened_with(monkeypatch, **engine_args) -> dict:
    return a_window(monkeypatch, **engine_args).options


SUSPENDED = ("Failed to create SRV: The GPU device instance has been suspended. Use "
             "GetDeviceRemovedReason to determine the appropriate action. (0x887a0005)")


def test_every_line_mpv_says_reaches_the_windows_watch_on_its_graphics_card_and_the_log(
        monkeypatch, caplog):
    window = a_window(monkeypatch)

    with caplog.at_level(logging.ERROR, logger="funestra.mpv_engine"):
        window.options["log_handler"]("error", "vo/gpu/d3d11", SUSPENDED)

    assert window.watch.lines == [SUSPENDED]
    assert [record.getMessage() for record in caplog.records] == [f"mpv vo/gpu/d3d11: {SUSPENDED}"]


class WindowMpv(FakeMpv):
    """A window's handle: the outputs it was told to build, whether a new one comes up, its track."""

    def __init__(self, *, vid=1, builds: bool = True) -> None:
        super().__init__()
        self.__dict__.update(vid=vid, current_vo="gpu", builds=builds)

    def __setattr__(self, name: str, value) -> None:
        if name in ("vo", "vid"):
            self.calls.append(("set", name, value))
        if name == "vo":
            self.__dict__["current_vo"] = value if self.builds or value != "gpu" else None
        super().__setattr__(name, value)


def outputs_and_tracks_asked_for(mpv: WindowMpv) -> list[tuple]:
    return [call for call in mpv.calls if call[0] == "set" and call[1] in ("vo", "vid")]


def test_a_window_whose_graphics_card_went_away_is_given_a_new_video_output(monkeypatch):
    window = a_window(monkeypatch, WindowMpv())

    came_up = window.watch.rebuild()

    assert outputs_and_tracks_asked_for(window.mpv) == [("set", "vo", "null"), ("set", "vo", "gpu")]
    assert came_up is True


def test_a_new_video_output_that_never_came_up_says_so(monkeypatch):
    assert a_window(monkeypatch, WindowMpv(builds=False)).watch.rebuild() is False


@pytest.mark.parametrize("given_up", [False, "no"])
def test_a_new_video_output_brings_back_the_track_mpv_gave_up_on_while_the_card_was_gone(
        monkeypatch, given_up):
    window = a_window(monkeypatch, WindowMpv(vid=given_up))

    window.watch.rebuild()

    assert outputs_and_tracks_asked_for(window.mpv)[-1] == ("set", "vid", "auto")


class NoFrameMpv(FakeMpv):
    def screenshot_raw(self, includes: str = "subtitles"):
        raise SystemError("Error running mpv command", -12)


def test_a_frame_mpv_cannot_capture_while_its_output_is_being_built_is_no_frame():
    assert Control(NoFrameMpv()).screenshot_bgra() is None


def test_a_closed_window_calls_off_its_watch_on_the_graphics_card(monkeypatch):
    window = a_window(monkeypatch, WindowMpv())

    window.engine.close()

    assert window.watch.stopped


def test_a_window_never_heard_opens_mpv_with_no_sound_track_for_a_sound_device_to_hold(
        monkeypatch):
    assert _options_mpv_opened_with(monkeypatch, audio=False)["aid"] == "no"


def test_a_window_that_can_be_heard_leaves_mpv_its_sound_track(monkeypatch):
    assert "aid" not in _options_mpv_opened_with(monkeypatch)


def test_staging_the_next_clip_never_removes_by_index():
    """The staged entry goes through ``playlist-clear``, which mpv resolves against
    whatever is playing at that instant.

    Removing by an index read a moment earlier is the bug this pins: with prefetch
    on, mpv rolls onto the staged entry by itself at end-of-file, so ``pos + 1``
    can already name the clip now on screen — and removing it leaves mpv on an
    empty playlist, which is a black window for the rest of the session.
    """
    mpv = FakeMpv(pos=0, count=2)
    Control(mpv).stage_next(Path("alpha.mp4"))
    assert ("clear",) in mpv.calls
    assert not [call for call in mpv.calls if call[0] == "remove"]
    assert mpv.calls[-1] == ("loadfile", "alpha.mp4", "append")


def test_staging_holds_up_when_mpv_says_nothing_is_playing():
    """-1 is mpv's "no entry playing", not entry zero.

    Read as a position it made the trim walk the playlist to nothing — so an engine
    that had lost its file could never get one back.
    """
    mpv = FakeMpv(pos=-1, count=3)
    Control(mpv).stage_next(Path("beta.mp4"))
    assert not [call for call in mpv.calls if call[0] == "remove"]
    assert mpv.calls[-1] == ("loadfile", "beta.mp4", "append")


def test_clearing_the_staged_entry_keeps_the_clip_on_screen():
    """A lock drops the prefetched next; the clip being held must not go with it."""
    mpv = FakeMpv(pos=0, count=2)
    Control(mpv).clear_next()
    assert mpv.calls == [("clear",)]


def test_settling_on_the_next_clip_keeps_it_on_screen():
    mpv = FakeMpv(pos=1, count=2)
    Control(mpv).settle_on_the_next()
    assert mpv.calls == [("clear",)]


def test_no_entry_playing_does_not_read_as_having_advanced():
    """An engine holding no file has not moved past the head — it has fallen off
    the playlist, and treating that as an advance walks the session's index on
    past a clip that never played."""
    assert Control(FakeMpv(pos=-1)).advanced_to_next is False
    assert Control(FakeMpv(pos=0)).advanced_to_next is False
    assert Control(FakeMpv(pos=1)).advanced_to_next is True


class BlockingMpv(FakeMpv):
    """A handle whose property read can be held open, the way a real one is
    while a file it is opening holds the core's lock."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.terminated = 0

    @property
    def time_pos(self):
        self.entered.set()
        self.release.wait(10.0)
        return 1.0

    def terminate(self) -> None:
        self.terminated += 1
        self.calls.append(("terminate",))


def test_close_waits_for_a_read_that_is_still_inside_mpv():
    """The shutdown crash, in miniature: python-mpv's terminate() nulls its
    handle before destroying the core, so a property read that began a moment
    earlier dereferences NULL.  close() may not run until the read is out."""
    mpv = BlockingMpv()
    control = Control(mpv)
    reading = threading.Thread(target=lambda: control.position_ms)
    reading.start()
    assert mpv.entered.wait(5.0)

    closing = threading.Thread(target=control.close)
    closing.start()
    closing.join(timeout=0.3)
    assert closing.is_alive()
    assert mpv.terminated == 0

    mpv.release.set()
    closing.join(timeout=10.0)
    reading.join(timeout=10.0)
    assert mpv.terminated == 1


def test_the_frame_rate_is_answered_while_a_read_is_stuck_inside_mpv():
    """A file being opened holds mpv's core lock for hundreds of milliseconds,
    and a Funestra asks for the frame rate every frame it paints."""
    mpv = BlockingMpv()
    control = Control(mpv)
    mpv.report("container-fps", 25.0)
    reading = threading.Thread(target=lambda: control.position_ms)
    reading.start()
    assert mpv.entered.wait(5.0)

    try:
        assert control.frame_rate == 25.0
    finally:
        mpv.release.set()
        reading.join(timeout=10.0)


def test_a_call_arriving_after_the_close_reaches_no_handle():
    """A worker that never noticed the stop flag keeps calling; every one of
    those calls has to become a no-op rather than a use-after-free."""
    mpv = BlockingMpv()
    mpv.release.set()
    control = Control(mpv)
    control.close()
    assert mpv.terminated == 1

    control.load(Path("alpha.mp4"))
    control.seek_ms(1000)
    assert control.position_ms == 0.0
    assert control.duration_ms == 0.0
    assert control.eof is False
    assert control.advanced_to_next is False
    assert mpv.calls == [("terminate",)]


def test_closing_twice_frees_once():
    """``MpvRenderContext.free`` is a bare ``mpv_render_context_free`` with no
    double-free guard of its own, so the guard is here."""
    mpv = BlockingMpv()
    mpv.release.set()
    control = Control(mpv)
    control.close()
    control.close()
    assert mpv.terminated == 1


_COINIT_APARTMENTTHREADED = 0x2
_APTTYPE_STA = 0
_APTTYPE_MAINSTA = 3


class AudioOutputTeardown(FakeMpv):
    """A handle whose teardown ends the way libmpv's does once a file with
    sound has played: its WASAPI output calls ``CoUninitialize`` on whichever
    thread destroys the core, having initialized COM on a thread of its own."""

    def terminate(self) -> None:
        ctypes.windll.ole32.CoUninitialize()


def _on_a_thread_holding_an_sta(work) -> None:
    """Run *work* on a thread holding a single-threaded apartment, as a Qt
    app's GUI thread does."""
    def run() -> None:
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        try:
            work()
        finally:
            ole32.CoUninitialize()

    gui_thread = threading.Thread(target=run)
    gui_thread.start()
    gui_thread.join(timeout=10.0)


def _apartment_type() -> int | None:
    kind, qualifier = ctypes.c_int(), ctypes.c_int()
    hr = ctypes.windll.ole32.CoGetApartmentType(ctypes.byref(kind), ctypes.byref(qualifier))
    return kind.value if hr == 0 else None


def test_closing_on_a_thread_that_holds_a_com_apartment_leaves_it_standing():
    left: list[int | None] = []

    def close_then_ask() -> None:
        Control(AudioOutputTeardown()).close()
        left.append(_apartment_type())

    _on_a_thread_holding_an_sta(close_then_ask)
    assert left in ([_APTTYPE_STA], [_APTTYPE_MAINSTA])


class SlowTeardown(FakeMpv):
    def __init__(self) -> None:
        super().__init__()
        self.torn_down = threading.Event()

    def terminate(self) -> None:
        time.sleep(0.2)
        self.torn_down.set()


def test_a_close_on_a_thread_holding_an_apartment_returns_once_mpv_is_torn_down():
    """A host takes the window mpv draws into down straight after the close."""
    mpv = SlowTeardown()
    torn_down_at_return: list[bool] = []

    def close_then_look() -> None:
        Control(mpv).close()
        torn_down_at_return.append(mpv.torn_down.is_set())

    _on_a_thread_holding_an_sta(close_then_look)
    assert torn_down_at_return == [True]


class EventThreadTeardown(FakeMpv):
    """python-mpv's terminate(): destroy the core, then join the thread that
    delivers mpv's events -- which is a wait on itself if that thread asked."""

    def __init__(self) -> None:
        super().__init__()
        self.event_thread: threading.Thread | None = None

    def terminate(self) -> None:
        if threading.current_thread() is not self.event_thread:
            self.event_thread.join()


def test_a_close_from_mpvs_own_event_thread_does_not_wait_on_itself():
    mpv = EventThreadTeardown()
    control = Control(mpv)
    mpv.event_thread = threading.Thread(target=control.close, daemon=True)
    mpv.event_thread.start()
    mpv.event_thread.join(timeout=2.0)
    assert not mpv.event_thread.is_alive()


STREAMING = {"name": "wasapi/{stream-id}", "description": "Speakers (Example AirLink)"}
HEADSET = {"name": "wasapi/{headset-id}", "description": "Headphones (Example Headset)"}


def test_a_headset_named_for_its_maker_takes_the_sound_over_that_makers_software_output(
        monkeypatch):
    """Two outputs can carry the maker's name — the headset's own, and the
    streaming driver its software installed — and the streaming one is listed
    first, so taking the first match leaves the headset silent."""
    monkeypatch.setattr(audio_outputs, "software_outputs",
                        lambda: frozenset({STREAMING["description"]}))
    mpv = FakeMpv()
    mpv.audio_device_list = [STREAMING, HEADSET]

    picked = Control(mpv).set_audio_device_matching("Example")

    assert mpv.audio_device == HEADSET["name"]
    assert picked == HEADSET["description"]


def test_an_output_no_device_is_named_by_leaves_the_sound_on_the_system_default():
    mpv = FakeMpv()
    mpv.audio_device_list = [STREAMING, HEADSET]

    assert Control(mpv).set_audio_device_matching("Nowhere") is None
    assert mpv.audio_device == "auto"


def test_a_picture_is_drawn_closer_as_its_hold_runs_out():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    control.now = 102.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.5).zoom))


def test_a_clip_after_a_picture_is_drawn_as_it_comes():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, move=DRIFT)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.now = 101.0
    control.push_still()

    mpv.report("path", "made-up-scene.mp4")
    mpv.report("current-tracks/video/image", False)
    control.push_still()

    assert (mpv.video_zoom, mpv.video_align_x, mpv.video_align_y) == (0.0, 0.0, 0.0)


def test_a_frozen_room_holds_the_picture_where_its_move_had_got_to():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    control.now = 101.0
    control.set_paused(True)
    control.now = 103.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.25).zoom))


def test_a_pan_reaches_mpv_as_how_far_the_picture_leans_each_way():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, move=DRIFT)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    control.push_still()

    assert (mpv.video_zoom, mpv.video_align_x, mpv.video_align_y) == DRIFT.at(0.0).placement()


def test_every_engine_keeps_a_picture_centered_along_a_side_it_fits_inside():
    options = _shared_options(muted=False, loop_file=False, prefetch=True)

    assert options["video_recenter"] == "yes"


def test_a_zoom_about_the_middle_asks_mpv_for_the_zoom_alone():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.now = 102.0

    control.push_still()

    assert [call[1] for call in mpv.calls if call[0] == "set"] == ["video_zoom"]


def test_a_picture_that_has_not_moved_since_the_last_frame_asks_mpv_for_nothing():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, move=DRIFT)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.push_still()
    asked = list(mpv.calls)

    control.push_still()

    assert mpv.calls == asked


def test_a_still_swapped_in_carries_on_the_move_of_the_picture_it_replaced():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.now = 102.0

    control.swap_still(Path("made-up-frame.png"))
    mpv.report("path", "made-up-frame.png")
    control.push_still()

    assert deals.dealt == 1
    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.5).zoom))


def swapped_in(mpv: FakeMpv, control: Control, at: float, name: str = "made-up-frame.png") -> None:
    control.now = at
    control.swap_still(Path(name))
    mpv.report("path", name)


def test_mpv_leaves_a_swapped_in_still_up_rather_than_ending_it_on_a_clock_of_its_own():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    swapped_in(mpv, control, at=102.0)

    assert mpv.image_display_duration == "inf"


def test_a_swapped_in_still_runs_out_when_the_picture_it_replaced_would_have():
    mpv = FakeMpv()
    mpv.eof_reached = False
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    swapped_in(mpv, control, at=102.0)

    ran_out = []
    for now in (103.9, 104.05):
        control.now = now
        control.push_still()
        ran_out.append(control.eof)

    assert ran_out == [False, True]


def test_a_still_swapped_in_keeps_the_next_clip_staged_after_it():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.stage_next(Path("made-up-next.png"))
    mpv.calls.clear()

    control.swap_still(Path("made-up-frame.png"))

    assert mpv.calls == [("play", "made-up-frame.png"), ("clear",),
                         ("loadfile", "made-up-next.png", "append")]


def test_a_still_swapped_in_after_the_engine_rolled_onto_its_staged_clip_stages_nothing():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    control.stage_next(Path("made-up-next.png"))
    control.settle_on_the_next()
    mpv.calls.clear()

    control.swap_still(Path("made-up-frame.png"))

    assert mpv.calls == [("play", "made-up-frame.png"), ("clear",)]


def test_a_swapped_in_still_that_runs_out_moves_on_to_the_staged_clip_at_the_pace():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.stage_next(Path("made-up-next.png"))
    swapped_in(mpv, control, at=102.0)
    mpv.calls.clear()

    control.now = 104.05
    control.push_still()

    assert mpv.image_display_duration == 4.0
    assert [call for call in mpv.calls if call[0] == "command"] == [("command", "playlist-next")]


def test_a_file_opened_after_a_swapped_in_still_holds_for_the_pace_again():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    swapped_in(mpv, control, at=102.0)

    control.load(Path("made-up-next.png"))

    assert mpv.image_display_duration == 4.0


def ran_out_on_a_swapped_in_still(mpv: FakeMpv) -> Control:
    mpv.eof_reached = False
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    swapped_in(mpv, control, at=102.0)
    control.now = 104.05
    control.push_still()
    return control


def test_a_file_opened_after_a_swapped_in_still_ran_out_has_not():
    mpv = FakeMpv()
    control = ran_out_on_a_swapped_in_still(mpv)

    control.load(Path("made-up-next.png"))

    assert control.eof is False


def test_a_pace_set_while_a_still_is_swapped_in_leaves_mpv_holding_it():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    swapped_in(mpv, control, at=102.0)

    control.set_pace(6.0)

    assert mpv.image_display_duration == "inf"


def test_a_file_opened_is_dealt_a_move_of_its_own_though_it_was_once_swapped_in():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    swapped_in(mpv, control, at=101.0, name="made-up-scene.png")

    control.load(Path("made-up-scene.png"))
    mpv.report("path", "made-up-scene.png")

    assert deals.dealt == 2


def test_a_picture_opened_again_after_its_hold_makes_its_move_again():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    control.now = 104.5
    control.load(Path("made-up-scene.png"))
    mpv.report("path", "made-up-scene.png")

    assert drawn_at(control, mpv, 106.5) == pytest.approx(CREEP.at(0.5).placement())


def test_every_picture_opened_is_dealt_one_move_whatever_mpv_reports_between():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    control.load(Path("made-up-scene.png"))
    mpv.report("path", None)
    control.load(Path("made-up-scene.png"))
    mpv.report("path", "made-up-scene.png")
    mpv.report("path", None)
    mpv.report("path", "made-up-other.png")

    assert deals.dealt == 3


def test_a_picture_the_engine_settles_on_after_coming_round_to_itself_makes_a_new_move():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT))
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.stage_next(Path("made-up-scene.png"))

    control.now = 104.5
    mpv.playlist_pos = 1
    control.settle_on_the_next()

    assert drawn_at(control, mpv, 106.5) == pytest.approx(DRIFT.at(0.5).placement())


def test_a_picture_the_engine_settles_on_is_dealt_one_move_though_mpv_reports_it_opening():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.stage_next(Path("made-up-next.png"))

    mpv.playlist_pos = 1
    mpv.report("path", "made-up-next.png")
    control.settle_on_the_next()

    assert deals.dealt == 2


def test_a_picture_settled_on_from_under_a_still_swapped_in_over_it_is_dealt_one_move():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.stage_next(Path("made-up-scene.png"))
    swapped_in(mpv, control, at=102.0)

    control.now = 104.05
    control.push_still()
    mpv.playlist_pos = 1
    mpv.report("path", "made-up-scene.png")
    control.settle_on_the_next()

    assert deals.dealt == 2


def test_a_still_swapped_in_on_a_locked_engine_never_runs_out():
    mpv = FakeMpv()
    mpv.eof_reached = False
    control = Control(mpv, now=100.0, looping=True)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    swapped_in(mpv, control, at=102.0)

    control.now = 110.0
    control.push_still()

    assert control.eof is False


def test_a_still_swapped_in_after_the_engine_let_go_of_its_file_stages_nothing():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    control.stage_next(Path("made-up-next.png"))
    control.stop()
    mpv.calls.clear()

    control.swap_still(Path("made-up-frame.png"))

    assert mpv.calls == [("play", "made-up-frame.png"), ("clear",)]


def drawn_at(control: Control, mpv: FakeMpv, now: float) -> tuple[float, float, float]:
    control.now = now
    control.push_still()
    return mpv.video_zoom, mpv.video_align_x, mpv.video_align_y


def test_an_unlocked_picture_past_its_hold_stays_where_its_move_ended():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    assert drawn_at(control, mpv, 104.05) == pytest.approx(CREEP.at(1.0).placement())


def test_locking_a_picture_has_it_make_a_new_move_each_time_it_repeats():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT))
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    control.set_loop_file(True)

    assert drawn_at(control, mpv, 105.0) == pytest.approx(DRIFT.at(0.25).placement())


def test_a_engine_opened_locked_has_its_pictures_make_a_new_move_each_time_they_repeat():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT), looping=True)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    assert drawn_at(control, mpv, 105.0) == pytest.approx(DRIFT.at(0.25).placement())


def test_unlocking_a_picture_has_it_finish_the_move_it_is_making():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT), looping=True)
    control.set_pace(4.0)
    show_a_picture(control, mpv)

    control.now = 104.5
    control.set_loop_file(False)

    assert drawn_at(control, mpv, 105.0) == pytest.approx(DRIFT.at(0.25).placement())


def test_between_two_files_a_still_is_left_where_its_move_had_got_to():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, move=DRIFT)
    control.set_pace(4.0)
    show_a_picture(control, mpv)
    control.now = 101.0
    control.push_still()

    mpv.report("current-tracks/video/image", None)
    control.now = 101.5
    control.push_still()

    assert (mpv.video_zoom, mpv.video_align_x, mpv.video_align_y) == DRIFT.at(0.25).placement()


def test_a_file_that_would_not_open_leaves_the_engine_with_nothing_up():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.idle_active = True

    assert control.idle is True


def test_a_file_that_opened_is_not_nothing_up():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.idle_active = False

    assert control.idle is False


def test_the_size_on_screen_is_the_one_mpv_scaled_the_file_to():
    mpv = FakeMpv()
    control = Control(mpv)

    mpv.report("video-out-params", {"dw": 1920, "dh": 816})

    assert control.video_dims == (1920, 816)


def test_between_files_there_is_no_size():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-out-params", {"dw": 1920, "dh": 816})

    mpv.report("video-out-params", None)

    assert control.video_dims == (0, 0)


def test_letting_go_of_the_file_on_screen_unloads_it():
    mpv = FakeMpv()
    control = Control(mpv)

    control.stop()

    assert ("command", "stop") in mpv.calls


WIDE_WINDOW = (1080, 524)


def test_as_many_portrait_pictures_as_fit_side_by_side_fill_a_wide_window():
    assert tiles_across((1080, 1920), WIDE_WINDOW) == 3


def test_a_landscape_picture_is_never_tiled_however_wide_the_window():
    assert tiles_across((1920, 1080), (4000, 1000)) == 1


def test_a_window_taller_than_it_is_wide_is_never_tiled_even_by_a_narrow_picture():
    assert tiles_across((300, 1200), (1080, 1396)) == 1


def test_a_picture_not_measured_yet_is_not_tiled():
    assert tiles_across((0, 0), WIDE_WINDOW) == 1


PORTRAIT_SOURCE = {"w": 1080, "h": 1920, "dw": 1080, "dh": 1920}


def _tiling_calls(mpv: FakeMpv) -> list[tuple]:
    return [call for call in mpv.calls if call[:2] == ("command", "change-list")]


def test_tiling_a_portrait_picture_across_a_wide_window_widens_its_shape_by_the_count():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-dec-params", PORTRAIT_SOURCE)

    control.tile_to_fill(*WIDE_WINDOW)

    assert _tiling_calls(mpv) == [
        ("command", "change-list", "glsl-shaders", "set", str(TILES_SHADER)),
        ("command", "change-list", "glsl-shader-opts", "set", "tiles=3"),
    ]
    assert mpv.video_aspect_override == "27:16"


def test_a_frame_that_changes_nothing_asks_mpv_for_nothing():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-dec-params", PORTRAIT_SOURCE)
    control.tile_to_fill(*WIDE_WINDOW)
    asked = list(mpv.calls)

    control.tile_to_fill(*WIDE_WINDOW)

    assert mpv.calls == asked


TALL_WINDOW = (1080, 1396)


def test_a_window_turned_tall_takes_the_tiles_away():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-dec-params", PORTRAIT_SOURCE)
    control.tile_to_fill(*WIDE_WINDOW)

    control.tile_to_fill(*TALL_WINDOW)

    assert _tiling_calls(mpv)[-1] == ("command", "change-list", "glsl-shaders", "clr", "")
    assert mpv.video_aspect_override == "no"


def test_a_landscape_file_after_a_tiled_one_takes_the_tiles_away():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-dec-params", PORTRAIT_SOURCE)
    control.tile_to_fill(*WIDE_WINDOW)

    mpv.report("video-dec-params", {"w": 1920, "h": 1080, "dw": 1920, "dh": 1080})
    control.tile_to_fill(*WIDE_WINDOW)

    assert _tiling_calls(mpv)[-1] == ("command", "change-list", "glsl-shaders", "clr", "")
    assert mpv.video_aspect_override == "no"


def test_the_source_shape_outlives_the_gap_between_files():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-dec-params", PORTRAIT_SOURCE)

    mpv.report("video-dec-params", None)

    assert control.source_dims == (1080, 1920)


def test_a_portrait_file_of_another_size_but_the_same_shape_keeps_its_tiles():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-dec-params", PORTRAIT_SOURCE)
    control.tile_to_fill(*WIDE_WINDOW)
    asked = list(mpv.calls)

    mpv.report("video-dec-params", {"w": 720, "h": 1280, "dw": 720, "dh": 1280})
    control.tile_to_fill(*WIDE_WINDOW)

    assert mpv.calls == asked


def test_the_tile_shader_ships_beside_the_engine_and_takes_its_count_as_a_parameter():
    assert "//!PARAM tiles" in TILES_SHADER.read_text(encoding="utf-8")


class _MpvWithNoMemoryForAnOverlay(FakeMpv):
    def overlay_add(self, *_args) -> None:
        raise SystemError("Error running mpv command", -12, ())


def test_an_overlay_mpv_has_no_memory_to_copy_reaches_the_window_as_running_out_of_memory():
    control = Control(_MpvWithNoMemoryForAnOverlay())

    with pytest.raises(MemoryError):
        control.overlay(10, 0, 0, np.zeros((2, 2, 4), dtype=np.uint8))
