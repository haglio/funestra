from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from app_support.file_channel import write_whole


class _Pair(NamedTuple):
    path: Path
    funscript: Path | None = None


class PlaylistItem(_Pair):
    points_of_interest: tuple = ()

    def __new__(cls, path: Path, funscript: Path | None = None, points_of_interest=()):
        item = super().__new__(cls, path, funscript)
        item.points_of_interest = tuple(tuple(box) for box in points_of_interest)
        return item

    def __eq__(self, other: object) -> bool:
        same_pair = tuple.__eq__(self, other)
        if isinstance(other, PlaylistItem) and same_pair is True:
            return self.points_of_interest == other.points_of_interest
        return same_pair

    def __ne__(self, other: object) -> bool:
        same = self.__eq__(other)
        return same if same is NotImplemented else not same

    __hash__ = _Pair.__hash__

    def __repr__(self) -> str:
        pair = super().__repr__()
        if not self.points_of_interest:
            return pair
        return f"{pair[:-1]}, points_of_interest={self.points_of_interest!r})"


def item_from_line(line: str) -> PlaylistItem | None:
    path_part, _, rest = line.partition("\t")
    funscript_part, _, points_part = rest.partition("\t")
    path_part = path_part.strip()
    funscript_part = funscript_part.strip()
    if not path_part:
        return None
    return PlaylistItem(Path(path_part), Path(funscript_part) if funscript_part else None,
                        _points_in(points_part))


def item_line(item: PlaylistItem) -> str:
    columns = [str(item.path), str(item.funscript or "")]
    if item.points_of_interest:
        columns.append(";".join(",".join(f"{round(edge, 4):g}" for edge in box)
                                for box in item.points_of_interest))
    return "\t".join(columns).rstrip("\t")


def _points_in(column: str) -> tuple:
    boxes = []
    for box in column.split(";"):
        try:
            edges = tuple(float(edge) for edge in box.split(","))
        except ValueError:
            continue
        match edges:
            case (_, _, _, _):
                boxes.append(edges)
    return tuple(boxes)


def read_playlist(path: Path) -> list[PlaylistItem]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    items: list[PlaylistItem] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        item = item_from_line(line)
        if item is not None:
            items.append(item)
    return items


READER_HOLD_BUDGET_S = 1.0
_RETRY_SPACING_S = 0.005


def write_playlist(path: Path, items: Iterable[PlaylistItem]) -> None:
    write_whole(path, "".join(f"{item_line(item)}\n" for item in items),
                attempts=round(READER_HOLD_BUDGET_S / _RETRY_SPACING_S),
                delay_s=_RETRY_SPACING_S)
