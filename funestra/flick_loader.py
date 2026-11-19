from __future__ import annotations

import time
from pathlib import Path
from typing import Any, NamedTuple


class FlickLoadParts(NamedTuple):
    flick_store: Any
    load_state: Any
    prefetch_state: Any
    current_flick_path_getter: Any
    decode_flick: Any
    start_thread: Any
    logger: Any
    on_active_flick_loaded: Any


class FlickLoadController:
    def __init__(self, parts: FlickLoadParts):
        (self.flick_store, self.load_state, self.prefetch_state,
         self.current_flick_path_getter, self.decode_flick, self.start_thread,
         self.logger, self.on_active_flick_loaded) = parts

    @property
    def is_busy(self) -> bool:
        return self.load_state.loading or self.prefetch_state.loading

    def frames_ready(self, path: Path) -> bool:
        if path in self.flick_store.flick_cache:
            return True
        if self.flick_store.adopt_decoded_frames(
                path, protected_paths=self._flick_on_screen()):
            self.logger.info("Adopted the prefetched %s", path.name)
            return True
        coming_in = (self.load_state.frames_coming_in_for(path)
                     or self.prefetch_state.frames_coming_in_for(path))
        if coming_in:
            self.logger.info("Showing %s while the rest of it is decoded", path.name)
            self.flick_store.cache_flick(path, coming_in, protected_paths=self._flick_on_screen())
            return True
        return False

    def request_flick_load(self, path: Path) -> None:
        if self.frames_ready(path) or self._already_decoding(path):
            return

        self.logger.info("Loading %s (no prefetch available)", path.name)
        request_id = self.load_state.begin(path)
        self.start_thread(
            target=self._loader_thread_fn,
            args=(path, request_id),
            name="genau-loader",
        )

    def request_prefetch(self, path: Path) -> None:
        if self.flick_store.holds(path) or self.is_busy:
            return

        self.logger.info("Prefetching %s", path.name)
        request_id = self.prefetch_state.begin(path)
        self.start_thread(
            target=self._prefetch_thread_fn,
            args=(path, request_id),
            name="genau-prefetch",
        )

    def adopt_loaded_flick_if_ready(self) -> None:
        self._put_up_the_flick_on_screen_at_its_first_frame()
        result = self.load_state.take_completed_result()
        if result is None:
            return

        path, frames, err = result
        if err or path in self.flick_store.flick_cache:
            return

        self._adopt(path, frames)

    def _put_up_the_flick_on_screen_at_its_first_frame(self) -> None:
        path = self.current_flick_path_getter()
        if path is None or path in self.flick_store.flick_cache:
            return
        if self.frames_ready(path):
            self.on_active_flick_loaded()

    def adopt_prefetch_if_ready(self) -> None:
        result = self.prefetch_state.take_completed_result()
        if result is None:
            return

        path, frames, err = result
        if err:
            return

        self.logger.info("Prefetch ready: %s (%d frames)", path.name, len(frames) if frames else 0)
        if path in self.flick_store.flick_cache:
            return
        if self.current_flick_path_getter() == path:
            self._adopt(path, frames)
            return
        self.flick_store.cache_decoded_frames(
            path, frames, protected_paths=self._flick_on_screen())

    def _adopt(self, path: Path, frames: list) -> None:
        self.flick_store.cache_flick(
            path, frames, protected_paths=self._flick_on_screen())
        if self.current_flick_path_getter() == path:
            self.on_active_flick_loaded()

    def _already_decoding(self, path: Path) -> bool:
        return (self.load_state.is_decoding(path)
                or self.prefetch_state.is_decoding(path))

    def _flick_on_screen(self) -> set[Path]:
        return {self.current_flick_path_getter()}

    def _decode_thread_fn(self, path: Path, request_id: int, state, log_error) -> None:
        began_for_the_log_line_alone = time.monotonic()
        try:
            frames: list = []
            for frame in self.decode_flick(path):
                frames.append(frame)
                if len(frames) == 1:
                    state.record_first_frame(frames, request_id)
            elapsed = time.monotonic() - began_for_the_log_line_alone
            self.logger.info("Decoded %s: %d frames in %.2fs", path.name, len(frames), elapsed)
            state.record_success(path, frames, request_id)
        except Exception as exc:
            log_error(path, exc)
            state.record_error(path, str(exc), request_id)

    def _loader_thread_fn(self, path: Path, request_id: int) -> None:
        self._decode_thread_fn(
            path, request_id, self.load_state,
            lambda p, e: self.logger.exception("Failed to decode %s", p),
        )

    def _prefetch_thread_fn(self, path: Path, request_id: int) -> None:
        self._decode_thread_fn(
            path, request_id, self.prefetch_state,
            lambda p, e: self.logger.warning("Prefetch decode failed for %s: %s", p, e),
        )
