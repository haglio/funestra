"""The playlist a content source hands a Funestra: one item per line.

The source -- Fun Time, or an Origenerator show it hosts -- writes this file,
tells the Funestra to RELOAD_PLAYLIST, and the Funestra reads it back.  Each line names one
item, with a TAB and its funscript after it when it has one, and a second TAB and
the places a lock punches in on after that when it has those; blank lines and
#-comments are ignored.  The same line is what PLAY_FILE carries, so a source
naming an item to jump to spells it exactly as the file does.

Written and read here, in one module, because more than one Funestra reads the
one shape the sources write: the Main Funestra drives the OSR2 from the funscript
column, and every Funestra colors its scrubber with it.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from app_support.file_channel import write_whole


class _Pair(NamedTuple):
    path: Path
    funscript: Path | None = None


class PlaylistItem(_Pair):
    """One thing a Funestra shows: its path, the script that drives the device
    while it plays, and the places in an image a lock punches in on, as
    ``(x0, y0, x1, y1)`` fractions of it.

    A pair as well as a record, on purpose: every reader in the family took
    the item as a ``(video, funscript)`` pair before it had a name, and a
    checkout that has not moved to the names yet still unpacks it -- so the
    places ride beside the pair rather than inside it.
    """

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
    """The item one line names, or None for a line naming nothing."""
    path_part, _, rest = line.partition("\t")
    funscript_part, _, points_part = rest.partition("\t")
    path_part = path_part.strip()
    funscript_part = funscript_part.strip()
    if not path_part:
        return None
    return PlaylistItem(Path(path_part), Path(funscript_part) if funscript_part else None,
                        _points_in(points_part))


def item_line(item: PlaylistItem) -> str:
    """*item* as the one line that names it, the inverse of :func:`item_from_line`."""
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
        if len(edges) == 4:
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
    """Write *items* as the file :func:`read_playlist` reads back, whole or not at all."""
    write_whole(path, "".join(f"{item_line(item)}\n" for item in items),
                attempts=round(READER_HOLD_BUDGET_S / _RETRY_SPACING_S),
                delay_s=_RETRY_SPACING_S)
