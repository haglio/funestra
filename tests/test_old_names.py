from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

OLD_PACKAGE_NAMES = pytest.mark.parametrize("old", ["player_core", "funestra_core"])


@OLD_PACKAGE_NAMES
def test_a_module_under_an_old_package_name_is_the_same_module(old):
    reached = importlib.import_module(f"{old}.playlist")

    assert reached is importlib.import_module("funestra.playlist")


@OLD_PACKAGE_NAMES
def test_a_patch_through_an_old_name_reaches_the_module_itself(old, monkeypatch):
    import funestra.status  # noqa: PLC0415

    monkeypatch.setattr(f"{old}.status.parse_status", lambda fields: None)

    assert funestra.status.parse_status({}) is None


@OLD_PACKAGE_NAMES
def test_an_old_package_hands_its_modules_out_as_attributes(old):
    import funestra.pointer  # noqa: PLC0415

    assert importlib.import_module(old).pointer is funestra.pointer


@OLD_PACKAGE_NAMES
def test_a_module_reached_through_an_old_name_keeps_its_own_spec(old):
    module = importlib.import_module(f"{old}.flag")

    assert module.__spec__.name == "funestra.flag"
    assert module.__name__ == "funestra.flag"


@OLD_PACKAGE_NAMES
def test_a_name_that_never_was_a_module_is_missing_under_every_name(old):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"{old}.no_such_module")

    with pytest.raises(AttributeError):
        _ = importlib.import_module(old).no_such_module


@OLD_PACKAGE_NAMES
def test_reaching_a_module_by_an_old_name_first_still_loads_it_once(old):
    probe = (
        f"import {old}.heatmap as old, funestra.heatmap as new, sys;"
        f"print(old is new, sys.modules['{old}.heatmap'] is sys.modules['funestra.heatmap'])"
    )
    result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                            capture_output=True, text=True, check=True)

    assert result.stdout.split() == ["True", "True"]


@OLD_PACKAGE_NAMES
def test_an_old_module_path_under_an_old_package_name_still_answers_to_its_old_names(old):
    old_module = importlib.import_module(f"{old}.mpv_player")

    from funestra.mpv_engine import MpvEngine  # noqa: PLC0415

    assert old_module.MpvPlayer is MpvEngine
