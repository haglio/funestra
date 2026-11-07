from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def assert_imports_without(module: str, *forbidden: str) -> None:
    body = "".join(f"import sys\nsys.modules[{name!r}] = None\n" for name in forbidden) + f"import {module}\n"
    run = subprocess.run(
        [sys.executable, "-c", body], capture_output=True, text=True, cwd=ROOT,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(
            filter(None, (str(ROOT), os.environ.get("PYTHONPATH"))))},
        timeout=60, check=False)

    assert run.returncode == 0, run.stderr[-2000:]
