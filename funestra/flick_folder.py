from __future__ import annotations

import os
import random
from collections.abc import Iterable, Iterator
from pathlib import Path

from app_support import haglio_settings
from app_support.flick_folder import (
    flat_flicks_in,  # noqa: F401 -- handed on to the apps, which import it from here
    trash_folder_beside,
    vr_flicks_in,  # noqa: F401
)
from app_support.trash_names import spot_in_trash

from .inclusion_pair import including_no_other

SUPPORTED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def _flicks() -> str:
    return haglio_settings.value("genau_flick_words", "many")


def no_other_flicks() -> str:
    return including_no_other(_flicks())


def _modified_at(entry: os.DirEntry) -> float:
    try:
        return entry.stat().st_mtime
    except OSError:
        return 0.0


def _videos_under(folder: Path) -> Iterator[os.DirEntry]:
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            yield from _videos_under(Path(entry.path))
        elif entry.is_file() and Path(entry.name).suffix.lower() in SUPPORTED_VIDEO_EXTS:
            yield entry


def scan_flicks(
    folders: Path | Iterable[Path], *, shuffle_on_load: bool = True, recent: bool = False,
    shuffle=random.shuffle,
) -> list[Path]:
    folders = (Path(folders),) if isinstance(folders, (str, Path)) else tuple(Path(f) for f in folders)
    entries = [entry for folder in folders
               for entry in sorted(_videos_under(folder), key=lambda entry: Path(entry.path))]
    if not entries:
        raise RuntimeError(f"No video {_flicks()} found in: "
                           f"{', '.join(str(f) for f in folders)}")
    if recent:
        entries.sort(key=_modified_at, reverse=True)
    files = [Path(entry.path) for entry in entries]
    if shuffle_on_load and not recent:
        shuffle(files)
    return files


def trash_folder_for(flick: Path, flicks_folder: Path) -> Path:
    trash = trash_folder_beside(flicks_folder)
    try:
        return trash / flick.parent.relative_to(flicks_folder)
    except ValueError:
        return trash


def move_to_trash(video: Path, trash_folder: Path) -> Path | None:
    if not video.exists():
        return None
    trash_folder.mkdir(parents=True, exist_ok=True)
    spot = spot_in_trash(trash_folder, video.name)
    video.replace(spot)
    return spot
