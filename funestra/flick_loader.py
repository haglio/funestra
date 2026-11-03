from __future__ import annotations

import time
from pathlib import Path


class FlickLoadController:
    def __init__(
        self,
        *,
        flick_store,
        load_state,
        prefetch_state,
        current_flick_path_getter,
        decode_flick,
        start_thread,
        logger,
        on_active_flick_loaded,
    ):
        self.flick_store = flick_store
        self.load_state = load_state
        self.prefetch_state = prefetch_state
        self.current_flick_path_getter = current_flick_path_getter
        self.decode_flick = decode_flick
        self.start_thread = start_thread
        self.logger = logger
        self.on_active_flick_loaded = on_active_flick_loaded

    @property
    def is_busy(self) -> bool:
        return self.load_state.loading or self.prefetch_state.loading

    def frames_ready(self, path: Path) -> bool:
        if path in self.flick_store.flick_cache:
            return True
        if self.flick_store.adopt_decoded_frames(
                path, protected_paths=self._flick_on_screen()):
            self.logger.info("Adopted prefetched flick %s", path.name)
            return True
        return False

    def request_flick_load(self, path: Path) -> None:
        if self.frames_ready(path) or self._already_decoding(path):
            return

        self.logger.info("Loading flick %s (no prefetch available)", path.name)
        request_id = self.load_state.begin(path)
        self.start_thread(
            target=self._loader_thread_fn,
            args=(path, request_id),
            name="genau-loader",
        )

    def request_prefetch(self, path: Path) -> None:
        if self.flick_store.holds(path) or self.is_busy:
            return

        self.logger.info("Prefetching flick %s", path.name)
        request_id = self.prefetch_state.begin(path)
        self.start_thread(
            target=self._prefetch_thread_fn,
            args=(path, request_id),
            name="genau-prefetch",
        )

    def adopt_loaded_flick_if_ready(self) -> None:
        result = self.load_state.take_completed_result()
        if result is None:
            return

        path, frames, err = result
        if err:
            return

        self._adopt(path, frames)

    def adopt_prefetch_if_ready(self) -> None:
        result = self.prefetch_state.take_completed_result()
        if result is None:
            return

        path, frames, err = result
        if err:
            return

        self.logger.info("Prefetch ready: %s (%d frames)", path.name, len(frames) if frames else 0)
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
        t0 = time.monotonic()
        try:
            frames = self.decode_flick(path)
            elapsed = time.monotonic() - t0
            self.logger.info("Decoded %s: %d frames in %.2fs", path.name, len(frames), elapsed)
            state.record_success(path, frames, request_id)
        except Exception as exc:
            log_error(path, exc)
            state.record_error(path, str(exc), request_id)

    def _loader_thread_fn(self, path: Path, request_id: int) -> None:
        self._decode_thread_fn(
            path, request_id, self.load_state,
            lambda p, e: self.logger.exception("Failed to decode flick %s", p),
        )

    def _prefetch_thread_fn(self, path: Path, request_id: int) -> None:
        self._decode_thread_fn(
            path, request_id, self.prefetch_state,
            lambda p, e: self.logger.warning("Prefetch decode failed for %s: %s", p, e),
        )
