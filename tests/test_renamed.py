"""A checkout from before a rename still imports and runs: from before the HUD
stopped being called a panel, and, in the HUD a satellite is handed, from before
the Player became the Funestra.

Every open branch of an app runs out of that app's one venv, so these are the
names those branches spell until they are rebased. Each test is one thing such a
checkout does; when no checkout does it any more, the test goes with the name.
"""
from __future__ import annotations

import inspect
import json

from funestra_fakes import FakeEngine

from funestra import hud
from funestra.funestra import Channels, Funestra, HudSurface
from funestra.playlist import PlaylistItem
from funestra.satellite_hud import HudModel, hud_text, parse_hud


def test_a_hud_written_before_the_rename_still_reads():
    assert parse_hud('{"player": "landscape"}').funestra == "landscape"


def test_the_published_hud_names_its_funestra_under_both_keys():
    raw = json.loads(hud_text(HudModel(funestra="portrait")))

    assert (raw["funestra"], raw["player"]) == ("portrait", "portrait")


def test_the_huds_old_module_path_gives_what_the_hud_module_has():
    from funestra.hud_panel import HudPanel, load_font  # noqa: PLC0415

    assert (HudPanel, load_font) == (hud.Hud, hud.load_font)


def test_a_funestra_takes_its_hud_under_the_old_keyword_and_answers_to_the_old_names(tmp_path):
    funestra = Funestra(FakeEngine(), channels=Channels(), playlist=[PlaylistItem(tmp_path / "v0.mp4")],
                        panel=lambda: None)

    assert (funestra.panel_edge, funestra.panel_minimized, funestra._panel) == (
        funestra.hud_edge, funestra.hud_minimized, funestra._hud)


def test_a_funestras_signature_names_the_old_keywords_its_shells_still_hand_it():
    signature = inspect.signature(Funestra)
    window = inspect.signature(Funestra.on_window)

    assert {"panel", "panel_surface"} <= signature.parameters.keys()
    assert "panel" in window.parameters


def test_the_surface_a_hud_is_drawn_on_answers_to_its_old_name():
    from funestra.funestra import PanelSurface  # noqa: PLC0415

    assert PanelSurface is HudSurface
