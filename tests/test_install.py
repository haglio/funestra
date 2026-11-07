# pip's plain editable install, setuptools' default mode, lets the repo root win as a namespace
# package, so funestra/__init__.py never runs. The probe runs from a folder outside every repo:
# from a repo root, python puts that folder first on its path and finds the package whatever the
# install did.
from __future__ import annotations

import subprocess
import sys
import tempfile

_PROBE = """
import funestra
from funestra import libmpv_loader
print(funestra.__file__)
print(libmpv_loader.__file__)
"""


def _resolve_from_a_folder_outside_every_repo() -> dict[str, str]:
    with tempfile.TemporaryDirectory() as neutral_cwd:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=neutral_cwd, capture_output=True, text=True, check=False,
        )
    assert result.returncode == 0, (
        f"funestra is not importable from this interpreter:\n{result.stderr}"
    )
    return dict(zip(("funestra", "libmpv_loader"), result.stdout.strip().splitlines(), strict=True))


def test_the_package_is_not_a_namespace_shadow_of_the_repo_root():
    found = _resolve_from_a_folder_outside_every_repo()["funestra"]

    assert found != "None", (
        "funestra resolved to a namespace package (the repo root), so its "
        "__init__.py never runs. Reinstall with:\n"
        "  python -m pip install -e <path-to-funestra> "
        "--config-settings editable_mode=compat"
    )
    assert found.endswith("__init__.py")


def test_the_installed_packages_modules_come_from_that_same_package():
    found = _resolve_from_a_folder_outside_every_repo()

    package_dir = found["funestra"].removesuffix("__init__.py")
    assert found["libmpv_loader"].startswith(package_dir)
