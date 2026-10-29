"""The offscreen engine's word on which file each frame it draws shows, wired
to mpv: the file asked for, the events mpv sends as it opens and starts it, and
what mpv says of the frame it is about to draw.  A fake engine stands in for
libmpv, whose DLL and GL context the real one needs."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from funestra import render_engine

FILE_LOADED = 8
PLAYBACK_RESTART = 21
FRAME_PRESENT = 1
FRAME_REDRAW = 2


class FakeHandle:
    def __init__(self, **_options) -> None:
        self.observers: dict[str, list] = {}
        self.event_callbacks: list = []

    def observe_property(self, name, handler) -> None:
        self.observers.setdefault(name, []).append(handler)

    def register_event_callback(self, callback) -> None:
        self.event_callbacks.append(callback)

    def report(self, name, value) -> None:
        for handler in self.observers.get(name, []):
            handler(name, value)

    def send(self, event_id: int) -> None:
        event = SimpleNamespace(event_id=SimpleNamespace(value=event_id))
        for callback in self.event_callbacks:
            callback(event)

    def play(self, _path) -> None:
        pass

    def playlist_clear(self) -> None:
        pass


class FakeRenderContext:
    def __init__(self, handle, _api, **_params) -> None:
        self.handle = handle
        handle.render_context = self
        self.frame_waiting = False
        self.next_frame_flags = 0

    def update(self) -> bool:
        waiting, self.frame_waiting = self.frame_waiting, False
        return waiting

    def render(self, **_params) -> None:
        pass

    def announce(self, flags: int) -> None:
        self.frame_waiting = True
        self.next_frame_flags = flags


class FakeRenderParam:
    def __init__(self, name, value) -> None:
        assert name == "next_frame_info"
        self.value = SimpleNamespace(**value)


def _next_frame_info(handle, param) -> None:
    param.value.flags = handle.render_context.next_frame_flags


@pytest.fixture
def engine(monkeypatch):
    fake = SimpleNamespace(
        MPV=FakeHandle,
        MpvGlGetProcAddressFn=lambda function: function,
        MpvRenderContext=FakeRenderContext,
        MpvRenderParam=FakeRenderParam,
        MpvEventID=SimpleNamespace(FILE_LOADED=FILE_LOADED, PLAYBACK_RESTART=PLAYBACK_RESTART),
        _mpv_render_context_get_info=_next_frame_info,
    )
    monkeypatch.setattr(render_engine, "_import_mpv", lambda: fake)
    return fake


def test_a_file_asked_for_is_shown_as_itself_only_once_mpv_has_started_it(engine):
    engine = render_engine.MpvRenderEngine(lambda _name: 0)
    handle = engine._mpv
    context = engine._render_context
    flat = Path("C:/videos/flat.mp4")

    engine.load(flat)
    handle.report("path", str(flat))
    handle.send(FILE_LOADED)
    context.announce(FRAME_PRESENT)
    assert engine.has_frame_to_draw
    assert engine.render(0, 16, 9) is None

    handle.send(PLAYBACK_RESTART)
    context.next_frame_flags = FRAME_PRESENT | FRAME_REDRAW

    assert engine.has_frame_to_draw
    assert engine.render(0, 16, 9) == str(flat)


def _options_mpv_opened_with(monkeypatch, engine, **engine_args) -> dict:
    opened: dict = {}

    def open_mpv(**options):
        opened.update(options)
        return FakeHandle()

    monkeypatch.setattr(engine, "MPV", open_mpv)
    render_engine.MpvRenderEngine(lambda _name: 0, **engine_args)
    return opened


def test_an_offscreen_engine_never_heard_opens_mpv_with_no_sound_track(monkeypatch, engine):
    assert _options_mpv_opened_with(monkeypatch, engine, audio=False)["aid"] == "no"


def test_an_offscreen_engine_that_can_be_heard_leaves_mpv_its_sound_track(monkeypatch, engine):
    assert "aid" not in _options_mpv_opened_with(monkeypatch, engine)


def test_an_offscreen_engine_frames_its_close_ups_for_the_target_it_last_drew_into(engine):
    engine = render_engine.MpvRenderEngine(lambda _name: 0)

    engine.render(0, 1600, 900)

    assert engine._fit().window == (1600, 900)
