from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_WIN32_CTYPES_NAMES = (
    "windll", "oledll", "WinDLL", "OleDLL", "WINFUNCTYPE", "HRESULT",
    "get_last_error", "set_last_error",
)

MODULES = tuple(f"funestra.{path.stem}" for path in sorted((ROOT / "funestra").glob("*.py"))
                if path.stem not in ("__init__", "__main__"))


@pytest.mark.parametrize("module", MODULES)
def test_a_module_imports_where_ctypes_has_no_windows_half_as_fun_time_s_own_check_imports_every_one_of_them(module):
    body = (f"import ctypes, ctypes.wintypes\n"
            f"for name in {_WIN32_CTYPES_NAMES!r}:\n"
            f"    if hasattr(ctypes, name):\n"
            f"        delattr(ctypes, name)\n"
            f"import {module}\n")
    run = subprocess.run([sys.executable, "-c", body], capture_output=True, text=True, cwd=ROOT,
                         env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                              "PYTHONPATH": os.pathsep.join(filter(None, (str(ROOT), os.environ.get("PYTHONPATH"))))},
                         timeout=60, check=False)

    assert run.returncode == 0, run.stderr[-2000:]
