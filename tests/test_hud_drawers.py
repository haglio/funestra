from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest
from app_support.dead_code import tracked_python
from app_support.siblings import checkouts_that_import

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "funestra"
PACKAGE_NAMES = ("funestra",)

WHOLE_MODULE = None

HUD_PAINTERS: dict[str, set[str] | None] = {
    "satellite_hud_paint": WHOLE_MODULE,
    "hud": WHOLE_MODULE,
    "hud_row": WHOLE_MODULE,
    "hud_minimize": WHOLE_MODULE,
    "hud_corners": {"plus_bgra"},
    "outside_buttons": WHOLE_MODULE,
    "hud_osr2": WHOLE_MODULE,
    "hud_overlay": WHOLE_MODULE,
    "main_hud_painter": {"MainHudPainter"},
    "playhead": {"PlayheadHudPainter"},
    "volume": {"VolumeHudPainter"},
    "scrubber_bar": {"progress_bar_bgra"},
    "osr2_visualizer": {"DriveSection"},
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


@dataclass(frozen=True)
class _AppSource:
    sibling: str
    package: str
    path: str
    text: str

    @property
    def tree(self) -> ast.AST | None:
        try:
            return ast.parse(self.text)
        except SyntaxError:
            return None


def _app_sources() -> tuple[list[_AppSource], list[str]]:
    consumers = checkouts_that_import(*PACKAGE_NAMES, near=Path(__file__))
    sources = [
        _AppSource(sibling.name, path.relative_to(sibling).parts[0],
                   str(path.relative_to(sibling)),
                   path.read_text(encoding="utf-8", errors="replace"))
        for sibling in consumers for path in tracked_python(sibling)
        if path.relative_to(sibling).parts[0] not in _NOT_A_DRAWER
    ]
    return sources, [sibling.name for sibling in consumers]


def _drawers(sources: list[_AppSource]) -> dict[tuple[str, str], set[str]]:
    drawers: dict[tuple[str, str], set[str]] = defaultdict(set)
    for source in sources:
        for painter in _painters_reached(source.text):
            drawers[(source.sibling, source.package)].add(f"{painter} in {source.path}")
    return dict(drawers)


@pytest.fixture(scope="module")
def app_sources() -> tuple[list[_AppSource], list[str]]:
    sources, consumers = _app_sources()
    if not consumers:
        pytest.skip("no sibling checkout beside this one imports funestra, so there is "
                    "nothing to hold the drawers against")
    return sources, consumers


@pytest.fixture(scope="module")
def drawers_and_consumers(app_sources):
    sources, consumers = app_sources
    return _drawers(sources), consumers


def _hud_part_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for module, listed in HUD_PAINTERS.items():
        tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
        public = {node.name for node in tree.body
                  if isinstance(node, ast.FunctionDef | ast.ClassDef)
                  and not node.name.startswith("_")}
        names.update((name, module) for name in (public if listed is WHOLE_MODULE else listed))
    return names


def _definitions_named_like_a_hud_part(source: _AppSource, parts: dict[str, str]) -> list[str]:
    tree = source.tree
    if tree is None:
        return []
    return [f"{source.sibling}/{source.path}:{node.lineno} {node.name} ({parts[node.name]} here)"
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.ClassDef) and node.name in parts]


def test_no_app_defines_a_hud_part_under_a_name_this_package_draws_it_by_since_every_funestra_draws_the_one_here_and_a_second_copy_drifts(
        app_sources):
    sources, consumers = app_sources
    parts = _hud_part_names()
    copies = [line for source in sources
              for line in _definitions_named_like_a_hud_part(source, parts)]
    assert copies == [], (
        f"an app defines a HUD part this package already draws for every Funestra (read from: "
        f"{', '.join(consumers)}); draw the one here, or name the app's own thing for what it is:\n"
        + "\n".join(f"  {line}" for line in copies))


def _shared_control_icons() -> tuple[set[str], set[str]]:
    tree = ast.parse((PACKAGE / "hud_controls.py").read_text(encoding="utf-8"))
    names = {node.args[1].id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "Button" and len(node.args) > 1
             and isinstance(node.args[1], ast.Name)}
    keys = {node.value.args[0].value for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "shared_icon"
            and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)}
    return names, keys


def _buttons_wearing_a_shared_controls_face(source: _AppSource, names: set[str],
                                            keys: set[str]) -> list[str]:
    tree = source.tree
    if tree is None:
        return []

    def wears_one(argument: ast.expr) -> bool:
        if isinstance(argument, ast.Name):
            return argument.id in names
        return (isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name)
                and argument.func.id == "shared_icon" and len(argument.args) == 1
                and isinstance(argument.args[0], ast.Constant) and argument.args[0].value in keys)

    return [f"{source.sibling}/{source.path}:{node.lineno}" for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "Button" and any(wears_one(argument) for argument in node.args)]


def test_the_shared_controls_icons_are_read_off_hud_controls():
    names, keys = _shared_control_icons()

    assert {"PREVIOUS_ICON", "NEXT_ICON", "LOCK_ICON", "TRASH_ICON", "FMODE_ICON"} <= names
    assert {"trash", "reset", "shuffle", "latest", "versions"} <= keys


def test_no_app_declares_a_control_every_funestra_shares_since_each_is_one_button_here_that_looks_sits_and_grays_alike_whichever_source_draws_it(
        app_sources):
    sources, consumers = app_sources
    names, keys = _shared_control_icons()
    declared = [line for source in sources
                for line in _buttons_wearing_a_shared_controls_face(source, names, keys)]
    assert declared == [], (
        f"an app builds a Button wearing a shared control's icon (read from: {', '.join(consumers)}); "
        "take the control from funestra.hud_controls, with the app's own command and words:\n"
        + "\n".join(f"  {line}" for line in declared))


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
    by_name = _painters_reached("from funestra.main_hud_painter import MainHudPainter\n")
    by_module = _painters_reached(
        "from funestra import main_hud_painter\npainter = main_hud_painter.MainHudPainter()\n")
    by_dotted = _painters_reached(
        "import funestra.playhead as playhead\npainter = playhead.PlayheadHudPainter()\n")
    model_only = _painters_reached("from funestra.main_hud_painter import MainHud\n")

    assert by_name == by_module == {"main_hud_painter.MainHudPainter"}
    assert by_dotted == {"playhead.PlayheadHudPainter"}
    assert model_only == set()


@pytest.mark.parametrize("module", ["hud_icons", "hud_title", "main_hud", "scrubber", "scrubber_bar"])
def test_a_module_that_describes_a_hud_imports_no_drawing_toolkit_so_it_is_built_tested_and_sent_about_without_one(
        module):
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom)}

    assert not imported & {"PIL", "pygame"}
