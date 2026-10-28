"""This repo's dead-code gate. The scan it calls is `app_support.dead_code`.

Every caller of this package lives outside it -- its own tests, and the apps
that import it -- so the scan reads them alongside the package, and what it
reports is what nothing anywhere uses. The apps are found beside this checkout
rather than named; a public clone has none beside it, and skips.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from app_support.dead_code import assert_no_dead_code, assert_whitelist_is_live, tracked_python
from app_support.siblings import checkouts_that_import

pytestmark = pytest.mark.repo_check

ROOT = Path(__file__).resolve().parent.parent
SCANNED = (ROOT / "funestra", ROOT / "funestra_core", ROOT / "player_core", ROOT / "tools")
WHITELIST = ROOT / "vulture_whitelist.py"


@pytest.fixture(scope="module")
def callers():
    apps = checkouts_that_import("funestra", "funestra_core", "player_core", near=Path(__file__))
    if not apps:
        pytest.skip("no checkout beside this one imports funestra, so there are no callers to read")
    return [ROOT / "tests", *(path for app in apps for path in tracked_python(app))]


def test_no_dead_code(callers):
    assert_no_dead_code(*SCANNED, whitelist=WHITELIST, callers=callers)


def test_the_whitelist_still_suppresses_what_it_claims_to(callers):
    assert_whitelist_is_live(*SCANNED, whitelist=WHITELIST, callers=callers)
