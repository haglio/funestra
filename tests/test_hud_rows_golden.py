from __future__ import annotations

import json
from pathlib import Path

import pytest

from funestra.hud_button import rows_raw
from funestra.hud_kinds import HudFacts, HudKind, device_rows, hud_rows
from funestra.modes import LengthMode, MainMode

_CASES = json.loads((Path(__file__).parent / "golden" / "hud_rows.json").read_text(encoding="utf-8"))


def _facts(kind: str, raw: dict) -> HudFacts:
    raw = dict(raw)
    if kind == "main":
        raw["main_mode"] = MainMode(raw["main_mode"])
        raw["length_mode"] = LengthMode(raw["length_mode"])
        raw["snippet"] = "" if raw["snippet"] == "normal" else raw["snippet"]
        raw.update(funestra="main", flick_one="pip", flick_many="pips")
    return HudFacts(**raw)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["kind"])
def test_every_hud_shows_the_buttons_its_app_listed_for_it(case):
    kind, facts = HudKind(case["kind"]), _facts(case["kind"], case["facts"])

    assert rows_raw(hud_rows(kind, facts)) == case["rows"]
    assert rows_raw(device_rows(kind, facts)) == case["device"]
