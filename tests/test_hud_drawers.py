"""The gate on who draws a HUD: a Funestra, and the drawers still to move onto one.

Read from the checkouts beside this one that import it, the way the dead-code
gate reads them: a package of one that imports a painter out of this one is
drawing a HUD itself.  A painter is what turns a panel, a row or a chip into pixels; the
models, the verbs and the placements a source hands a Funestra are not.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest
from app_support.dead_code import tracked_python
from app_support.siblings import checkouts_that_import

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "funestra"
PACKAGE_NAMES = ("funestra", "funestra_core", "player_core")

WHOLE_MODULE = None

HUD_PAINTERS: dict[str, set[str] | None] = {
    "satellite_hud_paint": WHOLE_MODULE,
    "hud_panel": WHOLE_MODULE,
    "hud_row": WHOLE_MODULE,
    "hud_minimize": WHOLE_MODULE,
    "hud_corners": {"plus_bgra"},
    "outside_buttons": WHOLE_MODULE,
    "hud_osr2": WHOLE_MODULE,
    "hud_overlay": WHOLE_MODULE,
    "console_hud": {"ConsolePainter"},
    "playhead": {"PlayheadHudPainter"},
    "volume": {"VolumeHudPainter"},
    "timeline": {"progress_bar_bgra"},
    "drive_readout": {"DriveSection"},
    "host_controls": {"HostControlsSection"},
}

KNOWN_DRAWERS = {
    ("origenerator", "origenerator"),
}

DRAWS_A_FUNESTRAS_MODE_PAIR_WHERE_NO_FUNESTRA_IS = {
    ("fun_time", "fun_time"),
}

ALLOWED_DRAWERS = KNOWN_DRAWERS | DRAWS_A_FUNESTRAS_MODE_PAIR_WHERE_NO_FUNESTRA_IS

_NOT_A_DRAWER = {"tests"}


def is_this_package(module: str | None) -> bool:
    return (module or "").partition(".")[0] in PACKAGE_NAMES


def _is_painter(module: str, name: str) -> bool:
    names = HUD_PAINTERS.get(module, set())
    return module in HUD_PAINTERS and (names is WHOLE_MODULE or name in names)


def _painters_reached(source: str) -> set[str]:
    if not any(name in source for name in PACKAGE_NAMES):
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    bound: dict[str, str] = {}
    reached: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and is_this_package(node.module):
            if "." in node.module:
                module = node.module.split(".", 1)[1]
                reached.update(f"{module}.{alias.name}" for alias in node.names
                               if _is_painter(module, alias.name))
            else:
                bound.update((alias.asname or alias.name, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            bound.update((alias.asname or alias.name.split(".")[-1], alias.name.split(".")[-1])
                         for alias in node.names if is_this_package(alias.name) and "." in alias.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            module = bound.get(node.value.id)
            if module is not None and _is_painter(module, node.attr):
                reached.add(f"{module}.{node.attr}")
    return reached


def _drawers() -> tuple[dict[tuple[str, str], set[str]], list[str]]:
    drawers: dict[tuple[str, str], set[str]] = defaultdict(set)
    consumers = checkouts_that_import(*PACKAGE_NAMES, near=Path(__file__))
    for sibling in consumers:
        for path in tracked_python(sibling):
            package = path.relative_to(sibling).parts[0]
            if package in _NOT_A_DRAWER:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            for painter in _painters_reached(source):
                drawers[(sibling.name, package)].add(f"{painter} in {path.relative_to(sibling)}")
    return dict(drawers), [sibling.name for sibling in consumers]


@pytest.fixture(scope="module")
def drawers_and_consumers():
    drawers, consumers = _drawers()
    if not consumers:
        pytest.skip("no sibling checkout beside this one imports funestra, so there is "
                    "nothing to hold the drawers against")
    return drawers, consumers


def test_a_painter_names_a_module_this_package_has():
    missing = sorted(module for module in HUD_PAINTERS
                     if not (PACKAGE / f"{module}.py").is_file())
    assert missing == []


def test_nothing_outside_the_known_drawers_paints_a_hud(drawers_and_consumers):
    drawers, consumers = drawers_and_consumers
    new = {where: found for where, found in drawers.items() if where not in ALLOWED_DRAWERS}
    assert not new, (
        f"a package draws a HUD itself (read from: {', '.join(consumers)}). "
        "Only a Funestra draws one: run on a Funestra and hand it the buttons to draw:\n"
        + "\n".join(f"  {sibling}/{package}: {painter}"
                    for (sibling, package), found in sorted(new.items()) for painter in sorted(found))
    )


def test_every_known_drawer_still_draws(drawers_and_consumers):
    drawers, consumers = drawers_and_consumers
    moved_on = sorted(ALLOWED_DRAWERS - set(drawers))
    assert not moved_on, (
        f"listed as a drawer and no longer drawing (read from: {', '.join(consumers)}); "
        "take its line out of the list it is in:\n"
        + "\n".join(f"  {sibling}/{package}" for sibling, package in moved_on)
    )


def test_a_painter_reached_by_module_counts_as_well_as_one_imported_by_name():
    by_name = _painters_reached("from funestra.console_hud import ConsolePainter\n")
    by_module = _painters_reached(
        "from funestra import console_hud\npainter = console_hud.ConsolePainter()\n")
    by_dotted = _painters_reached(
        "import funestra.playhead as playhead\npainter = playhead.PlayheadHudPainter()\n")
    model_only = _painters_reached("from funestra.console_hud import ConsoleHud\n")

    assert by_name == by_module == {"console_hud.ConsolePainter"}
    assert by_dotted == {"playhead.PlayheadHudPainter"}
    assert model_only == set()
