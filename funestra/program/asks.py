from __future__ import annotations

from pathlib import Path

from ..dashboard import ask

KEY = "key"
FOCUSED = "focused"


def key_pressed(name: str, held: str) -> str:
    return f"{KEY}|{name}|{held}"


def tell_the_app_a_key(dashboard_cmd: Path | None, name: str, held: str) -> None:
    ask(dashboard_cmd, key_pressed(name, held))


def tell_the_app_it_came_forward(dashboard_cmd: Path | None) -> None:
    ask(dashboard_cmd, FOCUSED)
