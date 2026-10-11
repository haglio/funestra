"""Something in a frame loop failing, said once rather than every frame.

A Funestra's loop runs at up to 120fps and calls the same work again immediately,
so a persistent fault reported every time would write thousands of identical
tracebacks a second into the log -- which both buries the first occurrence and
can fill the state directory the IPC files live in.

The first of each kind is a full traceback, because that is what a reader needs.
Every repeat after it is one debug line with no traceback, and the run of them
is counted; the count goes out when the fault gives way to another or when the
work succeeds again, which are the two moments it means something.

One log can carry more than one of these -- a Funestra's tick and a headset's
frame loop -- so each is named, and says which it is on every line.
"""
from __future__ import annotations

import logging

__all__: list[str] = []  # package-internal: no sibling reaches anything here

class TickFailures:
    def __init__(self, logger: logging.Logger, what: str = "refresh"):
        self.logger = logger
        # Named, because a log carrying two of these has to say which failed.
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
        """A turn that got through, which is when a run of failures is over."""
        self._report_the_run()
        self._kind = None
        self._repeats = 0

    def _report_the_run(self) -> None:
        if self._repeats:
            self.logger.error(
                "...and %d more %s like it: %s",
                self._repeats, self.what, self._kind[1],
            )
