from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app_support.subprocess_utils import hidden_subprocess_kwargs

_CHECKOUT = Path(__file__).resolve().parents[1]
_GENAUS_OWN = ("funestra.genau", "funestra.genau_engine", "funestra.flick_folder",
               "funestra.flick_list")
_NAME_WHAT_IT_LOADED_OF_GENAUS = (
    "import sys, funestra.program.app, funestra.program.launch; "
    f"print([name for name in {_GENAUS_OWN!r} if name in sys.modules])")


def _where_this_run_finds_its_modules() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": os.pathsep.join([str(_CHECKOUT), *sys.path])}


def test_a_program_launched_without_genau_loads_none_of_genaus_code():
    loaded = subprocess.run(
        [sys._base_executable, "-c", _NAME_WHAT_IT_LOADED_OF_GENAUS], cwd=_CHECKOUT,
        env=_where_this_run_finds_its_modules(), capture_output=True, text=True,
        check=True, **hidden_subprocess_kwargs())

    assert loaded.stdout.splitlines()[-1] == "[]"
