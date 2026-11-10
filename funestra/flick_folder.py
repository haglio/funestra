from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path

from app_support import haglio_settings
from app_support.flick_folder import (
    flat_flicks_in,  # noqa: F401 -- handed on to the apps, which import it from here
    trash_folder_beside,
    vr_flicks_in,  # noqa: F401
)
from app_support.trash_names import spot_in_trash

SUPPORTED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def _modified_at(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def scan_flicks(
    folders: Path | Iterable[Path], *, shuffle_on_load: bool = True, recent: bool = False,
    shuffle=random.shuffle,
) -> list[Path]:
    folders = (Path(folders),) if isinstance(folders, (str, Path)) else tuple(Path(f) for f in folders)
    files = [path for folder in folders for path in sorted(folder.rglob("*"))
             if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTS]
    if not files:
        raise RuntimeError(f"No video {haglio_settings.value('genau_flick_words', 'many')} found in: "
                           f"{', '.join(str(f) for f in folders)}")
    if recent:
        return sorted(files, key=_modified_at, reverse=True)
    if shuffle_on_load:
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
