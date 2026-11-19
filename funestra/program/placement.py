from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

PLACEMENT = (
    ("x", "--x"),
    ("y", "--y"),
    ("width", "--width"),
    ("height", "--height"),
    ("title", "--title"),
    ("taskbar_identity", "--taskbar-identity"),
    ("icon", "--icon"),
    ("tiles", "--tile"),
)


@dataclass(frozen=True)
class WindowPlacement:
    x: int | None = None
    y: int | None = None
    width: int = 1200
    height: int = 900
    title: str = "Funestra"
    taskbar_identity: str | None = None
    icon: Path | None = None
    tiles: bool = False

    @classmethod
    def from_args(cls, args) -> WindowPlacement:
        return cls(x=args.x, y=args.y, width=args.width, height=args.height,
                   title=args.title, taskbar_identity=args.taskbar_identity,
                   icon=args.icon, tiles=args.tile)

    def to_argv(self) -> list[str]:
        words: list[str] = []
        for field, flag in PLACEMENT:
            value = getattr(self, field)
            if isinstance(value, bool):
                words += [flag] if value else []
            elif value is not None:
                words += [flag, str(value)]
        return words


def add_placement_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--width", type=int, default=WindowPlacement.width)
    parser.add_argument("--height", type=int, default=WindowPlacement.height)
    parser.add_argument("--x", type=int, default=None)
    parser.add_argument("--y", type=int, default=None)
    parser.add_argument("--title", type=str, default=WindowPlacement.title,
                        help="Window caption, which the app that starts a Funestra finds its window by")
    parser.add_argument("--tile", action="store_true", default=False,
                        help="Show a portrait item side by side, as many times as "
                             "fit, while the window is wider than it is tall")
    parser.add_argument("--taskbar-identity", default=None,
                        help="Group this window under the launching application's taskbar "
                             "button; the app that starts it passes its own AppUserModelID")
    parser.add_argument("--icon", type=Path, default=None,
                        help="The window icon the app hands over, so an Alt-Tab entry "
                             "and a taskbar thumbnail show which app it belongs to")
