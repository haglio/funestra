from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Protocol

from app_support.json_store import locked_update, read_json
from app_support.mirrored_tree import library_roots_beside, mirrored_path

logger = logging.getLogger(__name__)

HALF_A_LOOP = 0.5

GENAU_SECTION = "genau"
FLIPPED = "flipped"
_FLIPS_READ_AHEAD_KEPT = 8


def _is_flipped(record: dict) -> bool:
    return record.get(GENAU_SECTION, {}).get(FLIPPED) is True


def _turned_over(record: dict) -> dict:
    genau = {key: value for key, value in record.get(GENAU_SECTION, {}).items() if key != FLIPPED}
    if not _is_flipped(record):
        genau[FLIPPED] = True
    rest = {key: value for key, value in record.items() if key != GENAU_SECTION}
    return {**rest, GENAU_SECTION: genau} if genau else rest


class FlipsKeptElsewhere(Protocol):
    def keeps(self, flick: Path) -> bool: ...

    def is_flipped(self, flick: Path) -> bool: ...

    def keep(self, flick: Path, flipped: bool) -> None: ...


class _KeptNowhereElse:
    @staticmethod
    def keeps(_flick: Path) -> bool:
        return False


class FlickFlip:
    def __init__(self, metadata_root: Path | None = None, *,
                 kept_elsewhere: FlipsKeptElsewhere | None = None) -> None:
        self._metadata_root = metadata_root
        self._elsewhere = kept_elsewhere or _KeptNowhereElse()
        self._flick: Path | None = None
        self.on = False
        self._read_ahead: OrderedDict[Path, bool] = OrderedDict()
        self._read_ahead_lock = threading.Lock()

    def read_ahead(self, flick: Path) -> None:
        flipped = self._recorded_as_flipped(flick)
        with self._read_ahead_lock:
            self._read_ahead[flick] = flipped
            self._read_ahead.move_to_end(flick)
            while len(self._read_ahead) > _FLIPS_READ_AHEAD_KEPT:
                self._read_ahead.popitem(last=False)

    @property
    def flips_read_ahead(self) -> int:
        return len(self._read_ahead)

    def follow(self, flick: Path | None) -> None:
        if flick == self._flick:
            return
        self._flick = flick
        if flick is None:
            self.on = False
            return
        with self._read_ahead_lock:
            read_ahead = self._read_ahead.pop(flick, None)
        self.on = self._recorded_as_flipped(flick) if read_ahead is None else read_ahead

    def applied_to(self, phase: float) -> float:
        return (phase + HALF_A_LOOP) % 1.0 if self.on else phase

    def toggle(self) -> None:
        if self._flick is None:
            return
        if self._elsewhere.keeps(self._flick):
            self.on = not self.on
            self._elsewhere.keep(self._flick, self.on)
            return
        record = self._record_of(self._flick)
        if record is None:
            logger.warning("Could not save the flip of %s: it has no metadata record",
                           self._flick.name)
            self.on = not self.on
            return
        try:
            self.on = _is_flipped(locked_update(record, _turned_over))
        except (OSError, ValueError):
            logger.warning("Could not save the flip of %s to %s", self._flick.name, record,
                           exc_info=True)
            self.on = not self.on

    def _record_of(self, flick: Path) -> Path | None:
        if self._metadata_root is None:
            return None
        return mirrored_path(flick, roots=library_roots_beside(self._metadata_root),
                             mirror_root=self._metadata_root, suffix=".json")

    def _recorded_as_flipped(self, flick: Path) -> bool:
        if self._elsewhere.keeps(flick):
            return self._elsewhere.is_flipped(flick)
        record = self._record_of(flick)
        if record is None:
            return False
        try:
            return _is_flipped(read_json(record))
        except (OSError, ValueError):
            return False
