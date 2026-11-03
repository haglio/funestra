
from __future__ import annotations

SHARED_ICON = "\x00glyph:"


def shared_icon(name: str) -> str:
    return SHARED_ICON + name


def shared_icon_name(icon: str) -> str:
    return icon[len(SHARED_ICON):]


APP_ICON = "\0app:"


def app_icon(letter: str) -> str:
    return APP_ICON + letter


def app_mark_letter(icon: str) -> str:
    return icon[len(APP_ICON):]


BROKER_ICON = app_icon("B")
FMODE_ICON = app_icon("F")

MINIMIZE_ICON = shared_icon("minus")

PREVIOUS_ICON = shared_icon("chevron_left")
BACK_ICON = shared_icon("chevrons_left")
FORWARD_ICON = shared_icon("chevrons_right")
NEXT_ICON = shared_icon("chevron_right")
LOCK_ICON = shared_icon("lock")

TOGGLE_SWITCH = "\0switch"
