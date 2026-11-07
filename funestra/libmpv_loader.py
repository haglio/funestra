from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows gives a packaged app a private copy of AppData that nothing else can see; the Claude app
# every agent's shell runs inside is one, so a copy under AppData would be found by every agent's run
# and by nothing the owner launches. The machine-wide copy lives in the user's own folder instead.
_USER_FOLDER_ID = "{5E6C858F-0E22-4760-9AFE-EA3317B67173}"  # Windows' FOLDERID_Profile


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
    # python-mpv finds the DLL on PATH alone, so os.add_dll_directory would not reach it.
    wanted = [str(d) for d in libmpv_dirs()]
    rest = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p not in wanted]
    os.environ["PATH"] = os.pathsep.join([*wanted, *rest])
