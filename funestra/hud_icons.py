"""How a HUD control says it wants one of the family's drawn marks.

A console model is a plain description the painter reads -- no colors, no
Pillow -- and that is worth keeping: it is what lets the model be built, tested
and sent around without a drawing toolkit anywhere near it.  So a control that
wants one of :mod:`shared_ui.icon_geometry`'s marks NAMES it, with the marker
below, and the painter is what turns the name into pixels
(:func:`funestra.hud.draw_mark`).

This module holds only the naming, and imports nothing, so both a model module
and a painter can use it without either dragging the other's dependencies along.
"""

from __future__ import annotations

SHARED_ICON = "\x00glyph:"


def shared_icon(name: str) -> str:
    """The marker standing for one of :mod:`shared_ui.icon_geometry`'s marks."""
    return SHARED_ICON + name


def shared_icon_name(icon: str) -> str:
    """Which mark *icon* stands for; only call it on a :data:`SHARED_MARK` one."""
    return icon[len(SHARED_ICON):]


# An app's own mark: the magenta five-by-five letter its .ico carries, drawn
# from :data:`shared_ui.app_icon.LETTERS` by the letter the marker names.
APP_ICON = "\0app:"


def app_icon(letter: str) -> str:
    return APP_ICON + letter


def app_mark_letter(icon: str) -> str:
    """Which letter *icon* stands for; only call it on an :data:`APP_MARK` one."""
    return icon[len(APP_ICON):]


# The two controls that stand for an app rather than for an action: the OSR2
# broker's "B" and F-mode's "F".
BROKER_ICON = app_icon("B")
FMODE_ICON = app_icon("F")

MINIMIZE_ICON = shared_icon("minus")

# The transport and the lock every source declares on a Funestra.
PREVIOUS_ICON = shared_icon("chevron_left")
BACK_ICON = shared_icon("chevrons_left")
FORWARD_ICON = shared_icon("chevrons_right")
NEXT_ICON = shared_icon("chevron_right")
LOCK_ICON = shared_icon("lock")

# The family's on/off switch, on while its button is lit.
TOGGLE_SWITCH = "\0switch"
