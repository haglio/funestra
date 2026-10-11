"""A button a content source declares on a Funestra's HUD, and its published form."""
from __future__ import annotations

import json

from shared_ui.icon_geometry import tooltip_for

from funestra.hud_button import Button, rows_from_raw, rows_raw
from funestra.hud_marks import shared_mark

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
