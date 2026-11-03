from __future__ import annotations

import pytest

from funestra.flick_advance import (
    DEFAULT_INTERVAL_S,
    MAX_INTERVAL_S,
    MIN_INTERVAL_S,
    FlickAdvanceState,
    adjust_interval,
    set_elapsed,
    set_interval,
    tick_flick_advance,
)


def _run(state, *, playing=True, seconds=30.0, step=0.1, start=0.0, on_screen="flick"):
    calls: list[int] = []
    tick_flick_advance(
        state, start, playing=playing, on_screen_flick=on_screen, step_flick=calls.append,
    )
    for i in range(int(seconds / step)):
        tick_flick_advance(
            state, start + step * (i + 1),
            playing=playing, on_screen_flick=on_screen, step_flick=calls.append,
        )
    return calls


def _series(state, start, stop, on_screen, *, playing=True, step=0.1):
    fires: list[float] = []
    n = int(round((stop - start) / step))
    for i in range(n + 1):
        now = round(start + step * i, 3)
        tick_flick_advance(
            state, now, playing=playing, on_screen_flick=on_screen,
            step_flick=lambda _delta, _now=now: fires.append(_now),
        )
    return fires


class TestTickFlickAdvance:
    def test_a_new_state_holds_its_flick(self):
        assert FlickAdvanceState().locked is True
        assert _run(FlickAdvanceState(), seconds=60.0) == []

    def test_unlocked_it_advances_after_the_interval(self):
        state = FlickAdvanceState(locked=False)
        assert _run(state, seconds=DEFAULT_INTERVAL_S + 3.0) == [1]

    def test_holds_the_flick_while_the_room_is_paused(self):
        assert _run(FlickAdvanceState(locked=False), playing=False, seconds=60.0) == []

    def test_a_pause_banks_no_time_toward_the_next_switch(self):
        state = FlickAdvanceState(locked=False, interval=10)
        assert _run(state, seconds=4.0) == []
        assert _run(state, playing=False, seconds=600.0, start=4.0) == []
        assert _run(state, seconds=5.0, start=604.0) == []
        assert _run(state, seconds=2.0, start=609.0) == [1]

    def test_locking_mid_interval_holds_the_flick_while_its_count_goes_round(self):
        state = FlickAdvanceState(locked=False, interval=5)
        assert _run(state, seconds=3.0) == []
        state.locked = True
        assert _run(state, seconds=60.0, start=3.0) == []
        assert 0.0 < state.elapsed < 5.0


class TestAdvanceMeasuresTheFlickOnScreen:
    def test_a_never_arriving_load_advances_only_once(self):
        state = FlickAdvanceState(locked=False, interval=3)
        fires = _series(state, 0.0, 30.0, "A")
        assert len(fires) == 1

    def test_the_interval_restarts_when_the_new_flick_arrives(self):
        state = FlickAdvanceState(locked=False, interval=3)
        fires = _series(state, 0.0, 5.0, "A")
        fires += _series(state, 5.1, 12.0, "B")
        assert len(fires) == 2
        assert 2.9 <= fires[0] <= 3.2
        assert 8.0 <= fires[1] <= 8.4

    def test_counting_starts_only_once_a_flick_is_on_screen(self):
        state = FlickAdvanceState(locked=False, interval=3)
        fires = _series(state, 0.0, 4.0, None)
        fires += _series(state, 4.1, 9.0, "A")
        assert len(fires) == 1
        assert 6.9 <= fires[0] <= 7.4


class TestTheLock:
    def test_the_count_carries_on_through_a_lock_and_an_unlock(self):
        state = FlickAdvanceState(locked=False, interval=10)
        assert _run(state, seconds=4.0) == []
        state.locked = True
        assert _run(state, seconds=3.0, start=4.0) == []
        state.locked = False
        assert _run(state, seconds=2.0, start=7.0) == []
        assert _run(state, seconds=1.5, start=9.0) == [1]


class TestTheInterval:
    def test_it_opens_on_the_default(self):
        assert FlickAdvanceState().interval == DEFAULT_INTERVAL_S

    def test_it_is_clamped_to_the_usable_range(self):
        state = FlickAdvanceState()
        set_interval(state, 0)
        assert state.interval == MIN_INTERVAL_S
        set_interval(state, 9999)
        assert state.interval == MAX_INTERVAL_S

    def test_the_arrows_stop_at_the_ends_rather_than_wrapping(self):
        state = FlickAdvanceState(interval=MIN_INTERVAL_S)
        adjust_interval(state, -1)
        assert state.interval == MIN_INTERVAL_S

        state = FlickAdvanceState(interval=MAX_INTERVAL_S)
        adjust_interval(state, 1)
        assert state.interval == MAX_INTERVAL_S


class TestHowLongTheFlickHasBeenUp:
    def test_it_counts_the_seconds_since_the_flick_came_on_screen(self):
        state = FlickAdvanceState(locked=False, interval=10)
        _run(state, seconds=4.0)

        assert state.elapsed == pytest.approx(4.0, abs=0.11)

    def test_a_held_flicks_count_goes_round_and_round(self):
        state = FlickAdvanceState(locked=True, interval=10)
        _run(state, seconds=4.0)
        assert state.elapsed == pytest.approx(4.0, abs=0.11)

        assert _run(state, seconds=7.0, start=4.0) == []

        assert state.elapsed == pytest.approx(1.0, abs=0.11)

    def test_a_held_flicks_count_stops_while_the_room_is_paused(self):
        state = FlickAdvanceState(locked=True, interval=10)
        _run(state, seconds=4.0)

        _run(state, playing=False, seconds=30.0, start=4.0)

        assert state.elapsed == pytest.approx(4.0, abs=0.11)


class TestAPressAlongTheTrack:
    def test_it_puts_the_flick_that_far_through_its_turn(self):
        state = FlickAdvanceState(locked=False, interval=10)
        _run(state, seconds=2.0)

        set_elapsed(state, 7.0)

        assert state.elapsed == 7.0
        assert _run(state, seconds=2.8, start=2.0) == []
        assert _run(state, seconds=0.4, start=4.8) == [1]

    def test_a_held_flicks_count_can_be_put_along_its_track_too(self):
        state = FlickAdvanceState(locked=True, interval=10)
        _run(state, seconds=2.0)

        set_elapsed(state, 7.0)

        assert state.elapsed == 7.0
        assert _run(state, seconds=4.0, start=2.0) == []
        assert state.elapsed == pytest.approx(1.0, abs=0.11)

    def test_once_the_switch_is_asked_for_the_track_stays_full(self):
        state = FlickAdvanceState(locked=False, interval=3)
        assert len(_series(state, 0.0, 4.0, "A")) == 1

        set_elapsed(state, 1.0)

        assert state.elapsed >= 3.0

    def test_it_moves_twenty_times_a_second_rather_than_every_tick(self):
        state = FlickAdvanceState(locked=False, interval=10)

        set_elapsed(state, 4.03)

        assert state.elapsed == 4.05
