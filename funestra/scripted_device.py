from __future__ import annotations

from .robot_hand import FULL_INTENSITY

REWIND_MS = 50


class _Unconnected:
    def update(self, position_ms: int, script, *, speed: float = 1.0,
               max_intensity: int = FULL_INTENSITY) -> None:
        pass

    def park(self) -> None:
        pass

    def reset(self) -> None:
        pass

    def want(self, wanted: bool) -> None:
        pass

    def close(self) -> None:
        pass


class ScriptedDevice:
    def __init__(self, tcode=None, *, enabled: bool = True) -> None:
        self._tcode = _Unconnected() if tcode is None else tcode
        self._enabled = enabled
        self._tcode.want(enabled)
        self._max_intensity = FULL_INTENSITY
        self._last_position_ms = 0.0
        self._resumed_at: float | None = None

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        if enabled:
            self.take_over()
        self._enabled = enabled
        self._tcode.want(enabled)

    def take_over(self) -> None:
        self._tcode.reset()

    def start_an_item(self) -> None:
        self.take_over()
        self._last_position_ms = 0.0

    def resume_at(self, position_ms: float) -> None:
        self.take_over()
        self._resumed_at = position_ms

    def follow(self, position_ms: float, script, *, speed: float, rolled: bool = False,
               over_an_image: bool = False) -> None:
        if not rolled and position_ms + REWIND_MS < self._last_position_ms:
            self.take_over()
        self._last_position_ms = position_ms
        if self._the_playhead_has_moved_since_the_resume(position_ms, over_an_image):
            self.drive(position_ms, script, speed=speed)

    def _the_playhead_has_moved_since_the_resume(self, position_ms: float,
                                                 over_an_image: bool) -> bool:
        if self._resumed_at is None:
            return True
        if position_ms == self._resumed_at and not over_an_image:
            return False
        self._resumed_at = None
        return True

    @property
    def max_intensity(self) -> int:
        return self._max_intensity

    def set_max_intensity(self, max_intensity: int) -> None:
        self._max_intensity = max(0, min(FULL_INTENSITY, max_intensity))

    def drive(self, position_ms: float, script, *, speed: float) -> None:
        if not self._enabled:
            return
        if script is not None:
            self._tcode.update(int(position_ms), script, speed=speed, max_intensity=self._max_intensity)
        else:
            self._tcode.park()

    def close(self) -> None:
        self._tcode.close()
