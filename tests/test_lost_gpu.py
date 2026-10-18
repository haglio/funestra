from __future__ import annotations

import logging
import threading

from funestra import lost_gpu
from funestra.lost_gpu import FIRST_WAIT_S, LASTED_S, LONGEST_WAIT_S, QUIET_S, LostGpu

# mpv's own line, word for word, from a Funestra whose graphics card Windows reset.
SUSPENDED = ("Failed to create SRV: The GPU device instance has been suspended. Use "
             "GetDeviceRemovedReason to determine the appropriate action. (0x887a0005)")


class Later:
    """Stands in for the timer: says how long each rebuild was set to wait, and runs it on cue."""

    def __init__(self) -> None:
        self.waits: list[float] = []
        self.cancelled = 0
        self._then = None

    def __call__(self, seconds: float, then):
        self.waits.append(seconds)
        self._then = then
        return self._cancel

    def _cancel(self) -> None:
        self.cancelled += 1

    def run(self) -> None:
        then, self._then = self._then, None
        then()


class Clock:
    def __init__(self) -> None:
        self.at = 0.0

    def __call__(self) -> float:
        return self.at


def watching(rebuild=lambda: True) -> tuple[LostGpu, Later, Clock]:
    later, clock = Later(), Clock()
    return LostGpu(rebuild=rebuild, now=clock, later=later), later, clock


def test_mpv_saying_the_gpu_is_gone_sets_one_rebuild_going_after_the_first_wait():
    lost, later, _clock = watching()

    for _ in range(3):
        lost.heard(SUSPENDED)

    assert later.waits == [FIRST_WAIT_S]


def test_the_same_news_from_the_hardware_decoder_counts_too():
    lost, later, _clock = watching()

    lost.heard("AVHWFramesContext: Could not create the texture (887a0005)")

    assert later.waits == [FIRST_WAIT_S]


def test_any_other_line_of_mpvs_sets_nothing_going():
    lost, later, _clock = watching()

    lost.heard("Failed to query swap chain's output information")

    assert later.waits == []


def test_the_new_output_is_built_once_the_wait_is_over():
    built = []
    lost, later, _clock = watching(rebuild=lambda: built.append("built") or True)
    lost.heard(SUSPENDED)

    later.run()

    assert built == ["built"]


def test_what_the_old_output_says_on_its_way_out_sets_nothing_going():
    lost, later, clock = watching()
    lost.heard(SUSPENDED)
    clock.at = FIRST_WAIT_S
    later.run()

    clock.at += QUIET_S / 2
    lost.heard(SUSPENDED)

    assert later.waits == [FIRST_WAIT_S]


def test_what_mpv_says_while_the_new_output_is_being_built_sets_nothing_going():
    def rebuild() -> bool:
        lost.heard(SUSPENDED)
        return True

    lost, later, _clock = watching(rebuild=rebuild)
    lost.heard(SUSPENDED)

    later.run()

    assert later.waits == [FIRST_WAIT_S]


def lost_again_and_again(times: int, *, apart_s: float) -> list[float]:
    lost, later, clock = watching()
    for _ in range(times):
        lost.heard(SUSPENDED)
        clock.at += later.waits[-1]
        later.run()
        clock.at += apart_s
    return later.waits


def test_a_gpu_lost_again_soon_after_its_rebuild_waits_twice_as_long_each_time():
    assert lost_again_and_again(3, apart_s=QUIET_S * 2) == [
        FIRST_WAIT_S, FIRST_WAIT_S * 2, FIRST_WAIT_S * 4]


def test_the_wait_stops_growing_at_the_longest_wait():
    assert max(lost_again_and_again(8, apart_s=QUIET_S * 2)) == LONGEST_WAIT_S


def test_an_output_that_lasted_leaves_the_next_loss_the_first_wait():
    assert lost_again_and_again(3, apart_s=LASTED_S) == [FIRST_WAIT_S] * 3


def test_a_new_output_that_never_came_up_is_built_again_after_a_longer_wait():
    lost, later, clock = watching(rebuild=lambda: False)
    lost.heard(SUSPENDED)
    clock.at = FIRST_WAIT_S

    later.run()

    assert later.waits == [FIRST_WAIT_S, FIRST_WAIT_S * 2]


def test_a_window_closing_calls_off_the_rebuild_and_builds_nothing_after():
    built = []
    lost, later, _clock = watching(rebuild=lambda: built.append("built") or True)
    lost.heard(SUSPENDED)

    lost.stop()
    later.run()
    lost.heard(SUSPENDED)

    assert (later.cancelled, built, later.waits) == (1, [], [FIRST_WAIT_S])


def test_the_log_says_what_mpv_said_and_whether_each_new_output_came_up(caplog):
    outcomes = iter([False, True])
    lost, later, _clock = watching(rebuild=lambda: next(outcomes))

    with caplog.at_level(logging.INFO, logger="funestra.lost_gpu"):
        lost.heard(SUSPENDED)
        later.run()
        later.run()

    said = [record.getMessage() for record in caplog.records]
    assert len(said) == 3
    assert SUSPENDED in said[0]
    assert "did not come up" in said[1]
    assert "came up" in said[2] and "did not" not in said[2]


def test_the_wait_runs_on_a_timer_of_its_own_and_can_be_called_off():
    ran, kept = threading.Event(), threading.Event()

    lost_gpu._after(0.01, ran.set)
    call_off = lost_gpu._after(0.2, kept.set)
    call_off()

    assert ran.wait(5.0)
    assert not kept.wait(0.4)
