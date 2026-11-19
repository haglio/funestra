from __future__ import annotations

import logging

import pytest

from funestra.frame_record import QUIET_S, SUMMARY_EVERY_S, FrameRecord


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def wind_ms(self, ms: float) -> None:
        self.now += ms / 1000.0


def _pass(record: FrameRecord, clock: Clock, **steps_ms: float) -> None:
    record.begin()
    for step, ms in steps_ms.items():
        clock.wind_ms(ms)
        record.lap(step)
    record.end()


@pytest.fixture
def lines(caplog):
    caplog.set_level(logging.INFO, logger="funestra.frame_record")
    return lambda: [r.getMessage() for r in caplog.records if r.name == "funestra.frame_record"]


def test_a_pass_inside_its_budget_writes_nothing(lines):
    clock = Clock()
    record = FrameRecord(16.7, clock=clock)

    for _ in range(5):
        _pass(record, clock, paint=4.0, advance=2.0)

    assert lines() == []


def test_a_late_pass_is_written_down_with_its_time_and_its_longest_step(lines):
    clock = Clock()
    record = FrameRecord(16.7, clock=clock)

    _pass(record, clock, advance=3.0, paint=30.0, radio=1.0)

    assert lines() == ["Late pass: 34.0 ms of a 16.7 ms budget, longest step paint (30.0 ms); "
                       "1 late pass(es) since the last line"]


def test_late_passes_inside_a_second_of_the_last_line_are_counted_into_the_next(lines):
    clock = Clock()
    record = FrameRecord(16.7, clock=clock)

    _pass(record, clock, paint=20.0)
    for _ in range(3):
        _pass(record, clock, advance=25.0)
    clock.wind_ms(QUIET_S * 1000.0)
    _pass(record, clock, advance=25.0)

    assert lines() == [
        "Late pass: 20.0 ms of a 16.7 ms budget, longest step paint (20.0 ms); "
        "1 late pass(es) since the last line",
        "Late pass: 25.0 ms of a 16.7 ms budget, longest step advance (25.0 ms); "
        "4 late pass(es) since the last line"]


def test_a_summary_line_counts_the_passes_the_late_ones_and_the_worst(lines):
    clock = Clock()
    record = FrameRecord(16.7, clock=clock)
    passes = 0

    while not any(line.startswith("Frame loop") for line in lines()):
        _pass(record, clock, paint=40.0 if passes == 7 else 10.0)
        passes += 1

    assert lines()[-1] == (f"Frame loop over {SUMMARY_EVERY_S:.0f} s: {passes} passes, 1 late, "
                           "worst 40.0 ms (paint)")


def test_mpvs_dropped_and_delayed_frames_are_written_down_when_they_rise(lines):
    clock = Clock()
    counts = [(0, 0, 0)]
    record = FrameRecord(16.7, clock=clock, mpv_counts=lambda: counts[0])

    _pass(record, clock, paint=5.0)
    counts[0] = (3, 1, 2)
    clock.wind_ms(QUIET_S * 1000.0)
    _pass(record, clock, paint=5.0)
    clock.wind_ms(QUIET_S * 1000.0)
    _pass(record, clock, paint=5.0)

    assert lines() == ["mpv's frame counters rose: 3 dropped by the video output, "
                       "1 dropped by the decoder, 2 delayed"]


def test_mpvs_counters_are_asked_at_most_once_a_second(lines):
    clock = Clock()
    asked = []
    record = FrameRecord(16.7, clock=clock,
                         mpv_counts=lambda: asked.append(1) or (0, 0, 0))

    for _ in range(50):
        _pass(record, clock, paint=5.0)

    assert len(asked) == 1
