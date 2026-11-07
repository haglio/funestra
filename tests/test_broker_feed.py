from __future__ import annotations

import ast
import dataclasses
import logging
import socket
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app_support.threading_utils import wait_until
from funestra_fakes import holds_of_the_lock

from funestra import broker_feed
from funestra.broker_feed import (
    BrokerFeed,
    BrokerSnapshot,
    UdpListener,
    apply_udp_line,
    bind_with_retry,
    snapshot,
    udp_reader,
)


class TestBrokerFeed:
    def test_it_holds_only_the_fields_something_reads(self):
        assert {f.name for f in dataclasses.fields(BrokerFeed)} == {
            "lock", "auto_active", "raw_bpm", "sync_pulse_id",
        }

    def test_default_values(self):
        s = BrokerFeed()
        assert s.auto_active is False
        assert s.raw_bpm is None
        assert s.sync_pulse_id == 0

    def test_has_lock(self):
        s = BrokerFeed()
        assert isinstance(s.lock, threading.Lock)


_MANY_SHORT_WAITS = (0.02,) * 500
_RETRIES_THAT_RUN_OUT_AT_ONCE = (0, 0, 0)


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _send(port: int, msg: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(msg.encode(), ("127.0.0.1", port))


_KNOCK = "SYNC"


def _knock_until_bound(port: int, state: BrokerFeed) -> None:
    def _knocked() -> bool:
        _send(port, _KNOCK)
        return state.sync_pulse_id > 0

    wait_until(_knocked, timeout=10.0, interval=0.02)


def _turned_away(caplog) -> bool:
    return any("bind attempt" in record.getMessage() for record in caplog.records)


def _run_reader(state: BrokerFeed, port: int) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    logger = logging.getLogger("test.udp_reader")
    t = threading.Thread(
        target=udp_reader, args=(UdpListener("127.0.0.1", port, state, stop, logger),), daemon=True)
    t.start()
    _knock_until_bound(port, state)
    return t, stop


class TestActingOnOneLine:
    @staticmethod
    def _applied(line: str, state: BrokerFeed | None = None) -> BrokerFeed:
        state = state if state is not None else BrokerFeed()
        apply_udp_line(state, line, logging.getLogger("test.udp_reader"))
        return state

    def test_auto_1_hands_the_room_to_the_broker(self):
        assert self._applied("AUTO 1").auto_active is True

    def test_auto_0_takes_the_room_back(self):
        state = BrokerFeed(auto_active=True)

        assert self._applied("AUTO 0", state).auto_active is False

    def test_any_other_payload_takes_the_room_back_too_as_the_safe_reading(self):
        state = BrokerFeed(auto_active=True)

        assert self._applied("AUTO yes", state).auto_active is False

    def test_bpm_parsed(self):
        assert self._applied("BPM 120.5").raw_bpm == pytest.approx(120.5)

    def test_an_invalid_bpm_is_a_lost_datagram_so_the_last_one_stands(self):
        state = BrokerFeed(raw_bpm=120.0)

        assert self._applied("BPM notanumber", state).raw_bpm == 120.0

    def test_bpm_invalid_is_said_on_the_log(self, caplog):
        with caplog.at_level("WARNING", logger="test.udp_reader"):
            self._applied("BPM notanumber")

        assert "notanumber" in caplog.text

    def test_sync_increments(self):
        state = BrokerFeed()

        self._applied("SYNC", state)
        self._applied("SYNC", state)

        assert state.sync_pulse_id == 2

    def test_a_lower_case_verb_is_the_same_verb(self):
        assert self._applied("auto 1").auto_active is True

    @pytest.mark.parametrize("line", [
        "SHOW", "HIDE", "BEATS 4", "MOTION twist", "PATTERN 2.5", "UNKNOWN payload",
        "", "   ",
    ])
    def test_a_verb_genau_does_not_act_on_leaves_the_state_where_it_was(self, line):
        state = self._applied(line)

        assert (state.auto_active, state.raw_bpm, state.sync_pulse_id) == (False, None, 0)

    def test_the_knock_only_counts_and_moves_nothing_a_case_asserts_about(self):
        state = self._applied(_KNOCK)

        assert (state.auto_active, state.raw_bpm, state.sync_pulse_id) == (False, None, 1)

    def test_the_state_is_moved_under_its_own_lock(self):
        state = BrokerFeed()
        held = holds_of_the_lock(state)

        apply_udp_line(state, "SYNC", logging.getLogger("test.udp_reader"))

        assert held == ["taken", "given back"]


class TestTheSocketLoop:
    def test_a_datagram_on_the_wire_reaches_the_state(self):
        state = BrokerFeed()
        port = _free_udp_port()
        t, stop = _run_reader(state, port)
        try:
            _send(port, "AUTO 1")
            wait_until(lambda: state.auto_active, timeout=10.0, interval=0.02)
        finally:
            stop.set()
            t.join(timeout=1.0)

        assert state.auto_active is True

    def test_a_quit_ends_an_idle_reader_within_a_time_nobody_feels(self):
        state = BrokerFeed()
        port = _free_udp_port()
        t, stop = _run_reader(state, port)
        stop.set()
        t.join(timeout=1.0)
        assert not t.is_alive()

    def test_the_bind_waits_grow_since_the_session_before_frees_the_port_quickly_or_after_a_slow_teardown(self):
        delays = broker_feed._BIND_RETRY_DELAYS

        assert list(delays) == sorted(set(delays))

    def test_the_retries_are_many_short_waits_so_the_bind_follows_the_port_at_once_however_slow_the_machine(self):
        assert max(_MANY_SHORT_WAITS) <= 0.05
        assert sum(_MANY_SHORT_WAITS) >= 5.0

    def test_a_bind_turned_away_follows_the_port_once_it_is_freed(self, caplog):
        state = BrokerFeed()
        port = _free_udp_port()

        # Windows lets two sockets that both set SO_REUSEADDR share a port, and the reader sets it,
        # so a blocker that set it too would block nothing.
        blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        blocker.bind(("127.0.0.1", port))

        stop = threading.Event()
        logger = logging.getLogger("test.udp_reader")
        t = threading.Thread(
            target=udp_reader,
            args=(UdpListener("127.0.0.1", port, state, stop, logger,
                              _MANY_SHORT_WAITS),),
            daemon=True,
        )
        try:
            with caplog.at_level(logging.WARNING):
                t.start()
                wait_until(lambda: _turned_away(caplog), timeout=10.0)
                blocker.close()

                _knock_until_bound(port, state)
                _send(port, "AUTO 1")
                wait_until(lambda: state.auto_active, timeout=10.0, interval=0.02)
        finally:
            stop.set()
            blocker.close()
            t.join(timeout=2.0)

        assert state.auto_active is True

    def test_a_quit_while_the_port_is_still_held_ends_the_wait_without_binding(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        blocker.bind(("127.0.0.1", 0))
        port = blocker.getsockname()[1]
        stop = threading.Event()
        stop.set()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            bound = bind_with_retry(sock, ("127.0.0.1", port), stop, logging.getLogger("broker_feed_test"), (30.0, 30.0))
        finally:
            sock.close()
            blocker.close()

        assert bound is False

    def test_bind_failure_gives_up_and_says_so_on_the_log(self):
        state = BrokerFeed()
        port = _free_udp_port()

        blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        blocker.bind(("127.0.0.1", port))

        stop = threading.Event()
        logger = MagicMock()
        t = threading.Thread(
            target=udp_reader,
            args=(UdpListener("127.0.0.1", port, state, stop, logger,
                              _RETRIES_THAT_RUN_OUT_AT_ONCE),),
            daemon=True,
        )
        t.start()
        try:
            t.join(timeout=8.0)
            assert not t.is_alive()
            logger.exception.assert_called_once_with("UDP reader failed")
        finally:
            stop.set()
            blocker.close()
            t.join(timeout=2.0)


class TestTheSnapshot:
    def test_it_copies_the_three_fields(self):
        feed = BrokerFeed(auto_active=True, raw_bpm=120.0, sync_pulse_id=7)

        assert snapshot(feed) == BrokerSnapshot(
            auto_active=True, raw_bpm=120.0, sync_pulse_id=7)

    def test_it_copies_them_under_one_hold_of_the_lock_so_a_tick_never_reads_half_of_two_datagrams(
            self):
        feed = BrokerFeed()
        held = holds_of_the_lock(feed)

        snapshot(feed)

        assert held == ["taken", "given back"]


class TestHowTheseTestsWait:
    def test_no_test_here_naps_since_every_wait_is_on_something_the_reader_did(self):
        calls = [node for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
                 if isinstance(node, ast.Call)]

        assert [ast.unparse(call) for call in calls if _is_a_nap(call)] == []


def _is_a_nap(call: ast.Call) -> bool:
    called = getattr(call.func, "attr", getattr(call.func, "id", ""))
    if called == "sleep":
        return True
    return called == "wait" and bool(call.args or [k for k in call.keywords if k.arg == "timeout"])
