"""How a HUD control says it wants one of the family's drawn marks.

A console model is a plain description the painter reads -- no colors, no
Pillow -- and that is worth keeping: it is what lets the model be built, tested
and sent around without a drawing toolkit anywhere near it.  So a control that
wants one of :mod:`shared_ui.icon_geometry`'s marks NAMES it, with the marker
below, and the painter is what turns the name into pixels
(:func:`funestra.hud_panel.draw_mark`).

This module holds only the naming, and imports nothing, so both a model module
and a painter can use it without either dragging the other's dependencies along.
"""

from __future__ import annotations

__all__ = [
    "BROKER_ICON",
    "FMODE_ICON",
    "MINIMIZE_ICON",
    "SHARED_MARK",
    "shared_mark",
    "shared_mark_name",
]

SHARED_MARK = "\x00glyph:"


def shared_mark(name: str) -> str:
    """The marker standing for one of :mod:`shared_ui.icon_geometry`'s marks."""
    return SHARED_MARK + name


def shared_mark_name(glyph: str) -> str:
    """Which mark *glyph* stands for; only call it on a :data:`SHARED_MARK` one."""
    return glyph[len(SHARED_MARK):]


# An app's own mark: the magenta five-by-five letter its .ico carries, drawn
# from :data:`shared_ui.app_icon.LETTERS` by the letter the marker names.
APP_MARK = "\0app:"


def app_mark(letter: str) -> str:
    return APP_MARK + letter


def app_mark_letter(glyph: str) -> str:
    """Which letter *glyph* stands for; only call it on an :data:`APP_MARK` one."""
    return glyph[len(APP_MARK):]


# The two controls that stand for an app rather than for an action: the OSR2
# broker's "B" and F-mode's "F".
BROKER_ICON = app_mark("B")
FMODE_ICON = app_mark("F")

# A drawn bar rather than a glyph: the minimize mark Windows puts on a title bar
# is in a face these HUDs do not load, and a painter draws the bar instead.
MINIMIZE_ICON = "\0minimize"
