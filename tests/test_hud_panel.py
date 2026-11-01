"""funestra.hud_panel answers only until the Fun Time branches still importing it
are rebased; this test goes with the module."""
from __future__ import annotations

from funestra import hud


def test_the_huds_old_module_path_gives_what_the_hud_module_has():
    from funestra.hud_panel import HudPanel, load_font  # noqa: PLC0415

    assert (HudPanel, load_font) == (hud.Hud, hud.load_font)
