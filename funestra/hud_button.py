"""A button a content source declares on a Funestra's HUD.

The source says what each button posts, what face it wears and what state it is
in; the Funestra lays the buttons out, draws them and posts the declared verb.
The record and its published form live together so a source in another
process (Fun Time, writing the HUD files) and one in the Funestra's own (a hosted
Origenerator) spell a button the same way.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from shared_ui.icon_geometry import tooltip_for
from shared_ui.spacing import BUTTON_SIZE_HUD

from .hud_marks import SHARED_MARK, shared_mark_name

__all__ = [
    "BUTTON",
    "FIT_THE_WORD",
    "Button",
]

BUTTON = BUTTON_SIZE_HUD  # a square control; the wider ones say their own width

# A word-carrying button asking the painter to size it to its word.
FIT_THE_WORD = 0


@dataclass(frozen=True)
class Button:
    """One item on a HUD: what it posts, what it looks like, how it is drawn.

    ``lit``, ``warn`` and ``hold`` are the live states — the family's blue for
    on, red for a live recording, blue for the loop that recording leaves
    running.  ``favorite`` names a control whose on-state is green (the
    favorites and the funscripts own that color); ``enhanced`` one whose mark
    and on-state are amber (an enhanced picture's own).  ``dim`` is a control
    at the end of its range or with nothing to act on: drawn faded and never a
    hit target.  ``danger`` draws the mark red — a control that takes something
    away.  ``remembered`` is a choice held but not applied, on the active gray.
    ``group_break`` opens the wider gap before this button.

    An empty ``command`` makes it a read-out: laid out in the row like anything
    else, drawn as bare text with no button, and never a hit target.  A read-out
    whose number only the drawing host knows names it in ``host_value``
    ("playback_speed", "advance_interval") and the painter fills it in.
    """

    command: str
    glyph: str
    tooltip: str
    width: int = BUTTON
    lit: bool = False
    warn: bool = False
    hold: bool = False
    dim: bool = False
    favorite: bool = False
    enhanced: bool = False
    danger: bool = False
    remembered: bool = False
    group_break: bool = False
    host_value: str = ""

    @property
    def tooltip_on_hover(self) -> str:
        if not self.glyph.startswith(SHARED_MARK):
            return self.tooltip
        return tooltip_for(shared_mark_name(self.glyph), self.tooltip)


_FLAGS = tuple(f.name for f in fields(Button) if f.type == "bool")
_WORDS = ("command", "glyph", "tooltip", "host_value")


def button_raw(button: Button) -> dict:
    raw: dict = {name: getattr(button, name) for name in _WORDS if getattr(button, name)}
    raw["width"] = button.width
    raw.update({name: True for name in _FLAGS if getattr(button, name)})
    return raw


def button_from_raw(raw: object) -> Button | None:
    if not isinstance(raw, dict):
        return None
    words = {name: str(raw.get(name, "") or "") for name in _WORDS}
    flags = {name: bool(raw.get(name, False)) for name in _FLAGS}
    return Button(**words, width=int(raw.get("width", BUTTON) or 0), **flags)


def buttons_raw(buttons: tuple[Button, ...]) -> list[dict]:
    return [button_raw(button) for button in buttons]


def buttons_from_raw(raw: object) -> tuple[Button, ...]:
    if not isinstance(raw, list):
        return ()
    buttons = [button_from_raw(item) for item in raw]
    return tuple(button for button in buttons if button is not None)


def rows_raw(rows: tuple[tuple[Button, ...], ...]) -> list[list[dict]]:
    return [buttons_raw(row) for row in rows]


def rows_from_raw(raw: object) -> tuple[tuple[Button, ...], ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(buttons_from_raw(row) for row in raw if isinstance(row, list))
