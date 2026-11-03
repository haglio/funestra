from __future__ import annotations

import logging


class TickFailures:
    def __init__(self, logger: logging.Logger, what: str = "refresh"):
        self.logger = logger
        self.what = what
        self._kind: tuple[str, str] | None = None
        self._repeats = 0

    def failed(self, exc: BaseException) -> None:
        kind = (type(exc).__name__, str(exc))
        if kind == self._kind:
            self._repeats += 1
            self.logger.debug("%s failed again: %s", self.what, exc)
            return
        self._report_the_run()
        self._kind = kind
        self._repeats = 0
        self.logger.error("%s failed", self.what, exc_info=exc)

    def worked(self) -> None:
        self._report_the_run()
        self._kind = None
        self._repeats = 0

    def _report_the_run(self) -> None:
        if self._repeats:
            self.logger.error(
                "...and %d more %s like it: %s",
                self._repeats, self.what, self._kind[1],
            )
