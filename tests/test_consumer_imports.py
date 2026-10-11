"""This repo's dead-code gate: the API each module declares is what the consumers reach.

**Not vulture, and deliberately so.** Every caller of this package lives in
another repo, so a scanner looking for callers here flags the entire public API
and the whitelist that quiets it just restates that API -- a gate that can never
fail. `CLAUDE.md` says not to add one back, and this is not it.

The answerable question is the one the consumers can answer. Every module
declares its public API in ``__all__``; this reads the sibling checkouts,
collects every name they import out of `funestra` (or `funestra_core` or
`player_core`, its old names), and holds the two
against each other in both directions: a declared name no consumer reaches is
a name published for nobody, and a name a consumer reaches that its module does
not declare is an API the module never meant to have.  A module that declares
nothing is package-internal, and says so.

**What it costs.** The answer depends on the sibling checkouts as they sit on
disk. One that is absent, or one on a branch that has dropped an import, moves
names into the unreached set and turns this red -- with the checkouts it read
named in the message, so the cause is in front of whoever sees it. The merge
gate clones the three consumers beside this repo for exactly that reason, so
what it holds the surface against there is their default branches; on the
developer machine it is the checkouts as they sit. A tree with no consumer
beside it at all -- a public clone, and nothing else now -- has nothing to
compare against and skips.
"""
from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "funestra"
PACKAGE_NAMES = ("funestra", "funestra_core", "player_core")

_NOT_SOURCE = {".venv", ".claude", "build", "__pycache__", "node_modules"}


def _primary_checkout(repo: Path) -> Path:
    """The checkout *repo* belongs to, given a worktree or the primary itself.

    Worktrees share one git directory whose parent is the primary. Anchoring on
    the primary matters: a worktree lives at `<primary>/.claude/worktrees/<name>`
    and its neighbours are other worktrees, not the sibling repos.
    """
    try:
        common = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return repo
    return (repo / common).resolve().parent


def _other_repos_beside(repo: Path):
    primary = _primary_checkout(repo)
    for sibling in sorted(primary.parent.iterdir()):
        if sibling.is_dir() and sibling != primary and not any(
                (sibling / name / "__init__.py").is_file() for name in PACKAGE_NAMES):
            yield sibling


def is_this_package(module: str | None) -> bool:
    return (module or "").partition(".")[0] in PACKAGE_NAMES


def _source_files(checkout: Path):
    for directory, subdirectories, files in os.walk(checkout):
        subdirectories[:] = [name for name in subdirectories
                             if name not in _NOT_SOURCE and not name.endswith(".egg-info")]
        yield from (Path(directory) / name for name in files if name.endswith(".py"))


def _modules():
    return sorted(path for path in PACKAGE.glob("*.py") if path.name != "__init__.py")


def _declared(module: Path) -> list[str] | None:
    """The names *module*'s ``__all__`` lists, or None when it declares nothing."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target.id], node.value
        else:
            continue
        if "__all__" in targets:
            assert isinstance(value, (ast.List, ast.Tuple)), f"{module.name}: __all__ is not a literal list"
            return [elt.value for elt in value.elts]
    return None


def _names_reached_from(source: str) -> set[str]:
    """The names one consumer module takes out of this package, by either of its names.

    Both spellings count: what a `from funestra.x import a` names directly,
    and what is read off a module bound by `from funestra import x` or
    `import funestra.x` -- the second is how most of the geometry and the
    format helpers are reached.

    A name reached only through a string -- `patch("funestra.x.name")` in
    a consumer's test -- is not counted, on purpose. Reading those would mean matching
    `funestra.x.name` anywhere in the text, which is also how these repos
    *write about* each other in docstrings, and counting a mention as a use is
    the silent failure. Missing a genuine one is the loud failure: the name
    lands in the report with the checkouts that were read named beside it.
    Checked when the gate went in -- the only names spelled that way across the
    three consumers were imported directly as well, or were not ours.
    """
    # Most of a consumer's tree has nothing to do with this package, and parsing
    # it all costs more than the whole rest of this suite.
    if not any(name in source for name in PACKAGE_NAMES):
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    modules, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and is_this_package(node.module):
            if "." in node.module:
                names.update(alias.name for alias in node.names)
            else:
                modules.update((alias.asname or alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if is_this_package(alias.name) and "." in alias.name:
                    modules.add(alias.asname or alias.name.split(".")[-1])
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in modules:
                names.add(node.attr)
    return names


def _renamed_in(module: Path) -> dict[str, str]:
    """The old names *module* still answers to, each with the name it became."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_RENAMED" for target in node.targets):
            return {old.value: new.value for old, new in zip(node.value.keys, node.value.values, strict=True)}
    return {}


def _what_the_consumers_reach() -> tuple[set[str], list[str]]:
    """Every name the sibling checkouts import, and which ones import anything.

    The consumers are found rather than named: a sibling that imports this
    package is one, and nothing here has to know an application's name to say so
    -- which is the rule the package itself is held to.
    """
    reached: set[str] = set()
    consumers = []
    for sibling in _other_repos_beside(ROOT):
        found: set[str] = set()
        for path in _source_files(sibling):
            found |= _names_reached_from(path.read_text(encoding="utf-8", errors="replace"))
        if found:
            reached |= found
            consumers.append(sibling.name)
    return reached, consumers


def _public_definitions(module: Path) -> set[str]:
    """Every module-level name *module* defines without a leading underscore."""
    found: set[str] = set()
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        elif isinstance(node, ast.ImportFrom):
            names = [alias.asname or alias.name for alias in node.names]
        else:
            continue
        found.update(name for name in names if not name.startswith("_"))
    return found


def test_every_module_declares_its_api():
    silent = [module.name for module in _modules() if _declared(module) is None]
    assert not silent, (
        "modules with no __all__ -- declare what the siblings may import, or an "
        "empty list for a package-internal module:\n" + "\n".join(f"  {name}" for name in silent)
    )


def test_a_declaration_names_only_what_the_module_defines():
    wrong = []
    for module in _modules():
        defined = _public_definitions(module)
        wrong.extend(f"{module.name}: {name}" for name in (_declared(module) or ()) if name not in defined)
    assert not wrong, "__all__ names a module does not define:\n" + "\n".join(f"  {w}" for w in wrong)


def test_the_walk_never_enters_a_tree_it_would_throw_away(tmp_path, monkeypatch):
    kept = tmp_path / "pkg" / "kept.py"
    kept.parent.mkdir()
    kept.write_text("", encoding="utf-8")
    for skipped in (".claude", ".venv", "pkg.egg-info"):
        nested = tmp_path / skipped / "deep"
        nested.mkdir(parents=True)
        (nested / "thrown_away.py").write_text("", encoding="utf-8")
    scanned: list[Path] = []
    real_scandir = os.scandir

    def spy(path="."):
        scanned.append(Path(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", spy)

    assert list(_source_files(tmp_path)) == [kept]
    entered = [path.relative_to(tmp_path).parts for path in scanned
               if path.is_relative_to(tmp_path)]
    assert [parts for parts in entered
            if not _NOT_SOURCE.isdisjoint(parts)
            or any(part.endswith(".egg-info") for part in parts)] == []


def test_a_copy_of_this_repo_beside_the_checkout_is_no_consumer(tmp_path):
    """The machine keeps an old-named clone of this repo beside the new one, and
    read as a consumer it made both scans red with this package's own names."""
    for copy in ("funestra", "player_core"):
        (tmp_path / copy / "funestra").mkdir(parents=True)
        (tmp_path / copy / "funestra" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "an_app").mkdir()

    assert [checkout.name for checkout in _other_repos_beside(tmp_path / "funestra")] == ["an_app"]


def test_an_old_name_a_module_still_answers_to_is_read_with_the_name_it_became(tmp_path):
    module = tmp_path / "renamed_module.py"
    module.write_text('_RENAMED = {"old_thing": "new_thing"}\n', encoding="utf-8")

    assert _renamed_in(module) == {"old_thing": "new_thing"}


@pytest.fixture(scope="module")
def reached_and_consumers():
    reached, consumers = _what_the_consumers_reach()
    renamed = {old: new for module in _modules() for old, new in _renamed_in(module).items()}
    reached |= {renamed[name] for name in reached if name in renamed}
    if not consumers:
        pytest.skip(
            "no sibling checkout beside this one imports funestra, so there is "
            "nothing to compare the declared surface against -- this is what a "
            "public clone with nothing beside it looks like"
        )
    return reached, consumers


def test_every_declared_name_has_a_consumer(reached_and_consumers):
    reached, consumers = reached_and_consumers
    for_nobody = []
    for module in _modules():
        for_nobody.extend(f"{module.name}: {name}" for name in (_declared(module) or ())
                          if name not in reached)
    assert not for_nobody, (
        f"declared names no consumer imports (read from: {', '.join(consumers)}). "
        "Each is published for nobody: give it a consumer or take it out of __all__:\n"
        + "\n".join(f"  {name}" for name in for_nobody)
    )


def test_every_name_a_consumer_reaches_is_declared(reached_and_consumers):
    reached, consumers = reached_and_consumers
    declared = {name for module in _modules() for name in (_declared(module) or ())}
    defined = {name for module in _modules() for name in _public_definitions(module)}
    undeclared = sorted((reached & defined) - declared)
    assert not undeclared, (
        f"names a consumer imports that no module declares (read from: {', '.join(consumers)}). "
        "An import a module never meant to offer: declare it in that module's __all__, or "
        "move the consumer off it:\n" + "\n".join(f"  {name}" for name in undeclared)
    )
