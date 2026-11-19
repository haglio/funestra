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
from funestra.ken_burns import Fit, zoom_in
from funestra.mpv_engine import (
    TILES_SHADER,
    MpvEngine,
    _client_size,
    _MpvControl,
    _shared_options,
    tiles_across,
)


class FakeMpv:
    frame_drop_count = decoder_frame_drop_count = vo_delayed_frame_count = 0

    def __init__(self, *, pos: int = 0, count: int = 2) -> None:
        self.observers: dict[str, object] = {}
        self.heard: dict[str, object] = {}
        self.event_callbacks: list = []
        self.reads: list[str] = []
        self._playlist_pos = pos
        self._idle_active = False
        self.duration = None
        self.playlist_count = count
        self.calls: list[tuple] = []
        self.audio_device_list: list[dict] = []
        self.audio_device = "auto"
        self.__dict__.update(dict.fromkeys(PLACING, 0.0))

    @property
    def playlist_pos(self) -> int:
        self.reads.append("playlist-pos")
        return self._playlist_pos

    @playlist_pos.setter
    def playlist_pos(self, pos: int) -> None:
        self._playlist_pos = pos
        self.report("playlist-pos", pos)

    @property
    def idle_active(self) -> bool:
        self.reads.append("idle-active")
        return self._idle_active

    @idle_active.setter
    def idle_active(self, idle: bool) -> None:
        self._idle_active = idle
        self.report("idle-active", idle)

    def observe_property(self, name: str, handler) -> None:
        self.observers[name] = handler
        if name == "playlist-pos":
            handler(name, self._playlist_pos)

    def register_event_callback(self, callback) -> None:
        self.event_callbacks.append(callback)

    def send(self, event_id: int) -> None:
        for callback in self.event_callbacks:
            callback(SimpleNamespace(event_id=SimpleNamespace(value=event_id)))

    def report(self, name: str, value) -> None:
        if name in self.heard and self.heard[name] == value:
            return
        self.heard[name] = value
        if name in self.observers:
            self.observers[name](name, value)

    def playlist_clear(self) -> None:
        self.calls.append(("clear",))
        if self._playlist_pos >= 0:
            self.playlist_pos, self.playlist_count = 0, 1

    def playlist_remove(self, index: int) -> None:
        self.calls.append(("remove", index))

    def loadfile(self, path: str, mode: str) -> None:
        self.calls.append(("loadfile", path, mode))
        if mode == "append":
            self.playlist_count += 1

    def play(self, path: str) -> None:
        self.calls.append(("play", path))
        self.playlist_pos, self.playlist_count = 0, 1

    def command(self, name: str, *args) -> None:
        if name == "playlist-next" and self._nothing_after_the_entry_playing():
            raise SystemError("Error running mpv command", -12)
        self.calls.append(("command", name, *args))

    def _nothing_after_the_entry_playing(self) -> bool:
        return not 0 <= self._playlist_pos < self.playlist_count - 1

    def __setattr__(self, name: str, value) -> None:
        if name in PLACING:
            self.calls.append(("set", name, value))
        super().__setattr__(name, value)


PLACING = {"video_zoom", "video_align_x", "video_align_y"}


CREEP = zoom_in(0.0, 0.0)


class Control(_MpvControl):

    def __init__(self, mpv, now: float = 0.0, viewport: tuple[int, int] = (0, 0),
                 deals: Deals | None = None, looping: bool = False) -> None:
        super().__init__(deals or Deals(CREEP), looping=looping)
        self.now = now
        self._viewport = viewport
        self._adopt(mpv)

    def _now(self) -> float:
        return self.now


WIDE = (1920, 1080)


def show_an_image(control: Control, mpv: FakeMpv, shape: tuple[int, int] = WIDE) -> None:
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


def test_the_engine_shows_a_video_only_when_mpv_says_its_video_track_is_no_image():
    mpv = FakeMpv()
    control = Control(mpv)

    shown = []
    for image in (False, None, True):
        mpv.report("current-tracks/video/image", image)
        shown.append(control.showing_video)

    assert shown == [True, False, False]


def moved_on(mpv: FakeMpv) -> int:
    return sum(1 for call in mpv.calls if call == ("command", "playlist-next"))


def an_image_with_the_next_staged(pace_s: float = 4.0, **control) -> tuple[FakeMpv, Control]:
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, **control)
    control.set_pace(pace_s)
    show_an_image(control, mpv)
    control.stage_next(Path("made-up-next.png"))
    return mpv, control


def pushed_at(control: Control, *moments: float) -> None:
    for now in moments:
        control.now = now
        control.push_still()


def test_every_engine_opens_mpv_holding_images_up_for_its_own_clock_to_end():
    options = _shared_options(muted=False, loop_file=False, prefetch=True)

    assert options["image_display_duration"] == "inf"


def test_a_pace_reaches_the_engines_clock_and_never_mpvs():
    mpv, _control = an_image_with_the_next_staged(2.5)

    assert "image_display_duration" not in vars(mpv)


def test_an_image_moves_on_to_the_staged_clip_once_its_pace_has_gone_by():
    mpv, control = an_image_with_the_next_staged(4.0)

    pushed_at(control, 103.9)
    assert moved_on(mpv) == 0
    pushed_at(control, 104.05, 104.1, 104.2)
    assert moved_on(mpv) == 1


def test_the_engine_shows_an_image_when_mpv_says_its_video_track_is_an_image():
    mpv = FakeMpv()
    control = Control(mpv)

    mpv.report("current-tracks/video/image", True)
    assert control.showing_image is True

    mpv.report("current-tracks/video/image", None)
    assert control.showing_image is False


# Every Lua script mpv loads for itself, by the option that keeps it out.
MPVS_OWN_SCRIPTS = (
    "osc", "load_scripts", "load_stats_overlay", "load_osd_console",
    "load_auto_profiles", "load_select", "load_positioning", "load_commands",
    "ytdl",
)


def test_a_engine_runs_none_of_mpvs_lua_scripts():
    options = _shared_options(muted=False, loop_file=True, prefetch=False)

    assert {name: options.get(name) for name in MPVS_OWN_SCRIPTS} == dict.fromkeys(
        MPVS_OWN_SCRIPTS, "no")


def _options_mpv_opened_with(monkeypatch, **engine_args) -> dict:
    opened: dict = {}

    def open_mpv(**options):
        opened.update(options)
        return FakeMpv()

    monkeypatch.setattr(mpv_engine, "_import_mpv", lambda: SimpleNamespace(MPV=open_mpv))
    MpvEngine(4242, **engine_args)
    return opened


def test_a_window_never_heard_opens_mpv_with_no_sound_track_for_a_sound_device_to_hold(
        monkeypatch):
    assert _options_mpv_opened_with(monkeypatch, audio=False)["aid"] == "no"


def test_a_window_that_can_be_heard_leaves_mpv_its_sound_track(monkeypatch):
    assert "aid" not in _options_mpv_opened_with(monkeypatch)


def test_staging_the_next_clip_never_removes_by_index():
    mpv = FakeMpv(pos=0, count=2)
    Control(mpv).stage_next(Path("alpha.mp4"))
    assert ("clear",) in mpv.calls
    assert not [call for call in mpv.calls if call[0] == "remove"]
    assert mpv.calls[-1] == ("loadfile", "alpha.mp4", "append")


def test_staging_holds_up_when_mpv_says_nothing_is_playing():
    mpv = FakeMpv(pos=-1, count=3)
    Control(mpv).stage_next(Path("beta.mp4"))
    assert not [call for call in mpv.calls if call[0] == "remove"]
    assert mpv.calls[-1] == ("loadfile", "beta.mp4", "append")


def test_staging_the_clip_already_staged_asks_mpv_nothing():
    mpv = FakeMpv(pos=0, count=2)
    control = Control(mpv)
    control.stage_next(Path("alpha.mp4"))
    mpv.calls.clear()

    control.stage_next(Path("alpha.mp4"))

    assert mpv.calls == []


def test_opening_a_file_forgets_whatever_was_staged_after_the_last_one():
    mpv = FakeMpv(pos=0, count=2)
    control = Control(mpv)
    control.stage_next(Path("alpha.mp4"))
    control.load(Path("beta.mp4"))
    mpv.calls.clear()

    control.stage_next(Path("alpha.mp4"))

    assert mpv.calls[-1] == ("loadfile", "alpha.mp4", "append")


def test_setting_a_volume_leaves_a_muted_engine_muted_which_the_silent_test_runs_rely_on():
    mpv = FakeMpv()
    mpv.mute = True

    Control(mpv).set_volume(80)

    assert (mpv.mute, mpv.volume) == (True, 80)


def test_muting_leaves_the_volume_where_it_was():
    mpv = FakeMpv()
    mpv.volume = 70

    Control(mpv).set_muted(True)

    assert (mpv.mute, mpv.volume) == (True, 70)


def test_clearing_the_staged_entry_keeps_the_clip_on_screen():
    mpv = FakeMpv(pos=0, count=2)
    Control(mpv).clear_next()
    assert mpv.calls == [("clear",)]


def test_settling_on_the_next_clip_keeps_it_on_screen():
    mpv = FakeMpv(pos=1, count=2)
    Control(mpv).settle_on_the_next()
    assert mpv.calls == [("clear",)]


def test_no_entry_playing_does_not_read_as_having_advanced():
    assert Control(FakeMpv(pos=-1)).advanced_to_next is False
    assert Control(FakeMpv(pos=0)).advanced_to_next is False
    assert Control(FakeMpv(pos=1)).advanced_to_next is True


class BlockingMpv(FakeMpv):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.terminated = 0

    @property
    def frame_drop_count(self):
        self.entered.set()
        self.release.wait(10.0)
        return 1

    def terminate(self) -> None:
        self.terminated += 1
        self.calls.append(("terminate",))


def test_close_waits_for_a_read_that_is_still_inside_mpv():
    mpv = BlockingMpv()
    control = Control(mpv)
    reading = threading.Thread(target=control.frame_counts)
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
    mpv = BlockingMpv()
    control = Control(mpv)
    mpv.report("container-fps", 25.0)
    reading = threading.Thread(target=control.frame_counts)
    reading.start()
    assert mpv.entered.wait(5.0)

    try:
        assert control.frame_rate == 25.0
    finally:
        mpv.release.set()
        reading.join(timeout=10.0)


def test_a_call_arriving_after_the_close_reaches_no_handle():
    mpv = BlockingMpv()
    mpv.release.set()
    control = Control(mpv)
    control.close()
    assert mpv.terminated == 1

    control.load(Path("alpha.mp4"))
    control.seek_ms(1000)
    assert control.position_ms == 0.0
    assert control.duration_ms == 0.0
    assert control.advanced_to_next is False
    assert mpv.calls == [("terminate",)]


def test_closing_twice_frees_once_since_python_mpv_s_own_free_has_no_guard_against_a_second_call():
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

    def terminate(self) -> None:
        ctypes.windll.ole32.CoUninitialize()


def _on_a_thread_holding_an_sta(work) -> None:
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
    mpv = SlowTeardown()
    torn_down_at_return: list[bool] = []

    def close_then_look() -> None:
        Control(mpv).close()
        torn_down_at_return.append(mpv.torn_down.is_set())

    _on_a_thread_holding_an_sta(close_then_look)
    assert torn_down_at_return == [True]


class EventThreadTeardown(FakeMpv):

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


def test_a_radio_station_the_engine_opens_sounds_where_the_engine_does(monkeypatch):
    opened: dict = {}

    class StationMpv:
        def __init__(self, **options):
            opened.update(options)

        def loadfile(self, path, mode):
            pass

    monkeypatch.setattr(mpv_engine, "_import_mpv", lambda: SimpleNamespace(MPV=StationMpv))
    monkeypatch.setattr(audio_outputs, "software_outputs", frozenset)
    mpv = FakeMpv()
    mpv.audio_device_list = [STREAMING, HEADSET]
    control = Control(mpv)
    control.set_audio_device_matching("Headset")

    control.radio_station([Path("alpha.mp4")])

    assert opened["audio_device"] == HEADSET["name"]


def test_an_image_is_drawn_closer_as_its_hold_runs_out():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    control.now = 102.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.5).zoom))


def test_a_clip_after_an_image_is_drawn_as_it_comes():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(DRIFT))
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.now = 101.0
    control.push_still()

    mpv.report("path", "made-up-scene.mp4")
    mpv.report("current-tracks/video/image", False)
    control.push_still()

    assert (mpv.video_zoom, mpv.video_align_x, mpv.video_align_y) == (0.0, 0.0, 0.0)


def test_a_frozen_room_holds_the_image_where_its_move_had_got_to():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    control.now = 101.0
    control.set_paused(True)
    control.now = 103.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.25).zoom))


def test_a_pan_reaches_mpv_as_how_far_the_image_leans_each_way():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(DRIFT))
    control.set_pace(4.0)
    show_an_image(control, mpv)

    control.push_still()

    assert (mpv.video_zoom, mpv.video_align_x, mpv.video_align_y) == DRIFT.at(0.0).placement()


def test_every_engine_keeps_an_image_centered_along_a_side_it_fits_inside():
    options = _shared_options(muted=False, loop_file=False, prefetch=True)

    assert options["video_recenter"] == "yes"


def test_an_audio_device_that_cannot_open_never_stops_the_video():
    options = _shared_options(muted=False, loop_file=False, prefetch=False)

    assert options["audio_fallback_to_null"] == "yes"


def test_mpv_is_asked_for_warnings_and_worse_only():
    options = _shared_options(muted=False, loop_file=False, prefetch=False)

    assert options["loglevel"] == "warn"


@pytest.mark.parametrize(("level", "logged"), [("fatal", 50), ("error", 40), ("warn", 30)])
def test_an_mpv_message_reaches_the_log_at_the_matching_level(caplog, level, logged):
    with caplog.at_level(1, logger=mpv_engine.logger.name):
        mpv_engine._log_mpv(level, "vo", "made-up trouble  ")

    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [(logged, "mpv vo: made-up trouble")]


def test_an_audio_device_underrun_is_news_since_mpv_rides_it_out_by_itself(caplog):
    with caplog.at_level(1, logger=mpv_engine.logger.name):
        mpv_engine._log_mpv("warn", "cplayer", "Audio device underrun detected.\n")

    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.INFO, "mpv cplayer: Audio device underrun detected.")]


def test_mpv_s_note_that_audio_and_video_drifted_apart_is_news_since_it_pulls_them_together_by_itself(caplog):
    paragraph = (
        "\n\nAudio/Video desynchronisation detected! Possible reasons include too slow\n"
        "hardware, temporary CPU spikes, broken drivers, and broken files. Audio\n"
        "position will not match to the video (see A-V status field).\n"
        "Consider trying `--profile=fast` and/or `--hwdec=auto` as they may help.\n\n")
    with caplog.at_level(1, logger=mpv_engine.logger.name):
        for line in paragraph.splitlines(keepends=True):
            mpv_engine._log_mpv("warn", "cplayer", line)

    assert {r.levelno for r in caplog.records} == {logging.INFO}


def test_a_blank_line_from_mpv_writes_nothing(caplog):
    with caplog.at_level(1, logger=mpv_engine.logger.name):
        mpv_engine._log_mpv("warn", "cplayer", "\n")

    assert caplog.records == []


def test_the_next_entry_is_opened_ahead_only_where_asked_for_so_a_satellite_s_auto_advance_cuts_to_a_video_already_loaded():
    ahead = _shared_options(muted=False, loop_file=False, prefetch=True)
    alone = _shared_options(muted=False, loop_file=False, prefetch=False)

    assert (ahead.get("prefetch_playlist"), "prefetch_playlist" in alone) == ("yes", False)


def test_a_looping_engine_repeats_its_file_and_another_walks_on():
    looping = _shared_options(muted=False, loop_file=True, prefetch=False)
    walking = _shared_options(muted=False, loop_file=False, prefetch=False)

    assert (looping["loop_file"], walking["loop_file"]) == ("inf", "no")


def test_a_zoom_about_the_middle_asks_mpv_for_the_zoom_alone():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.now = 102.0

    control.push_still()

    assert [call[1] for call in mpv.calls if call[0] == "set"] == ["video_zoom"]


def test_an_image_that_has_not_moved_since_the_last_frame_asks_mpv_for_nothing():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(DRIFT))
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.push_still()
    asked = list(mpv.calls)

    control.push_still()

    assert mpv.calls == asked


def test_a_still_swapped_in_carries_on_the_move_of_the_image_it_replaced():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.now = 102.0

    control.swap_image(Path("made-up-frame.png"))
    mpv.report("path", "made-up-frame.png")
    control.push_still()

    assert deals.dealt == 1
    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.5).zoom))


def swapped_in(mpv: FakeMpv, control: Control, at: float, name: str = "made-up-frame.png") -> None:
    control.now = at
    control.swap_image(Path(name))
    mpv.report("path", name)


def test_swapping_a_still_in_hands_mpv_no_clock_to_end_it_on():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    swapped_in(mpv, control, at=102.0)

    assert "image_display_duration" not in vars(mpv)


def test_a_swapped_in_still_runs_out_when_the_image_it_replaced_would_have():
    mpv, control = an_image_with_the_next_staged(4.0)
    swapped_in(mpv, control, at=102.0)

    pushed_at(control, 103.9)
    assert moved_on(mpv) == 0
    pushed_at(control, 104.05)
    assert moved_on(mpv) == 1


def test_an_image_mpv_rolled_onto_by_itself_stays_up_until_the_funestra_follows_the_roll():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    control.load(Path("made-up-clip.mp4"))
    mpv.report("path", "made-up-clip.mp4")
    mpv.report("current-tracks/video/image", False)
    control.stage_next(Path("made-up-next.png"))
    mpv.calls.clear()

    control.now = 112.0
    mpv.playlist_pos = 1
    mpv.report("path", "made-up-next.png")
    mpv.report("current-tracks/video/image", True)
    control.push_still()

    assert [call for call in mpv.calls if call[0] == "command"] == []


def test_a_still_swapped_in_keeps_the_next_clip_staged_after_it():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.stage_next(Path("made-up-next.png"))
    mpv.calls.clear()

    control.swap_image(Path("made-up-frame.png"))

    assert mpv.calls == [("play", "made-up-frame.png"), ("clear",),
                         ("loadfile", "made-up-next.png", "append")]


def test_a_still_swapped_in_after_the_engine_rolled_onto_its_staged_clip_stages_nothing():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    control.stage_next(Path("made-up-next.png"))
    control.settle_on_the_next()
    mpv.calls.clear()

    control.swap_image(Path("made-up-frame.png"))

    assert mpv.calls == [("play", "made-up-frame.png"), ("clear",)]


def test_the_image_after_one_that_moved_on_counts_its_own_pace_from_when_it_came_up():
    mpv, control = an_image_with_the_next_staged(4.0)
    swapped_in(mpv, control, at=102.0)
    pushed_at(control, 104.05)

    control.now = 104.2
    mpv.playlist_pos = 1
    mpv.report("path", "made-up-next.png")
    control.settle_on_the_next()
    control.stage_next(Path("made-up-after.png"))
    pushed_at(control, 108.1)
    assert moved_on(mpv) == 1
    pushed_at(control, 108.25)
    assert moved_on(mpv) == 2


def test_a_pace_set_while_a_still_is_swapped_in_times_it_from_then_on():
    mpv, control = an_image_with_the_next_staged(4.0)
    swapped_in(mpv, control, at=102.0)

    control.set_pace(8.0)

    pushed_at(control, 105.9)
    assert moved_on(mpv) == 0
    pushed_at(control, 106.05)
    assert moved_on(mpv) == 1


def test_an_image_says_how_far_into_its_pace_it_is():
    _mpv, control = an_image_with_the_next_staged(4.0)

    pushed_at(control, 101.0)

    assert control.image_time == pytest.approx((1_000.0, 4_000.0))


def test_a_video_has_no_image_time():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    mpv.report("path", "made-up-scene.mp4")
    mpv.report("current-tracks/video/image", False)

    pushed_at(control, 101.0)

    assert control.image_time is None


def test_a_locked_images_time_comes_round_again_each_pace():
    _mpv, control = an_image_with_the_next_staged(4.0, looping=True)

    pushed_at(control, 105.0)

    assert control.image_time == pytest.approx((1_000.0, 4_000.0))


def test_a_press_back_along_an_images_track_gives_it_that_much_longer():
    mpv, control = an_image_with_the_next_staged(4.0)
    pushed_at(control, 103.0)

    control.seek_image(1_000.0)

    pushed_at(control, 103.0)
    assert control.image_time == pytest.approx((1_000.0, 4_000.0))
    pushed_at(control, 105.9)
    assert moved_on(mpv) == 0
    pushed_at(control, 106.05)
    assert moved_on(mpv) == 1


def test_an_images_slow_zoom_goes_back_with_its_time():
    mpv, control = an_image_with_the_next_staged(4.0)
    pushed_at(control, 103.0)

    control.seek_image(1_000.0)

    assert drawn_at(control, mpv, 103.0) == pytest.approx(CREEP.at(0.25).placement())


def test_a_press_at_the_end_of_an_images_track_moves_it_on():
    mpv, control = an_image_with_the_next_staged(4.0)

    control.seek_image(4_000.0)

    pushed_at(control, 100.1)
    assert moved_on(mpv) == 1


def test_a_press_along_the_track_of_an_image_held_for_nought_changes_nothing():
    mpv, control = an_image_with_the_next_staged(0.0)

    control.seek_image(2_000.0)

    pushed_at(control, 1_000.0)
    assert control.image_time == (0.0, 0.0)
    assert moved_on(mpv) == 0


def test_an_image_held_for_less_than_its_pace_moves_on_then_and_counts_its_time_against_it():
    mpv, control = an_image_with_the_next_staged(4.0)

    control.hold_image_for(2.0)

    pushed_at(control, 101.0)
    assert control.image_time == pytest.approx((1_000.0, 2_000.0))
    pushed_at(control, 101.9)
    assert moved_on(mpv) == 0
    pushed_at(control, 102.05)
    assert moved_on(mpv) == 1
    assert control.image_time == pytest.approx((2_000.0, 2_000.0))


def test_an_image_held_for_less_than_its_pace_makes_its_move_at_the_pace():
    mpv, control = an_image_with_the_next_staged(4.0)
    control.hold_image_for(2.0)

    assert drawn_at(control, mpv, 101.0) == pytest.approx(CREEP.at(0.25).placement())


def test_a_file_opened_is_dealt_a_move_of_its_own_though_it_was_once_swapped_in():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_an_image(control, mpv)
    swapped_in(mpv, control, at=101.0, name="made-up-scene.png")

    control.load(Path("made-up-scene.png"))
    mpv.report("path", "made-up-scene.png")

    assert deals.dealt == 2


def test_an_image_opened_again_after_its_hold_makes_its_move_again():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    control.now = 104.5
    control.load(Path("made-up-scene.png"))
    mpv.report("path", "made-up-scene.png")

    assert drawn_at(control, mpv, 106.5) == pytest.approx(CREEP.at(0.5).placement())


def test_every_image_opened_is_dealt_one_move_whatever_mpv_reports_between():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    control.load(Path("made-up-scene.png"))
    mpv.report("path", None)
    control.load(Path("made-up-scene.png"))
    mpv.report("path", "made-up-scene.png")
    mpv.report("path", None)
    mpv.report("path", "made-up-other.png")

    assert deals.dealt == 3


def test_an_image_the_engine_settles_on_after_coming_round_to_itself_makes_a_new_move():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT))
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.stage_next(Path("made-up-scene.png"))

    control.now = 104.5
    mpv.playlist_pos = 1
    control.settle_on_the_next()

    assert drawn_at(control, mpv, 106.5) == pytest.approx(DRIFT.at(0.5).placement())


def test_an_image_the_engine_settles_on_is_dealt_one_move_though_mpv_reports_it_opening():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.stage_next(Path("made-up-next.png"))

    mpv.playlist_pos = 1
    mpv.report("path", "made-up-next.png")
    control.settle_on_the_next()

    assert deals.dealt == 2


def test_an_image_settled_on_from_under_a_still_swapped_in_over_it_is_dealt_one_move():
    mpv = FakeMpv()
    deals = Deals(CREEP)
    control = Control(mpv, now=100.0, deals=deals)
    control.set_pace(4.0)
    show_an_image(control, mpv)
    control.stage_next(Path("made-up-scene.png"))
    swapped_in(mpv, control, at=102.0)

    control.now = 104.05
    control.push_still()
    mpv.playlist_pos = 1
    mpv.report("path", "made-up-scene.png")
    control.settle_on_the_next()

    assert deals.dealt == 2


def test_a_still_swapped_in_on_a_locked_engine_never_runs_out():
    mpv, control = an_image_with_the_next_staged(4.0, looping=True)
    swapped_in(mpv, control, at=102.0)

    pushed_at(control, 110.0)

    assert moved_on(mpv) == 0


def test_a_still_swapped_in_after_the_engine_let_go_of_its_file_stages_nothing():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    control.stage_next(Path("made-up-next.png"))
    control.stop()
    mpv.calls.clear()

    control.swap_image(Path("made-up-frame.png"))

    assert mpv.calls == [("play", "made-up-frame.png"), ("clear",)]


def drawn_at(control: Control, mpv: FakeMpv, now: float) -> tuple[float, float, float]:
    control.now = now
    control.push_still()
    return mpv.video_zoom, mpv.video_align_x, mpv.video_align_y


def test_an_unlocked_image_past_its_hold_stays_where_its_move_ended():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    assert drawn_at(control, mpv, 104.05) == pytest.approx(CREEP.at(1.0).placement())


def test_locking_an_image_has_it_make_a_new_move_each_time_it_repeats():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT))
    control.set_pace(4.0)
    show_an_image(control, mpv)

    control.set_loop_file(True)

    assert drawn_at(control, mpv, 105.0) == pytest.approx(DRIFT.at(0.25).placement())


def test_a_engine_opened_locked_has_its_images_make_a_new_move_each_time_they_repeat():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT), looping=True)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    assert drawn_at(control, mpv, 105.0) == pytest.approx(DRIFT.at(0.25).placement())


def test_unlocking_an_image_has_it_finish_the_move_it_is_making():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(CREEP, DRIFT), looping=True)
    control.set_pace(4.0)
    show_an_image(control, mpv)

    control.now = 104.5
    control.set_loop_file(False)

    assert drawn_at(control, mpv, 105.0) == pytest.approx(DRIFT.at(0.25).placement())


def test_between_two_files_a_still_is_left_where_its_move_had_got_to():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, deals=Deals(DRIFT))
    control.set_pace(4.0)
    show_an_image(control, mpv)
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


def test_between_files_there_is_no_size_and_a_caller_keeps_its_last_one_so_the_old_video_s_final_frame_stays_up():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("video-out-params", {"dw": 1920, "dh": 816})

    mpv.report("video-out-params", None)

    assert control.video_dims == (0, 0)


def test_letting_go_of_the_file_on_screen_unloads_it_so_it_can_be_moved():
    mpv = FakeMpv()
    control = Control(mpv)

    control.stop()

    assert ("command", "stop") in mpv.calls


WIDE_WINDOW = (1080, 524)


def test_as_many_portrait_items_as_fit_side_by_side_fill_a_wide_window():
    assert tiles_across((1080, 1920), WIDE_WINDOW) == 3


def test_a_landscape_item_is_never_tiled_however_wide_the_window():
    assert tiles_across((1920, 1080), (4000, 1000)) == 1


def test_a_window_taller_than_it_is_wide_is_never_tiled_even_by_a_narrow_item():
    assert tiles_across((300, 1200), (1080, 1396)) == 1


def test_an_item_not_measured_yet_is_not_tiled():
    assert tiles_across((0, 0), WIDE_WINDOW) == 1


PORTRAIT_SOURCE = {"w": 1080, "h": 1920, "dw": 1080, "dh": 1920}


def _tiling_calls(mpv: FakeMpv) -> list[tuple]:
    return [call for call in mpv.calls if call[:2] == ("command", "change-list")]


def test_tiling_a_portrait_item_across_a_wide_window_widens_its_shape_by_the_count():
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


FACE = (0.4, 0.1, 0.6, 0.3)


def test_a_locked_image_with_places_is_drawn_on_the_close_up_its_window_frames():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0, viewport=WIDE, deals=Deals(CREEP), looping=True)
    control.set_pace(4.0)
    show_an_image(control, mpv, (832, 1216))

    control.set_points_of_interest((FACE,))

    assert drawn_at(control, mpv, 104.0) == pytest.approx(
        Fit(WIDE, (832, 1216)).framing(FACE).placement())


SM_CXSCREEN, SM_CYSCREEN = 0, 1


def test_a_windows_size_is_read_off_windows_itself():
    user32 = ctypes.windll.user32
    screen = (user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN))

    assert _client_size(user32.GetDesktopWindow()) == screen


def test_a_window_that_is_not_there_has_no_size():
    assert _client_size(0) == (0, 0)


def test_a_windowed_engine_frames_its_close_ups_for_the_window_it_draws_into(monkeypatch):
    desktop = ctypes.windll.user32.GetDesktopWindow()
    monkeypatch.setattr(mpv_engine, "_import_mpv",
                        lambda: SimpleNamespace(MPV=lambda **_options: FakeMpv()))

    engine = MpvEngine(desktop)

    assert engine._fit().viewport == _client_size(desktop)


def test_the_frame_counts_are_mpvs_own_counters_of_dropped_and_delayed_frames():
    mpv = FakeMpv()
    mpv.frame_drop_count, mpv.decoder_frame_drop_count, mpv.vo_delayed_frame_count = 4, None, 2

    assert Control(mpv).frame_counts() == (4, 0, 2)


def _decoder_lines(caplog) -> list[tuple[str, str]]:
    return [(r.levelname, r.getMessage()) for r in caplog.records
            if r.name == "funestra.mpv_engine" and "decod" in r.getMessage()]


def _open_a_video(mpv: FakeMpv, path: str, decoder, source=PORTRAIT_SOURCE) -> None:
    mpv.report("path", path)
    mpv.report("current-tracks/video/image", False)
    mpv.report("hwdec-current", decoder)
    mpv.report("video-dec-params", source)


def test_each_video_opened_says_once_which_decoder_mpv_chose(caplog):
    caplog.set_level(logging.INFO, logger="funestra.mpv_engine")
    mpv = FakeMpv()
    Control(mpv)

    _open_a_video(mpv, "made-up-one.mp4", "nvdec")
    mpv.report("video-dec-params", {"w": 1080, "h": 1920, "dw": 1080, "dh": 1920, "rotate": 0})
    _open_a_video(mpv, "made-up-two.mp4", "nvdec")

    assert _decoder_lines(caplog) == [
        ("INFO", "mpv decodes this 1080x1920 video with nvdec"),
        ("INFO", "mpv decodes this 1080x1920 video with nvdec"),
    ]


@pytest.mark.parametrize("decoder", ["d3d11va-copy", "nvdec-copy", "no", "", None])
def test_a_video_decoded_on_the_processor_or_copied_back_is_warned_of(caplog, decoder):
    caplog.set_level(logging.INFO, logger="funestra.mpv_engine")
    mpv = FakeMpv()
    Control(mpv)

    _open_a_video(mpv, "made-up-one.mp4", decoder)

    [(level, line)] = _decoder_lines(caplog)
    assert level == "WARNING"
    assert line.startswith("mpv decodes this 1080x1920 video ")
    assert ("copies each frame back from the graphics card" in line) == str(decoder).endswith("-copy")


def test_an_image_says_nothing_of_a_decoder(caplog):
    caplog.set_level(logging.INFO, logger="funestra.mpv_engine")
    mpv = FakeMpv()
    control = Control(mpv)

    show_an_image(control, mpv)
    mpv.report("video-dec-params", {"w": 1920, "h": 1080, "dw": 1920, "dh": 1080})

    assert _decoder_lines(caplog) == []


def test_a_wheel_notch_zooms_in_keeping_the_point_under_the_pointer_where_it_was():
    mpv = FakeMpv()
    control = Control(mpv, viewport=WIDE)
    show_an_image(control, mpv)

    control.zoom_at(480, 270, steps=1)
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(1.25))
    assert (mpv.video_align_x, mpv.video_align_y) == pytest.approx((-0.5, -0.5))


def placing(mpv: FakeMpv) -> tuple[float, float, float]:
    return mpv.video_zoom, mpv.video_align_x, mpv.video_align_y


def zoomed_on_an_image(pace_s: float = 0.0, **control) -> tuple[FakeMpv, Control]:
    mpv = FakeMpv()
    control = Control(mpv, viewport=WIDE, **control)
    control.set_pace(pace_s)
    show_an_image(control, mpv)
    control.zoom_at(960, 540, steps=1)
    control.push_still()
    return mpv, control


def test_the_wheel_never_zooms_out_past_the_whole_item():
    mpv, control = zoomed_on_an_image()

    control.zoom_at(100, 100, steps=-3)
    control.push_still()

    assert placing(mpv) == (0.0, 0.0, 0.0)


def test_a_drag_moves_the_zoomed_item_the_way_the_mouse_went():
    mpv, control = zoomed_on_an_image()

    control.pan_by(100, 0)
    control.push_still()

    assert placing(mpv) == pytest.approx((math.log2(1.25), -5 / 12, 0.0))


def test_a_drag_stops_at_the_items_edge():
    mpv, control = zoomed_on_an_image()

    control.pan_by(1000, -1000)
    control.push_still()

    assert placing(mpv) == pytest.approx((math.log2(1.25), -1.0, 1.0))


def test_a_drag_at_normal_size_moves_nothing():
    mpv = FakeMpv()
    control = Control(mpv, viewport=WIDE)
    show_an_image(control, mpv)

    control.pan_by(100, 100)
    control.push_still()

    assert placing(mpv) == (0.0, 0.0, 0.0)


def test_the_next_item_comes_on_at_normal_size():
    mpv, control = zoomed_on_an_image()

    control.load(Path("made-up-next.mp4"))
    mpv.report("current-tracks/video/image", False)
    control.push_still()

    assert placing(mpv) == (0.0, 0.0, 0.0)


def test_a_zoomed_image_goes_on_drifting_under_the_zoom():
    mpv, control = zoomed_on_an_image(pace_s=4.0, now=100.0)

    control.now = 102.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.5).zoom * 1.25))


def test_a_zoomed_image_still_moves_on_when_its_time_is_up():
    mpv, control = an_image_with_the_next_staged(pace_s=4.0, viewport=WIDE)
    control.zoom_at(960, 540, steps=1)

    pushed_at(control, 105.0)

    assert moved_on(mpv) == 1


def test_the_image_after_a_zoomed_one_drifts():
    mpv, control = zoomed_on_an_image(pace_s=4.0, now=100.0)

    control.load(Path("made-up-next.png"))
    control.now = 102.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(CREEP.at(0.5).zoom))


def test_a_video_starting_over_keeps_its_zoom():
    mpv = FakeMpv()
    control = Control(mpv, viewport=WIDE)
    control.load(Path("made-up-scene.mp4"))
    mpv.report("current-tracks/video/image", False)
    mpv.report("video-out-params", {"dw": 1920, "dh": 1080})
    control.zoom_at(960, 540, steps=1)
    control.push_still()
    zoomed = placing(mpv)

    control.load(Path("made-up-scene.mp4"))
    control.push_still()

    assert placing(mpv) == zoomed


START_FILE, FILE_LOADED = 6, 8


def test_what_a_pass_asks_about_the_file_playing_is_answered_from_what_mpv_reported():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("time-pos", 1.5)
    mpv.report("duration", 20.0)
    mpv.playlist_pos = 1
    mpv.idle_active = False
    mpv.reads.clear()

    for _ in range(5):
        answers = (control.position_ms, control.duration_ms, control.advanced_to_next,
                   control.idle)

    assert (answers, mpv.reads) == ((1_500.0, 20_000.0, True, False), [])


class SlowToReport(FakeMpv):
    def report(self, name: str, value) -> None:
        if name != "playlist-pos" or self.reporting:
            super().report(name, value)

    reporting = True


def test_a_roll_is_not_read_twice_while_mpv_has_yet_to_report_its_playlist_cleared():
    mpv = SlowToReport()
    control = Control(mpv)
    mpv.playlist_pos = 1
    mpv.reporting = False

    control.settle_on_the_next()

    assert control.advanced_to_next is False


def test_a_seek_moves_the_playhead_it_answers_with_at_once_as_mpv_itself_does():
    control = Control(FakeMpv())

    control.seek_ms(4_200.0)

    assert control.position_ms == 4_200.0


def test_between_two_files_there_is_no_length_or_playhead_to_answer_with():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("time-pos", 9.0)
    mpv.report("duration", 20.0)

    mpv.send(START_FILE)

    assert (control.position_ms, control.duration_ms) == (0.0, 0.0)


def test_opening_a_file_forgets_the_length_and_playhead_of_the_one_before():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("time-pos", 9.0)
    mpv.report("duration", 20.0)

    control.load(Path("beta.mp4"))

    assert (control.position_ms, control.duration_ms) == (0.0, 0.0)


def test_a_file_as_long_as_the_one_before_it_still_gets_its_length_since_mpv_reports_no_change():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("duration", 5.0)
    mpv.send(START_FILE)
    mpv.duration = 5.0

    mpv.send(FILE_LOADED)

    assert control.duration_ms == 5_000.0


class CountsLoopSets(FakeMpv):
    def __setattr__(self, name: str, value) -> None:
        if name.startswith("ab_loop"):
            self.calls.append(("set", name, value))
        super().__setattr__(name, value)


def test_with_no_loop_set_clearing_it_tells_mpv_nothing_since_every_file_opened_clears_it():
    mpv = CountsLoopSets()
    control = Control(mpv)

    for _ in range(3):
        control.clear_ab_loop()

    assert mpv.calls == []


def test_a_loop_that_was_set_is_cleared_once():
    mpv = CountsLoopSets()
    control = Control(mpv)
    control.set_ab_loop(2_000.0, 4_000.0)
    mpv.calls.clear()

    control.clear_ab_loop()
    control.clear_ab_loop()

    assert mpv.calls == [("set", "ab_loop_a", "no"), ("set", "ab_loop_b", "no")]
