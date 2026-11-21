from __future__ import annotations

import subprocess
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from .flick_decode import read_frames_per_second

UNREAD_FRAMES_PER_SECOND = 30.0
_RATES_READ_AHEAD_KEPT = 8


class FlickFrameRates:
    def __init__(self, *, read: Callable[[Path], float] = read_frames_per_second) -> None:
        self._read = read
        self._rates: OrderedDict[Path, float] = OrderedDict()
        self._lock = threading.Lock()

    def read_ahead(self, flick: Path) -> None:
        try:
            rate = self._read(flick)
        except (OSError, ValueError, ZeroDivisionError, subprocess.CalledProcessError):
            return
        if rate <= 0:
            return
        with self._lock:
            self._rates[flick] = rate
            self._rates.move_to_end(flick)
            while len(self._rates) > _RATES_READ_AHEAD_KEPT:
                self._rates.popitem(last=False)

    def of(self, flick: Path | None) -> float:
        with self._lock:
            return self._rates.get(flick, UNREAD_FRAMES_PER_SECOND)
