from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Protocol

from app_support.file_channel import publish_whole
from app_support.threading_utils import start_daemon_thread

from .dashboard import ask

logger = logging.getLogger(__name__)


class OffTheLoop(Protocol):
    def publish(self, path: Path, text: str) -> bool: ...

    def ask(self, command_file: Path | None, command: str) -> None: ...

    def do[T](self, work: Callable[[], T], then: Callable[[T], None] | None = None) -> None: ...

    def deliver(self) -> None: ...

    def close(self) -> None: ...


def at_once[T](work: Callable[[], T], then: Callable[[T], None] | None = None) -> None:
    done = work()
    if then is not None:
        then(done)


class AtOnce:
    def publish(self, path: Path, text: str) -> bool:
        return publish_whole(path, text)

    def ask(self, command_file: Path | None, command: str) -> None:
        ask(command_file, command)

    def do[T](self, work: Callable[[], T], then: Callable[[T], None] | None = None) -> None:
        at_once(work, then)

    def deliver(self) -> None:
        pass

    def close(self) -> None:
        pass


class BehindTheLoop:
    def __init__(self) -> None:
        self._jobs: queue.SimpleQueue[Callable[[], None] | None] = queue.SimpleQueue()
        self._done: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._texts: dict[Path, str] = {}
        self._texts_lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def publish(self, path: Path, text: str) -> bool:
        with self._texts_lock:
            already_waiting = path in self._texts
            self._texts[path] = text
        if not already_waiting:
            self._hand_over(partial(self._publish_the_newest, path))
        return True

    def _publish_the_newest(self, path: Path) -> None:
        with self._texts_lock:
            text = self._texts.pop(path)
        publish_whole(path, text)

    def ask(self, command_file: Path | None, command: str) -> None:
        self._hand_over(partial(ask, command_file, command))

    def do[T](self, work: Callable[[], T], then: Callable[[T], None] | None = None) -> None:
        def job() -> None:
            done = work()
            if then is not None:
                self._done.put(partial(then, done))

        self._hand_over(job)

    def deliver(self) -> None:
        while True:
            try:
                hand_back = self._done.get_nowait()
            except queue.Empty:
                return
            hand_back()

    def close(self) -> None:
        if self._worker is None:
            return
        self._jobs.put(None)
        self._worker.join()
        self._worker = None

    def _hand_over(self, job: Callable[[], None]) -> None:
        if self._worker is None:
            self._worker = start_daemon_thread(target=self._work, name="funestra-off-the-loop")
        self._jobs.put(job)

    def _work(self) -> None:
        while (job := self._jobs.get()) is not None:
            try:
                job()
            except Exception:
                logger.exception("A job handed off a Funestra's loop failed")
