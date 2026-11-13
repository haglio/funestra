from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .up_next import put_up_next


def _listed(videos: Sequence[Path]) -> list[Path]:
    if not videos:
        raise ValueError("playlist must not be empty")
    return list(videos)


class Lineup:
    def __init__(self, videos: Sequence[Path]) -> None:
        self._videos = _listed(videos)
        self._index = 0
        self._versions: dict[Path, Path] = {}
        self._frame: Path | None = None
        self._an_image_was_put_up = False

    def __len__(self) -> int:
        return len(self._videos)

    @property
    def videos(self) -> list[Path]:
        return list(self._videos)

    @property
    def index(self) -> int:
        return self._index

    @property
    def current(self) -> Path:
        return self._videos[self._index]

    @property
    def showing(self) -> Path:
        return self._file_at(self._index)

    @property
    def on_screen(self) -> Path:
        return self.showing if self._frame is None else self._frame

    @property
    def an_image_was_put_up(self) -> bool:
        return self._an_image_was_put_up

    def _file_at(self, index: int) -> Path:
        video = self._videos[index % len(self._videos)]
        return self._versions.get(video, video)

    def place_of(self, video: Path) -> int | None:
        return self._videos.index(video) if video in self._videos else None

    def stand_at(self, index: int) -> None:
        self._index = index % len(self._videos)
        self._frame = None
        self._an_image_was_put_up = False

    def put_up(self, frame: Path) -> None:
        self._frame = frame
        self._an_image_was_put_up = True

    def take_down_the_frame(self) -> bool:
        was_up, self._frame = self._frame is not None, None
        return was_up

    @property
    def rolls_onto_itself(self) -> bool:
        return len(self._videos) == 1

    @property
    def what_the_roll_puts_up(self) -> Path:
        return self.on_screen if self.rolls_onto_itself else self._file_at(self._index + 1)

    def roll(self) -> None:
        if not self.rolls_onto_itself:
            self._frame = None
            self._an_image_was_put_up = False
        self._index = (self._index + 1) % len(self._videos)

    def step_version(self, versions: Sequence[Path], delta: int) -> bool:
        showing = self.showing
        if len(versions) <= 1 or showing not in versions:
            return False
        target = versions[(versions.index(showing) + delta) % len(versions)]
        if target == self.current:
            self._versions.pop(self.current, None)
        else:
            self._versions[self.current] = target
        return True

    def forget_versions(self) -> None:
        self._versions = {}

    def put_next(self, video: Path) -> None:
        self._index = put_up_next(self._videos, self._index, video, self.place_of(video))

    def discard(self) -> bool:
        if len(self._videos) <= 1:
            return False
        self._versions.pop(self._videos.pop(self._index), None)
        return True

    def start_over_with(self, videos: Sequence[Path]) -> None:
        self._videos = _listed(videos)
        self._versions = {}

    def take(self, videos: Sequence[Path]) -> bool:
        current = self.current
        chosen = self._versions.get(current)
        self._videos = _listed(videos)
        self._versions = {} if chosen is None else {current: chosen}
        if current in self._videos:
            self._index = self._videos.index(current)
            return True
        self._versions = {}
        if self._frame in self._videos:
            self._index = self._videos.index(self._frame)
            self._frame = None
            return True
        return False
