"""The Broker as a HUD's Broker button shows it: whether it is running, and the
press that starts or stops it.

No app imports the Broker, so what one needs to know about it -- the names its
processes run under, the launcher that starts its tray, the file that asks it
to stop -- it publishes in ``broker_contract.json`` beside that launcher.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app_support import osr2_device, state_files
from app_support.file_channel import publish_stamp, stamp_age
from app_support.process_identity import ProcessNamer
from app_support.subprocess_utils import hidden_subprocess_kwargs

logger = logging.getLogger(__name__)

CONTRACT_FILE = "broker_contract.json"
HEARTBEAT_FRESH_S = 3.0
# Inert where the starting process is in no job that permits breakaway, which is
# every launch but an integration run's.
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


@dataclass(frozen=True)
class BrokerContract:
    app_name: str
    package_dir: str
    broker_module: str
    tray_module: str
    tray_launcher: str
    stop_request: str | None = None

    @property
    def image_pattern(self) -> str:
        # The bare interpreters too: naming a process is best-effort.
        return ProcessNamer(self.app_name).process_name_pattern

    @property
    def command_line_pattern(self) -> str:
        return _as_pattern(self.broker_module) + "|" + _as_pattern(self.tray_module)

    @property
    def broker_command_line_pattern(self) -> str:
        # The broker alone: a live tray is not a live broker.
        return _as_pattern(self.broker_module)

    @property
    def launcher_pattern(self) -> str:
        return _as_pattern(self.tray_launcher)


def _as_pattern(literal: str) -> str:
    return literal.replace(".", "\\.")


def read_contract(tray_launcher: Path | str | None) -> BrokerContract | None:
    """The document beside *tray_launcher*, or None with a line in the log."""
    if tray_launcher is None:
        return None
    return _contract_at(Path(tray_launcher).parent / CONTRACT_FILE)


def tray_launcher_in(checkout: Path) -> Path | None:
    contract = _contract_at(checkout / CONTRACT_FILE)
    return None if contract is None else checkout / contract.tray_launcher


def _contract_at(published: Path) -> BrokerContract | None:
    try:
        named = json.loads(published.read_text(encoding="utf-8"))
        return BrokerContract(
            app_name=named["app_name"],
            package_dir=named["package_dir"],
            broker_module=named["broker_module"],
            tray_module=named["tray_module"],
            tray_launcher=named["tray_launcher"],
            stop_request=named.get("stop_request"),
        )
    except (OSError, ValueError, KeyError, TypeError) as refusal:
        logger.error("No broker contract readable at %s (%s)", published, refusal)
        return None


def is_running(state_dir: Path, *, now: float | None = None) -> bool:
    heartbeat = stamp_age(Path(state_dir) / state_files.BROKER_HEARTBEAT, now)
    return ((heartbeat is not None and heartbeat <= HEARTBEAT_FRESH_S)
            or osr2_device.trouble(Path(state_dir), now=now) is osr2_device.Osr2Trouble.NOT_FOUND)


def start(tray_launcher: Path | None) -> None:
    """Start the Broker's tray, which starts the Broker.

    Safe over a live one: the tray holds a single-instance mutex, so the launch
    costs one process that exits at once.
    """
    if not (tray_launcher and Path(tray_launcher).is_file()):
        logger.warning("No broker started: no tray launcher at %s", tray_launcher)
        return
    subprocess.Popen(["wscript.exe", str(tray_launcher)], cwd=Path(tray_launcher).parent,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **launch_kwargs())


def launch_kwargs() -> dict:
    launch = hidden_subprocess_kwargs()
    if sys.platform == "win32":
        launch["creationflags"] = launch.get("creationflags", 0) | CREATE_BREAKAWAY_FROM_JOB
    return launch


def stop(state_dir: Path, tray_launcher: Path | None) -> None:
    contract = read_contract(tray_launcher)
    if contract is None or contract.stop_request is None:
        logger.warning("No broker stopped: the one beside %s names no stop request",
                       tray_launcher)
        return
    publish_stamp(Path(state_dir) / contract.stop_request)


def press(state_dir: Path, tray_launcher: Path | None) -> None:
    if is_running(state_dir):
        stop(state_dir, tray_launcher)
    else:
        start(tray_launcher)
