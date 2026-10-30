"""Guard the one way this package can be installed wrong.

Sibling repos sit in a directory that is itself on ``sys.path`` (fun_time's venv
carries a ``shared_ui.pth`` naming ``projects/``), and this repo's directory is
called ``funestra`` — the same name as its package. So ``import funestra`` has
two candidates: the package, and the repo root as an implicit *namespace*
package.

Setuptools' default editable install resolves the top-level name through a
meta-path finder that ``PathFinder`` never reaches, so the namespace shadow
wins: ``funestra/__init__.py`` never executes, and no module under it imports.

``pip install -e ... --config-settings editable_mode=compat`` puts the repo root
on ``sys.path`` instead, and a real package beats a namespace portion, so the
shadow cannot form. This test is what makes a wrong reinstall fail loudly rather
than years later.

The check runs in a subprocess with its working directory outside every repo,
because a run started *from* a repo root finds the package through the cwd and
would pass whatever the install did — which is exactly the false green this
guard exists to avoid.
"""
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


def _resolve_from_outside_any_repo() -> dict[str, str]:
    with tempfile.TemporaryDirectory() as neutral_cwd:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=neutral_cwd, capture_output=True, text=True,
        )
    assert result.returncode == 0, (
        f"funestra is not importable from this interpreter:\n{result.stderr}"
    )
    return dict(zip(("funestra", "libmpv_loader"), result.stdout.strip().splitlines(), strict=True))


def test_the_package_is_not_a_namespace_shadow_of_the_repo_root():
    found = _resolve_from_outside_any_repo()["funestra"]

    assert found != "None", (
        "funestra resolved to a namespace package (the repo root), so its "
        "__init__.py never runs. Reinstall with:\n"
        "  python -m pip install -e <path-to-funestra> "
        "--config-settings editable_mode=compat"
    )
    assert found.endswith("__init__.py")


def test_the_installed_packages_modules_come_from_that_same_package():
    found = _resolve_from_outside_any_repo()

    package_dir = found["funestra"].removesuffix("__init__.py")
    assert found["libmpv_loader"].startswith(package_dir)
