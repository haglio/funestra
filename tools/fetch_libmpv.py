"""Fetch the libmpv build this family runs against, at the pinned version.

    python tools/fetch_libmpv.py            # fetch it if absent
    python tools/fetch_libmpv.py --require  # ...and exit non-zero unless it is there

``libmpv-2.dll`` is ~117 MB, is in no package, and is the engine every player in
the suite stands on.  ``tools/libmpv.lock`` pins which build: the asset's digest
is verified and a mismatch is refused outright.  Upstream keeps about a month of
releases, so a pinned tag eventually stops existing; that case is loud, names the
lock file, and falls back to resolving the newest build.  Standard library only,
so this runs before anything is installed.

It lands in ``%USERPROFILE%\\.haglio\\libmpv``, the one copy every install finds:
an app pins a version of funestra, so its venv holds a copy of the package
beside no ``vendor/`` of its own.  ``funestra.libmpv_loader`` spells the same
path, and ``tests/test_fetch_libmpv.py`` holds the two together.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

LOCK = Path(__file__).resolve().parent / "libmpv.lock"
LOADER = Path(__file__).resolve().parent.parent / "funestra" / "libmpv_loader.py"

_ASSET = re.compile(r"mpv-dev-x86_64-[0-9].*\.7z$")
_DOWNLOAD_TIMEOUT = 300


def _loader():
    """funestra's own loader, read from this checkout by path: it is standard
    library only, and this script runs before anything is installed."""
    spec = importlib.util.spec_from_file_location(
        "_funestra_libmpv_loader", LOADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dll_path() -> Path:
    """Where the DLL goes: the machine-wide copy every install of funestra finds."""
    return _loader().machine_libmpv_dir() / "libmpv-2.dll"


def lock() -> dict[str, str]:
    """The pin, as ``key = value`` lines; ``#`` starts a comment."""
    pinned = {}
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if "=" in line:
            key, value = line.split("=", 1)
            pinned[key.strip()] = value.strip()
    return pinned


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _releases(repository: str) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases?per_page=15", headers=headers)
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT) as response:
        return json.load(response)


def newest_asset(repository: str) -> tuple[str, str] | None:
    """The newest matching asset in *repository*, as (url, sha256 or "")."""
    for release in _releases(repository):
        for asset in release.get("assets", []):
            if _ASSET.search(asset["name"]):
                digest = (asset.get("digest") or "").removeprefix("sha256:")
                return asset["browser_download_url"], digest
    return None


def pinned_asset(pinned: dict[str, str]) -> tuple[str, str]:
    return (f"https://github.com/{pinned['source']}/releases/download/"
            f"{pinned['tag']}/{pinned['asset']}"), pinned["sha256"]


def _reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60).close()
    except OSError:
        return False
    return True


def resolve(pinned: dict[str, str]) -> tuple[str, str]:
    """The asset to fetch and the digest to hold it to, pin first.

    An empty digest means nothing verifies it -- which is what every run did
    before this file, and is reported as the exception it now is.
    """
    url, digest = pinned_asset(pinned)
    if _reachable(url):
        return url, digest
    print(f"::warning::{LOCK.name} pins {pinned['tag']}, which upstream no longer serves; "
          f"taking the newest build instead. Bump the pin.", file=sys.stderr)
    for repository in (pinned["source"], pinned["fallback"]):
        found = newest_asset(repository)
        if found:
            return found
    raise SystemExit("could not resolve any libmpv dev build")


def download(url: str, digest: str, into: Path) -> Path:
    archive = into / url.rsplit("/", 1)[-1]
    urllib.request.urlretrieve(url, archive)
    if digest and sha256_of(archive) != digest:
        raise SystemExit(
            f"{archive.name} does not match the digest {LOCK.name} pins.\n"
            f"  expected {digest}\n  got      {sha256_of(archive)}\n"
            "Upstream rebuilt the tag or the download was tampered with; do not use it.")
    if not digest:
        print(f"::warning::{archive.name} was taken unverified: nothing publishes a digest for it.",
              file=sys.stderr)
    return archive


def extract(archive: Path, into: Path) -> Path:
    """The DLL out of the 7-zip archive, using whichever 7z the machine has."""
    subprocess.run(["7z", "x", str(archive), f"-o{into}"], check=True,
                   stdout=subprocess.DEVNULL)
    found = next(into.rglob("libmpv-2.dll"), None)
    if found is None:
        raise SystemExit(f"libmpv-2.dll is not in {archive.name}")
    return found


def fetch() -> Path:
    """Put the pinned DLL in its machine-wide home, and say which build it is."""
    pinned = lock()
    url, digest = resolve(pinned)
    dll = dll_path()
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir)
        found = extract(download(url, digest, scratch), scratch)
        dll.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found, dll)
    print(f"{dll} <- {url}")
    return dll


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--require", action="store_true",
                        help="exit non-zero unless the DLL is in place afterwards")
    arguments = parser.parse_args()
    dll = dll_path()
    if dll.is_file() and dll.stat().st_size > 0:
        print(f"{dll} is already here ({dll.stat().st_size} bytes)")
    else:
        fetch()
    present = dll.is_file() and dll.stat().st_size > 0
    return 0 if present or not arguments.require else 1


if __name__ == "__main__":
    raise SystemExit(main())
