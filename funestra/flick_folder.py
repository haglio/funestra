"""The flicks folder, its 2D and VR folders, and the pile beside it a condemned
flick is moved to, laid out the same way.

Condemning does the least it can — one file move.  A flick's other traces (its
metadata record, the Genaumacher session it was cut from) stay where they are, and
the filename carries which flick it was.
"""
from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path

from app_support.flick_folder import flat_flicks_in, vr_flicks_in, weird_dir_for_flicks_folder

__all__ = [
    "SUPPORTED_VIDEO_EXTS",
    "flat_flicks_in",
    "move_flick_to_weird",
    "scan_flicks",
    "vr_flicks_in",
    "weird_dir_for_flicks_folder",
    "weird_folder_for",
]

SUPPORTED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def _modified_at(path: Path) -> float:
    """*path*'s modification time; one we cannot stat sorts oldest."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def scan_flicks(
    folders: Path | Iterable[Path], *, shuffle_on_load: bool = True, recent: bool = False,
    shuffle=random.shuffle,
) -> list[Path]:
    """Every flick under *folders* -- one folder, or several browsed as one
    sequence -- in the browse order asked for.

    *recent* is Latest — newest-first across every folder, so the flicks that
    have just arrived head the sequence — and it outranks *shuffle_on_load*: an
    order named outright is not then randomized away.  Without it the folders'
    own order stands, one after another, shuffled together when the config says
    to.  A folder with nothing in it contributes nothing; only no flicks anywhere
    is an error.

    *shuffle* is a dependency rather than a module global so the shuffled order
    can be asked about at all: the reorder path is otherwise only testable by
    running it until a different order comes out.
    """
    folders = (Path(folders),) if isinstance(folders, (str, Path)) else tuple(Path(f) for f in folders)
    files = [path for folder in folders for path in sorted(folder.rglob("*"))
             if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTS]
    if not files:
        raise RuntimeError(f"No video flicks found in: {', '.join(str(f) for f in folders)}")
    if recent:
        return sorted(files, key=_modified_at, reverse=True)
    if shuffle_on_load:
        shuffle(files)
    return files


def cache_dir_for_flicks_folder(folder: Path) -> Path:
    return folder.parent / "frames"


def weird_folder_for(flick: Path, flicks_folder: Path) -> Path:
    weird = weird_dir_for_flicks_folder(flicks_folder)
    try:
        return weird / flick.parent.relative_to(flicks_folder)
    except ValueError:
        return weird


def move_flick_to_weird(flick_path: Path, weird_dir: Path) -> Path | None:
    """Move *flick_path* into *weird_dir*, returning where it landed.

    Returns None when the flick is already gone — two WEIRD verbs can name the
    same flick before the first has finished, and the second must not take the
    Funestra down with it.
    """
    if not flick_path.exists():
        return None
    weird_dir.mkdir(parents=True, exist_ok=True)
    destination = weird_dir / flick_path.name
    flick_path.replace(destination)
    return destination
