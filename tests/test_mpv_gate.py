"""The lease that stops an engine's mpv being freed under a live call."""
from __future__ import annotations

import threading
import time

from funestra.mpv_gate import CallGate, mpv_call


def test_a_gate_with_nothing_inside_closes_at_once():
    gate = CallGate()
    started = time.monotonic()
    assert gate.close(timeout=5.0)
    assert (time.monotonic() - started) < 1.0


def test_a_call_inside_holds_the_close_off_and_then_lets_it_through():
    """The whole point: close() answers only once mpv is unoccupied."""
    gate = CallGate()
    inside = threading.Event()
    release = threading.Event()
    answered: list[bool] = []

    def caller() -> None:
        with gate.entered() as live:
            assert live
            inside.set()
            release.wait(5.0)

    def closer() -> None:
        answered.append(gate.close(timeout=5.0))

    worker = threading.Thread(target=caller)
    worker.start()
    assert inside.wait(5.0)
    shutting = threading.Thread(target=closer)
    shutting.start()
    shutting.join(timeout=0.3)
    assert shutting.is_alive()
    assert not answered
    release.set()
    shutting.join(timeout=5.0)
    worker.join(timeout=5.0)
    assert answered == [True]


def test_close_gives_up_rather_than_freeing_under_a_live_call():
    gate = CallGate()
    inside = threading.Event()
    release = threading.Event()

    def caller() -> None:
        with gate.entered() as live:
            assert live
            inside.set()
            release.wait(10.0)

    worker = threading.Thread(target=caller)
    worker.start()
    assert inside.wait(5.0)
    assert not gate.close(timeout=0.2)
    assert gate.inside == 1
    release.set()
    worker.join(timeout=5.0)


def test_a_close_that_gave_up_can_be_answered_once_the_call_returns():
    gate = CallGate()
    release = threading.Event()
    inside = threading.Event()

    def caller() -> None:
        with gate.entered() as live:
            assert live
            inside.set()
            release.wait(10.0)

    worker = threading.Thread(target=caller)
    worker.start()
    assert inside.wait(5.0)
    assert not gate.close(timeout=0.2)
    release.set()
    worker.join(timeout=5.0)
    assert gate.close(timeout=5.0)


def test_closing_bars_new_calls_immediately_so_a_looping_worker_cannot_extend_the_wait():
    gate = CallGate()
    assert gate.close(timeout=5.0)
    with gate.entered() as live:
        assert not live
    assert gate.closing
    assert gate.inside == 0


def test_only_one_close_ever_owns_the_teardown():
    """python-mpv's render-context free has no double-free guard; this is it."""
    gate = CallGate()
    assert gate.close(timeout=5.0)
    assert not gate.close(timeout=5.0)
    assert not gate.close(timeout=5.0)


def test_leases_nest_so_a_guarded_method_may_call_another():
    gate = CallGate()
    with gate.entered() as outer, gate.entered() as inner:
        assert outer
        assert inner
        assert gate.inside == 2
    assert gate.inside == 0
    assert gate.close(timeout=5.0)


class Guarded:
    def __init__(self) -> None:
        self._gate = CallGate()
        self.calls: list[str] = []

    @mpv_call(0.0)
    def position_ms(self) -> float:
        self.calls.append("position_ms")
        return 42.0

    @mpv_call()
    def seek(self) -> None:
        self.calls.append("seek")


def test_a_guarded_call_after_the_close_does_nothing_and_says_so():
    engine = Guarded()
    assert engine.position_ms() == 42.0
    assert engine._gate.close(timeout=5.0)
    assert engine.position_ms() == 0.0
    assert engine.seek() is None
    assert engine.calls == ["position_ms"]
