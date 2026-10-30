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

MINIMIZE_ICON = shared_mark("minus")

# The transport and the lock every source declares on a Funestra.
PREVIOUS_ICON = shared_mark("chevron_left")
BACK_ICON = shared_mark("chevrons_left")
FORWARD_ICON = shared_mark("chevrons_right")
NEXT_ICON = shared_mark("chevron_right")
LOCK_ICON = shared_mark("lock")

# What a funestra from before a control wore the family's mark publishes for it:
# Origenerator publishes its HUD from a funestra of its own, which can be older
# than the one drawing it.
_RETIRED_GLYPHS = {"\0minimize": MINIMIZE_ICON}


def current_glyph(glyph: str) -> str:
    return _RETIRED_GLYPHS.get(glyph, glyph)

# The family's on/off switch, on while its button is lit.
TOGGLE_SWITCH = "\0switch"
