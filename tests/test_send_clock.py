from __future__ import annotations

import logging

import pytest

from funestra.send_clock import SENDS_A_SECOND, SendClock
from funestra.tick_failures import TickFailures

_A_BEAT = 1.0 / SENDS_A_SECOND


class _Time:
    def __init__(self, *, beats_to_run: int, a_beat_takes: float = 0.0) -> None:
        self.now = 100.0
        self.beats: list[float] = []
        self.slept: list[float] = []
        self._beats_to_run = beats_to_run
        self._a_beat_takes = a_beat_takes

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def beat(self, now: float) -> None:
        self.beats.append(now)
        self.now += self._a_beat_takes

    def stopped(self) -> bool:
        return len(self.beats) >= self._beats_to_run


def _clock(time: _Time, beat=None, logger=None) -> SendClock:
    return SendClock(beat or time.beat, TickFailures(logger or logging.getLogger("tests.send_clock"), "send"),
                     stopped=time.stopped, clock=time.clock, sleep=time.sleep)


def test_it_beats_at_once_and_then_evenly_thirty_times_a_second():
    time = _Time(beats_to_run=4)

    _clock(time).run()

    assert time.beats == pytest.approx([100.0 + beat * _A_BEAT for beat in range(4)])


def test_between_beats_it_sleeps_and_does_nothing_else():
    time = _Time(beats_to_run=3)

    _clock(time).run()

    assert time.slept == pytest.approx([_A_BEAT, _A_BEAT])


def test_time_a_beat_took_comes_out_of_the_wait_for_the_next_so_the_beats_stay_even():
    time = _Time(beats_to_run=3, a_beat_takes=0.010)

    _clock(time).run()

    assert time.beats == pytest.approx([100.0, 100.0 + _A_BEAT, 100.0 + 2 * _A_BEAT])


def test_beats_missed_while_one_ran_long_are_not_made_up_for_with_a_burst():
    time = _Time(beats_to_run=3, a_beat_takes=3 * _A_BEAT)

    _clock(time).run()

    assert time.beats == pytest.approx([100.0, 100.0 + 3 * _A_BEAT, 100.0 + 6 * _A_BEAT])
    assert time.slept == []


def test_a_beat_that_fails_is_reported_and_the_next_one_still_comes():
    time = _Time(beats_to_run=2)
    reported: list[str] = []

    class Heard(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            reported.append(record.getMessage())

    logger = logging.getLogger("tests.send_clock.failing")
    logger.addHandler(Heard())

    def beat(now: float) -> None:
        time.beat(now)
        if len(time.beats) == 1:
            raise ValueError("no position to send")

    _clock(time, beat, logger).run()

    assert len(time.beats) == 2
    assert reported == ["send failed"]


def test_told_to_stop_it_stops():
    time = _Time(beats_to_run=0)

    _clock(time).run()

    assert time.beats == []
