"""The Broker as a HUD's Broker button shows it, and what a press on it does."""
from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from app_support import state_files
from app_support.process_identity import ProcessNamer

from funestra import broker

# A Broker checkout as it publishes itself -- invented, not this machine's, so
# the test says what it depends on rather than inheriting it.
PUBLISHED = {
    "app_name": "Relay",
    "package_dir": "relay_pkg",
    "broker_module": "relay_pkg.app",
    "tray_module": "relay_pkg.tray",
    "tray_launcher": "launch_relay_tray.vbs",
    "stop_request": "relay_stop_request.txt",
}


def _a_broker_checkout(checkout: Path, **published: str | None) -> Path:
    """A checkout publishing PUBLISHED, and the launcher path a host holds."""
    named = {key: value for key, value in {**PUBLISHED, **published}.items() if value is not None}
    checkout.mkdir(parents=True, exist_ok=True)
    (checkout / broker.CONTRACT_FILE).write_text(json.dumps(named), encoding="utf-8")
    launcher = checkout / named["tray_launcher"]
    launcher.write_text("' a launcher", encoding="utf-8")
    return launcher


def _stamped(path: Path, age: float, *, now: float = 1000.0) -> None:
    path.write_text(str(now - age), encoding="utf-8")


class TestTheImagePattern:
    """Built from the published label by the same rule the Broker names by."""

    def test_it_matches_the_names_a_broker_of_that_name_launches_under(self, tmp_path):
        pattern = broker.read_contract(_a_broker_checkout(tmp_path)).image_pattern

        for role in ("Broker", "Tray"):
            name = ProcessNamer(PUBLISHED["app_name"]).exe_name("pythonw.exe", role)
            assert re.match(pattern, name), name

    def test_it_still_matches_a_broker_that_could_not_be_named(self, tmp_path):
        # The copy is best-effort, so a broker can arrive under the plain
        # interpreter and must stay reachable.
        pattern = broker.read_contract(_a_broker_checkout(tmp_path)).image_pattern

        for name in ("pythonw.exe", "python.exe", "py.exe"):
            assert re.match(pattern, name), name

    def test_it_leaves_a_hosts_own_processes_alone(self, tmp_path):
        pattern = broker.read_contract(_a_broker_checkout(tmp_path)).image_pattern

        for name in ("FunTime-MainFunestra.exe", "FunTime-Dashboard.exe", "notepad.exe"):
            assert not re.match(pattern, name), name


class TestReadingTheContract:
    def test_a_launcher_with_no_contract_beside_it_reads_as_nothing(self, tmp_path):
        (tmp_path / "launch_relay_tray.vbs").write_text("' a launcher", encoding="utf-8")

        assert broker.read_contract(tmp_path / "launch_relay_tray.vbs") is None

    def test_no_launcher_at_all_reads_as_nothing(self):
        assert broker.read_contract(None) is None

    def test_a_broker_older_than_its_stop_request_is_still_read(self, tmp_path):
        contract = broker.read_contract(_a_broker_checkout(tmp_path, stop_request=None))

        assert contract.tray_module == PUBLISHED["tray_module"]
        assert contract.stop_request is None

    def test_a_host_that_knows_only_the_checkout_finds_the_launcher_the_broker_names(
            self, tmp_path):
        assert broker.tray_launcher_in(tmp_path) is None

        launcher = _a_broker_checkout(tmp_path)

        assert broker.tray_launcher_in(tmp_path) == launcher


class TestWhetherItIsRunning:
    """Lit while the Broker holds the serial port, which it says every half
    second -- or while it is up looking for an OSR2 that is unplugged."""

    def test_its_heartbeat_counts_as_fresh_up_to_three_seconds_old(self, tmp_path):
        _stamped(tmp_path / state_files.BROKER_HEARTBEAT, 3.0)
        assert broker.is_running(tmp_path, now=1000.0)

        _stamped(tmp_path / state_files.BROKER_HEARTBEAT, 3.1)
        assert not broker.is_running(tmp_path, now=1000.0)

    def test_a_heartbeat_never_written_or_not_a_number_is_not_running(self, tmp_path):
        assert not broker.is_running(tmp_path, now=1000.0)

        (tmp_path / state_files.BROKER_HEARTBEAT).write_text("not a timestamp", encoding="utf-8")
        assert not broker.is_running(tmp_path, now=1000.0)

    def test_a_broker_looking_for_an_unplugged_osr2_is_running(self, tmp_path):
        _stamped(tmp_path / state_files.OSR2_NOT_FOUND, 1.0)

        assert broker.is_running(tmp_path, now=1000.0)


class TestStarting:
    def test_it_starts_the_tray_hidden_and_outside_a_run_s_job_object(self, tmp_path):
        """The tray has to outlive whatever started it, an integration run's job
        object included."""
        launcher = _a_broker_checkout(tmp_path)

        with patch("funestra.broker.subprocess.Popen") as popen:
            broker.start(launcher)

        (argv,), kwargs = popen.call_args
        assert argv == ["wscript.exe", str(launcher)]
        assert kwargs["cwd"] == launcher.parent
        assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["creationflags"] & broker.CREATE_BREAKAWAY_FROM_JOB
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW

    def test_with_no_launcher_nothing_is_started(self, tmp_path):
        with patch("funestra.broker.subprocess.Popen") as popen:
            broker.start(None)
            broker.start(tmp_path / "launch_relay_tray.vbs")

        popen.assert_not_called()

    def test_a_missing_launcher_says_so_rather_than_going_quiet(self, tmp_path, caplog):
        """A host whose launcher is not there gets no Broker, and with no line
        about it that is a silent OSR2 with nothing anywhere to explain it."""
        with caplog.at_level(logging.WARNING, logger="funestra.broker"):
            broker.start(tmp_path / "nowhere" / "launch_relay_tray.vbs")

        assert any("broker" in record.getMessage().lower() for record in caplog.records)


class TestStopping:
    def test_it_asks_the_broker_in_the_file_the_broker_names(self, tmp_path):
        launcher = _a_broker_checkout(tmp_path / "checkout")
        state = tmp_path / "state"
        state.mkdir()

        broker.stop(state, launcher)

        assert (state / PUBLISHED["stop_request"]).is_file()

    def test_a_broker_that_names_no_stop_request_is_left_running(self, tmp_path):
        launcher = _a_broker_checkout(tmp_path / "checkout", stop_request=None)
        state = tmp_path / "state"
        state.mkdir()

        broker.stop(state, launcher)

        assert list(state.iterdir()) == []


class TestThePress:
    """Which way a press on the button goes is what its light says."""

    def test_a_press_on_a_running_broker_stops_it(self, tmp_path):
        launcher = _a_broker_checkout(tmp_path / "checkout")
        state = tmp_path / "state"
        state.mkdir()
        _stamped(state / state_files.BROKER_HEARTBEAT, 0.0, now=time.time())

        with patch("funestra.broker.subprocess.Popen") as popen:
            broker.press(state, launcher)

        popen.assert_not_called()
        assert (state / PUBLISHED["stop_request"]).is_file()

    def test_a_press_on_a_broker_that_is_not_running_starts_it(self, tmp_path):
        launcher = _a_broker_checkout(tmp_path / "checkout")
        state = tmp_path / "state"
        state.mkdir()

        with patch("funestra.broker.subprocess.Popen") as popen:
            broker.press(state, launcher)

        popen.assert_called_once()
        assert not (state / PUBLISHED["stop_request"]).exists()
