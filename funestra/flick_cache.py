"""Decoded flicks kept in memory, and the decode requests that fill the cache.

Two caches, both bounded and both least-recently-used: the flicks that have been
taken up on screen, and frames decoded ahead of being taken up.  The flick on
screen is protected from trimming, whatever its age -- the picture must not
vanish under the viewer to make room for its neighbor.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .renamed import answers_to_old_names

__all__ = [
    "DecodeRequestState",
    "FlickCacheStore",
]

def trim_path_lru_cache[T](
    cache: OrderedDict[Path, T],
    *,
    limit: int,
    protected_paths: set[Path] | None = None,
) -> None:
    limit = max(1, int(limit))
    protected = {path for path in (protected_paths or set()) if path is not None}

    skipped = 0
    while len(cache) > limit and cache:
        oldest_key = next(iter(cache))
        if oldest_key in protected:
            cache.move_to_end(oldest_key)
            skipped += 1
            if skipped >= len(cache):
                break
            continue
        cache.popitem(last=False)
        skipped = 0


@answers_to_old_names({"loaded_clip_path": "loaded_flick_path"})
@dataclass
class DecodeRequestState:
    """One decode in flight, and the result it left for the loop to take.

    A result carrying a request id older than the latest request is stale --
    the loop asked for something else since -- and is dropped when taken, with
    the state left loading for the request that superseded it.
    """

    request_id: int = 0
    loading: bool = False
    decoding_path: Path | None = None
    loaded_flick_path: Path | None = None
    loaded_frames: list | None = None
    load_error: str | None = None
    request_id_done: int | None = None

    def begin(self, path: Path) -> int:
        self.request_id += 1
        self.loading = True
        self.decoding_path = path
        self.loaded_flick_path = None
        self.loaded_frames = None
        self.load_error = None
        self.request_id_done = None
        return self.request_id

    def is_decoding(self, path: Path) -> bool:
        """Whether the decode in flight is this flick's."""
        return self.loading and self.decoding_path == path

    def record_success(self, path: Path, frames: list, request_id: int) -> None:
        self.loaded_flick_path = path
        self.loaded_frames = frames
        self.load_error = None
        self.request_id_done = request_id

    def record_error(self, path: Path, error: str, request_id: int) -> None:
        self.loaded_flick_path = path
        self.loaded_frames = None
        self.load_error = error
        self.request_id_done = request_id

    def take_completed_result(self) -> tuple[Path | None, list | None, str | None] | None:
        if self.request_id_done is None:
            return None

        if self.request_id_done != self.request_id:
            self.request_id_done = None
            self.loaded_flick_path = None
            self.loaded_frames = None
            self.load_error = None
            return None

        path = self.loaded_flick_path
        frames = self.loaded_frames
        error = self.load_error

        self.request_id_done = None
        self.loading = False
        self.decoding_path = None
        return path, frames, error


@answers_to_old_names({
    "cache_clip": "cache_flick",
    "clip_cache": "flick_cache",
    "clip_entry_for": "flick_entry_for",
})
class FlickCacheStore:
    def __init__(self, *, limit: int):
        self.limit = limit
        self.flick_cache: OrderedDict[Path, dict] = OrderedDict()
        self.decoded_frame_cache: OrderedDict[Path, list] = OrderedDict()

    def trim_cache(self, *, protected_paths: set[Path] | None = None) -> None:
        trim_path_lru_cache(
            self.flick_cache,
            limit=self.limit,
            protected_paths=protected_paths,
        )

    def trim_decoded_cache(self, *, protected_paths: set[Path] | None = None) -> None:
        trim_path_lru_cache(
            self.decoded_frame_cache,
            limit=self.limit,
            protected_paths=protected_paths,
        )

    def holds(self, path: Path) -> bool:
        """Whether this flick's frames are in hand at all -- up, or decoded ahead."""
        return path in self.flick_cache or path in self.decoded_frame_cache

    def flick_entry_for(self, path: Path) -> dict:
        entry = self.flick_cache[path]
        self.flick_cache.move_to_end(path)
        return entry

    def cache_flick(self, path: Path, frames: list, *, protected_paths: set[Path] | None = None) -> None:
        """Keep *frames* as the flick at *path*, ready to go on screen."""
        self.flick_cache[path] = {
            "frames": frames,
        }
        self.flick_cache.move_to_end(path)
        self.trim_cache(protected_paths=protected_paths)

    def cache_decoded_frames(self, path: Path, frames: list, *, protected_paths: set[Path] | None = None) -> None:
        self.decoded_frame_cache[path] = frames
        self.decoded_frame_cache.move_to_end(path)
        self.trim_decoded_cache(protected_paths=protected_paths)

    def adopt_decoded_frames(self, path: Path, *, protected_paths: set[Path] | None = None) -> bool:
        """Move *path*'s decode-ahead frames into the flicks-on-screen cache.

        Moved rather than copied: decode-ahead room is for flicks that are not up
        yet, and a flick left on both piles holds one of the two slots against
        its own neighbors for as long as it is showing.
        """
        frames = self.decoded_frame_cache.pop(path, None)
        if frames is None:
            return False

        self.cache_flick(path, frames, protected_paths=protected_paths)
        return True
