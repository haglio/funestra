from __future__ import annotations

from typing import NamedTuple

_RENDER_ENDPOINTS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
_DESCRIPTION = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
_ADAPTER = "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"  # what Windows shows in the brackets
_BUS = "{a45c254e-df1c-4efd-8020-67d146a850e0},24"
_STATE_MASK = 0x0F
_ACTIVE = 0x01
_NO_HARDWARE = "ROOT"  # what Windows enumerates a driver that has no device of its own on


class Output(NamedTuple):
    label: str
    handle: str


class Endpoint(NamedTuple):

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
    needle = (wanted or "").strip().lower()
    if not needle:
        return None
    if software is None:
        software = software_outputs()
    matches = [output for output in outputs
               if needle in f"{output.label} {output.handle}".lower()]
    real = [output for output in matches if output.label not in software]
    return next(iter(real or matches), None)
