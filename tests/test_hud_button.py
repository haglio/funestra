"""A button a content source declares on a Funestra's HUD, and its published form."""
from __future__ import annotations

import json

from shared_ui.icon_geometry import tooltip_for

from funestra.hud_button import Button, rows_from_raw, rows_raw
from funestra.hud_marks import (
    BACK_ICON,
    FORWARD_ICON,
    LOCK_ICON,
    MINIMIZE_ICON,
    NEXT_ICON,
    PREVIOUS_ICON,
    shared_mark,
)

_A_MARK_THIS_VERSION_LACKS = "a_mark_from_another_version"


def test_a_declared_button_survives_the_round_trip_through_json():
    rows = (
        (Button("portrait_prev", "⏮", "Previous clip"),
         Button("portrait_lock", "🔒", "Lock / unlock this clip", lit=True, favorite=True)),
        (Button("origenerator_activate", "Origenerator", "Origenerator mode", width=0,
                group_break=True, dim=True),
         Button("", "", "", width=22, host_value="playback_speed")),
    )

    assert rows_from_raw(json.loads(json.dumps(rows_raw(rows)))) == rows


def test_a_button_wearing_a_mark_this_version_lacks_says_why_under_its_own_tooltip():
    button = Button("auto", shared_mark(_A_MARK_THIS_VERSION_LACKS), "Generate on its own")

    assert button.tooltip_on_hover == tooltip_for(_A_MARK_THIS_VERSION_LACKS,
                                                  "Generate on its own")


def test_a_button_with_a_typed_glyph_or_a_word_keeps_its_own_tooltip():
    for face in ("⏮", "Origenerator", ""):
        assert Button("go", face, "Go there").tooltip_on_hover == "Go there", face


def test_a_button_wearing_a_real_mark_keeps_its_own_tooltip():
    assert Button("weird", shared_mark("trash"), "Mark weird").tooltip_on_hover == "Mark weird"


def test_minimize_wears_the_familys_minus():
    assert shared_mark("minus") == MINIMIZE_ICON


def test_a_minimize_published_before_it_wore_the_minus_reads_back_as_the_minus():
    """Origenerator publishes its HUD from its own funestra, which can be older
    than the one drawing it, and an older one spelled minimize its own way."""
    raw = [[{"command": "show_minimize", "glyph": "\0minimize", "tooltip": "Minimize"}]]

    assert rows_from_raw(raw) == ((Button("show_minimize", shared_mark("minus"), "Minimize"),),)


def test_the_transport_and_the_lock_every_source_declares_wear_the_familys_marks():
    """Fun Time and Origenerator both declare these on a Funestra, so they take
    their faces from here rather than each typing its own."""
    faces = (PREVIOUS_ICON, BACK_ICON, FORWARD_ICON, NEXT_ICON, LOCK_ICON)

    assert faces == tuple(shared_mark(name) for name in
                          ("chevron_left", "chevrons_left", "chevrons_right", "chevron_right", "lock"))
