from __future__ import annotations

import base64
import subprocess
from collections.abc import Callable
from threading import Thread

from app_support.subprocess_utils import hidden_subprocess_kwargs
from app_support.threading_utils import start_daemon_thread
from shared_ui.palette import TEXT_MUTED, hovered
from shared_ui.spacing import GAP_SMALL

from .geometry import Rect, contains
from .hud_button import Button
from .hud_icons import shared_icon

COPY_ICON = "copy"
COPY_TOOLTIP = "Copy to clipboard"
COPY_NAME = "copy_name"
COPY_GAP = GAP_SMALL


def copy_button() -> Button:
    return Button(COPY_NAME, shared_icon(COPY_ICON), COPY_TOOLTIP)


def copy_icon_rect(after_x: int, line_top: int, line_h: int) -> Rect:
    return (after_x + COPY_GAP, line_top, line_h, line_h)


def copy_icon_ink(rect: Rect, pointer: tuple[int, int] | None) -> tuple[int, int, int, int]:
    pointed_at = pointer is not None and contains(rect, *pointer)
    return (*(hovered(TEXT_MUTED) if pointed_at else TEXT_MUTED), 255)


def copy_to_clipboard(text: str, *, run: Callable[..., object] = subprocess.run) -> None:
    run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _set_clipboard_to(text)],
        check=False, **hidden_subprocess_kwargs())


def _set_clipboard_to(text: str) -> str:
    spelled = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return ("Set-Clipboard -Value ([Text.Encoding]::UTF8.GetString("
            f"[Convert]::FromBase64String('{spelled}')))")


def copy_while_the_funestra_plays_on(text: str, *,
                                     run: Callable[..., object] = subprocess.run) -> Thread:
    return start_daemon_thread(target=copy_to_clipboard, args=(text,), kwargs={"run": run},
                               name="copy-name")
