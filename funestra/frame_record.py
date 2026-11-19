from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import NamedTuple

logger = logging.getLogger(__name__)

DESKTOP_FRAME_MS = 1000.0 / 60.0
QUIET_S = 1.0
SUMMARY_EVERY_S = 60.0

MpvCounts = tuple[int, int, int]
NO_COUNTS: MpvCounts = (0, 0, 0)


class _Pass(NamedTuple):
    took: float = 0.0
    step: str = ""
    step_took: float = 0.0
    steps: tuple[tuple[str, float], ...] = ()
    uploaded_bytes: int = 0


class FrameRecord:
    def __init__(self, frame_ms: float = DESKTOP_FRAME_MS, *, every_step: bool = False,
                 mpv_counts: Callable[[], MpvCounts] = lambda: NO_COUNTS,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self._budget_s = frame_ms / 1000.0
        self._every_step = every_step
        self._laps: list[tuple[str, float]] = []
        self._mpv_counts = mpv_counts
        self._clock = clock
        self._began = self._lapped_at = 0.0
        self._step, self._step_took = "", 0.0
        now = clock()
        self._looked_at = now - QUIET_S
        self._summed_at = now
        self._unsaid_late = 0
        self._worst_unsaid = _Pass()
        self._passes = self._late = 0
        self._worst = _Pass()
        self._counts_said = NO_COUNTS

    def begin(self) -> None:
        self._began = self._lapped_at = self._clock()
        self._step, self._step_took = "", 0.0
        self._laps.clear()

    def lap(self, step: str) -> None:
        now = self._clock()
        took = now - self._lapped_at
        self._lapped_at = now
        if self._every_step:
            self._laps.append((step, took))
        if took > self._step_took:
            self._step, self._step_took = step, took

    def end(self, *, uploaded_bytes: int = 0) -> None:
        this = _Pass(self._lapped_at - self._began, self._step, self._step_took,
                     tuple(self._laps), uploaded_bytes)
        self._passes += 1
        if this.took > self._worst.took:
            self._worst = this
        if this.took > self._budget_s:
            self._late += 1
            self._unsaid_late += 1
            if this.took > self._worst_unsaid.took:
                self._worst_unsaid = this
        if self._lapped_at - self._looked_at >= QUIET_S:
            self._looked_at = self._lapped_at
            self._say()
        if self._lapped_at - self._summed_at >= SUMMARY_EVERY_S:
            self._sum_up()

    def _say(self) -> None:
        if self._unsaid_late:
            worst = self._worst_unsaid
            logger.info(
                "Late pass: %.1f ms of a %.1f ms budget, longest step %s (%.1f ms); "
                "%d late pass(es) since the last line%s",
                worst.took * 1000.0, self._budget_s * 1000.0, worst.step,
                worst.step_took * 1000.0, self._unsaid_late,
                _each_step(worst) if self._every_step else "")
            self._unsaid_late = 0
            self._worst_unsaid = _Pass()
        counts = self._mpv_counts()
        risen = [now - was for now, was in zip(counts, self._counts_said, strict=True)]
        self._counts_said = counts
        if any(risen):
            logger.info("mpv's frame counters rose: %d dropped by the video output, "
                        "%d dropped by the decoder, %d delayed", *risen)

    def _sum_up(self) -> None:
        logger.info("Frame loop over %.0f s: %d passes, %d late, worst %.1f ms (%s)",
                    self._lapped_at - self._summed_at, self._passes, self._late,
                    self._worst.took * 1000.0, self._worst.step or "no step")
        self._summed_at = self._lapped_at
        self._passes = self._late = 0
        self._worst = _Pass()


def _each_step(late: _Pass) -> str:
    steps = ", ".join(f"{step} {took * 1000.0:.1f}" for step, took in late.steps)
    return f"; its steps {steps} ms, {late.uploaded_bytes / 1e6:.1f} MB uploaded"
