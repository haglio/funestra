from __future__ import annotations

import time
from collections.abc import Callable

from .tick_failures import TickFailures

SENDS_A_SECOND = 30


class SendClock:
    def __init__(self, beat: Callable[[float], None], failures: TickFailures, *,
                 stopped: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._beat = beat
        self._failures = failures
        self._stopped = stopped
        self._clock = clock
        self._sleep = sleep
        self._every = 1.0 / SENDS_A_SECOND

    def run(self) -> None:
        due = self._clock()
        while not self._stopped():
            now = self._clock()
            if now < due:
                self._sleep(due - now)
                continue
            self._beat_once(now)
            due += self._every
            if due <= now:
                due = now + self._every

    def _beat_once(self, now: float) -> None:
        try:
            self._beat(now)
        except Exception as exc:
            self._failures.failed(exc)
            return
        self._failures.worked()
