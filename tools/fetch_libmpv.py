from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

LOCK = Path(__file__).resolve().parent / "libmpv.lock"
LOADER = Path(__file__).resolve().parent.parent / "funestra" / "libmpv_loader.py"

_ASSET = re.compile(r"mpv-dev-lgpl-x86_64-[0-9].*\.7z$")
_DOWNLOAD_TIMEOUT = 300


def _loader_loaded_from_its_file():
    spec = importlib.util.spec_from_file_location(
        "_funestra_libmpv_loader", LOADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dll_path() -> Path:
    return _loader_loaded_from_its_file().machine_libmpv_dir() / "libmpv-2.dll"


def pin_record(dll: Path) -> Path:
    return dll.with_name(dll.name + ".pin")


def fetched_from_the_pin(dll: Path) -> bool:
    record = pin_record(dll)
    return (dll.is_file() and dll.stat().st_size > 0 and record.is_file()
            and record.read_text(encoding="utf-8").strip() == lock()["asset"])


def lock() -> dict[str, str]:
    pinned = {}
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if "=" in line:
            key, value = line.split("=", 1)
            pinned[key.strip()] = value.strip()
    return pinned


def sha256_of(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _releases(repository: str) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases?per_page=15", headers=headers)
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT) as response:
        return json.load(response)


def newest_asset(repository: str) -> tuple[str, str] | None:
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
    subprocess.run(["7z", "x", str(archive), f"-o{into}"], check=True,
                   stdout=subprocess.DEVNULL)
    found = next(into.rglob("libmpv-2.dll"), None)
    if found is None:
        raise SystemExit(f"libmpv-2.dll is not in {archive.name}")
    return found


def put_in_place(found: Path, dll: Path) -> None:
    dll.parent.mkdir(parents=True, exist_ok=True)
    if dll.exists():
        dll.replace(dll.with_name(f"{dll.name}.replaced-{time.time_ns()}"))
    shutil.copy2(found, dll)
    for replaced in dll.parent.glob(f"{dll.name}.replaced-*"):
        with contextlib.suppress(PermissionError):
            replaced.unlink()


def fetch() -> Path:
    pinned = lock()
    url, digest = resolve(pinned)
    dll = dll_path()
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir)
        found = extract(download(url, digest, scratch), scratch)
        put_in_place(found, dll)
    pin_record(dll).write_text(url.rsplit("/", 1)[-1], encoding="utf-8")
    print(f"{dll} <- {url}")
    return dll


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the libmpv build this family runs against, at the pinned version.")
    parser.add_argument("--require", action="store_true",
                        help="exit non-zero unless the DLL is in place afterwards")
    arguments = parser.parse_args()
    dll = dll_path()
    if fetched_from_the_pin(dll):
        print(f"{dll} is already here, from {lock()['asset']}")
    else:
        fetch()
    present = dll.is_file() and dll.stat().st_size > 0
    return 0 if present or not arguments.require else 1


if __name__ == "__main__":
    raise SystemExit(main())
