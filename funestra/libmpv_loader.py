"""Locate the libmpv DLL so ``import mpv`` can find it.

python-mpv resolves libmpv through the Windows DLL search path (``%PATH%``),
not ``os.add_dll_directory``, so the directory holding ``libmpv-2.dll`` must be
on PATH before ``import mpv``.  The DLL is ~117 MB and is NOT committed; it is
fetched once (see the README).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

__all__: list[str] = []  # package-internal: no sibling reaches anything here

# FOLDERID_Profile: the folder %USERPROFILE% normally names.
_USER_FOLDER_ID = "{5E6C858F-0E22-4760-9AFE-EA3317B67173}"


def user_folder() -> Path:
    if sys.platform != "win32":
        return Path.home()
    # Local, and below the platform check: `ctypes.wintypes` raises on import
    # off Windows, where this function never gets this far.
    import ctypes  # noqa: PLC0415
    import uuid  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    class _Guid(ctypes.Structure):
        _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD),
                    ("data3", wintypes.WORD), ("data4", ctypes.c_ubyte * 8)]

    guid = _Guid.from_buffer_copy(uuid.UUID(_USER_FOLDER_ID).bytes_le)
    found = ctypes.c_wchar_p()
    result = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(found))
    try:
        if result != 0:
            raise OSError(f"Windows would not say where the user's folder is ({result:#x})")
        return Path(found.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(found)


def machine_libmpv_dir() -> Path:
    return user_folder() / ".haglio" / "libmpv"


def libmpv_dirs() -> list[Path]:
    return [Path(__file__).resolve().parent.parent / "vendor", machine_libmpv_dir()]


def add_libmpv_to_path() -> None:
    wanted = [str(d) for d in libmpv_dirs()]
    rest = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p not in wanted]
    os.environ["PATH"] = os.pathsep.join([*wanted, *rest])
