"""Which sound output a Funestra takes when a session names its device.

A session names the device it wants by a fragment of its name ("Pimax") rather
than by an id, because Windows reissues endpoint ids whenever a device is
re-enumerated.  The catch is that a headset's own software installs outputs
that carry the maker's name too -- a wireless streaming driver, most of them --
so the fragment can name two outputs at once, and taking the first one lands
the sound on the one nothing is listening to.  So the output a real device
answers wins over a driver that answers nothing, and the streaming output is
still taken when it is the only one named.
"""
from __future__ import annotations

from typing import NamedTuple

__all__ = ["Output", "pick_output"]

_RENDER_ENDPOINTS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
_DESCRIPTION = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"  # PKEY_Device_DeviceDesc
_ADAPTER = "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"  # what Windows shows in the brackets
_BUS = "{a45c254e-df1c-4efd-8020-67d146a850e0},24"  # PKEY_Device_EnumeratorName
_STATE_MASK = 0x0F  # DEVICE_STATEMASK_ALL: the stored value carries flags above these
_ACTIVE = 0x01  # DEVICE_STATE_ACTIVE
_NO_HARDWARE = "ROOT"  # what Windows enumerates a driver that has no device of its own on


class Output(NamedTuple):
    """One output, as the system names it and as its engine opens it."""

    label: str
    handle: str


class Endpoint(NamedTuple):
    """One of Windows' own render endpoints, read from where it records them."""

    active: bool
    description: str
    adapter: str
    bus: str


def _windows_endpoints():
    # Local: `winreg` does not exist off Windows, and only this function needs it.
    import winreg  # noqa: PLC0415

    def value(key, name):
        try:
            return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _RENDER_ENDPOINTS) as render:
        for index in range(winreg.QueryInfoKey(render)[0]):
            try:
                with winreg.OpenKey(render, winreg.EnumKey(render, index)) as endpoint, \
                        winreg.OpenKey(endpoint, "Properties") as properties:
                    yield Endpoint(
                        active=(value(endpoint, "DeviceState") or 0) & _STATE_MASK == _ACTIVE,
                        description=value(properties, _DESCRIPTION) or "",
                        adapter=value(properties, _ADAPTER) or "",
                        bus=value(properties, _BUS) or "",
                    )
            except OSError:
                continue


def software_outputs(endpoints=None):
    """The names of the live outputs that no real device answers.

    Read from the machine rather than guessed from the name, because "AirLink"
    or "Virtual" in one is a house style, not a rule.  Anywhere the machine
    cannot answer -- another platform, a registry that will not open -- nothing
    is named as software, and a named device is taken as it was before.
    """
    if endpoints is None:
        try:
            endpoints = list(_windows_endpoints())
        except (ImportError, OSError):
            return frozenset()
    return frozenset(
        f"{endpoint.description} ({endpoint.adapter})" for endpoint in endpoints
        if endpoint.active and endpoint.bus.upper() == _NO_HARDWARE
    )


def pick_output(outputs, wanted, *, software=None):
    """The :class:`Output` to play on for a device named *wanted*, or None.

    *wanted* is matched case-insensitively against each output's label and
    handle.  None -- for a blank name, or one no output carries -- leaves the
    caller on the system default, which is what a headset that is off should
    fall back to rather than silence.
    """
    needle = (wanted or "").strip().lower()
    if not needle:
        return None
    if software is None:
        software = software_outputs()
    matches = [output for output in outputs
               if needle in f"{output.label} {output.handle}".lower()]
    real = [output for output in matches if output.label not in software]
    return next(iter(real or matches), None)
