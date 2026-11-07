from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def imports_in_a_child(module: str, *, prelude: str = "", **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", prelude + f"import {module}\n"], capture_output=True, text=True,
        cwd=ROOT, timeout=60, check=False,
        env={**os.environ, **env, "PYTHONPATH": os.pathsep.join(
            filter(None, (str(ROOT), os.environ.get("PYTHONPATH"))))})


def modules_named_in_imports(module: str) -> set[str]:
    return modules_named_in_source(Path(importlib.util.find_spec(module).origin), module.rpartition(".")[0])


def packages_named_in_imports(module: str) -> set[str]:
    return {name.partition(".")[0] for name in modules_named_in_imports(module)}


def modules_named_in_source(source_file: Path, package: str = "") -> set[str]:
    named: set[str] = set()
    for node in ast.walk(ast.parse(source_file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            named |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = (f"{package}.{node.module}" if node.module else package) if node.level else (node.module or "")
            named.add(base)
            named |= {f"{base}.{alias.name}" for alias in node.names}
    return named


def assert_imports_without(module: str, *forbidden: str) -> None:
    assert not any(name == banned or name.startswith(banned + ".")
                   for name in modules_named_in_imports(module) for banned in forbidden)
    blocked = "".join(f"import sys\nsys.modules[{name!r}] = None\n" for name in forbidden)
    run = imports_in_a_child(module, prelude=blocked)

    assert run.returncode == 0, run.stderr[-2000:]
