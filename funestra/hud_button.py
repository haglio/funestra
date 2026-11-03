from __future__ import annotations

from dataclasses import dataclass, fields

from shared_ui.icon_geometry import tooltip_for
from shared_ui.spacing import BUTTON_SIZE_HUD

from .hud_icons import SHARED_ICON, shared_icon_name

BUTTON = BUTTON_SIZE_HUD

FIT_THE_WORD = 0


@dataclass(frozen=True)
class Button:
    command: str
    icon: str
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
    def is_a_name(self) -> bool:
        return self.icon[:1].isalpha()

    @property
    def tooltip_on_hover(self) -> str:
        if not self.icon.startswith(SHARED_ICON):
            return self.tooltip
        return tooltip_for(shared_icon_name(self.icon), self.tooltip)


_FLAGS = tuple(f.name for f in fields(Button) if f.type == "bool")
_WIRE_KEYS = {"command": "command", "icon": "glyph", "tooltip": "tooltip", "host_value": "host_value"}


def button_raw(button: Button) -> dict:
    raw: dict = {key: getattr(button, name) for name, key in _WIRE_KEYS.items() if getattr(button, name)}
    raw["width"] = button.width
    raw.update({name: True for name in _FLAGS if getattr(button, name)})
    return raw


def button_from_raw(raw: object) -> Button | None:
    if not isinstance(raw, dict):
        return None
    words = {name: str(raw.get(key, "") or "") for name, key in _WIRE_KEYS.items()}
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
