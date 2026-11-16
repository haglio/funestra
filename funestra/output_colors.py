from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

WATCHED = ("current-vo", "current-gpu-context", "display-names", "video-target-params")


class OutputColors:

    def __init__(self) -> None:
        self._heard: dict[str, object] = {}
        self._last_line: str | None = None

    def watch(self, handle) -> None:
        for name in WATCHED:
            handle.observe_property(name, self.heard)

    def heard(self, name: str, value) -> None:
        self._heard[name] = value
        line = self._line()
        if line is not None and line != self._last_line:
            self._last_line = line
            logger.info("%s", line)

    def _line(self) -> str | None:
        target = self._heard.get("video-target-params")
        if not isinstance(target, dict):
            return None
        displays = self._heard.get("display-names") or ["?"]
        return (
            f"Video output {self._heard.get('current-vo') or '?'} on "
            f"{self._heard.get('current-gpu-context') or '?'}, display {', '.join(displays)}: "
            f"transfer {target.get('gamma', '?')}, primaries {target.get('primaries', '?')}, "
            f"peak {_peak(target)}")


def _peak(target: dict) -> str:
    relative, luma = target.get("sig-peak"), target.get("max-luma")
    said = f"{relative:.2f}" if isinstance(relative, (int, float)) else "?"
    return f"{said} ({luma:.0f} cd/m2)" if isinstance(luma, (int, float)) else said
