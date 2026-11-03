from __future__ import annotations

import logging
import logging as _logging

import pytest

from funestra.tick_failures import TickFailures


@pytest.fixture
def said(caplog):
    caplog.set_level(logging.DEBUG, logger="test.tick")
    return caplog


def _failures(what: str = "refresh") -> TickFailures:
    return TickFailures(logging.getLogger("test.tick"), what)


def _levels(caplog) -> list[str]:
    return [record.levelname for record in caplog.records]


class TestWhatFailed:
    def test_the_name_it_was_given_is_in_every_line(self):

        records = []

        class _Collect(_logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        logger = _logging.getLogger("test.named")
        logger.setLevel(_logging.DEBUG)
        logger.addHandler(_Collect())
        failures = TickFailures(logger, "controller sync")

        failures.failed(RuntimeError("the runtime would not answer"))
        failures.failed(RuntimeError("the runtime would not answer"))
        failures.worked()

        assert all("controller sync" in line for line in records), records


class TestTheFirstOfAKind:
    def test_it_is_reported_with_its_traceback(self, said):
        failures = _failures()

        failures.failed(RuntimeError("the tick broke"))

        assert _levels(said) == ["ERROR"]
        assert said.records[0].exc_info is not None
        assert "the tick broke" in said.text

    def test_a_second_kind_is_reported_with_its_own(self, said):
        failures = _failures()
        failures.failed(RuntimeError("the tick broke"))

        failures.failed(ValueError("something else"))

        assert _levels(said) == ["ERROR", "ERROR"]
        assert "something else" in said.text

    def test_the_same_class_carrying_a_different_message_is_a_second_kind(self, said):
        failures = _failures()
        failures.failed(OSError("no such file: genau_status.txt"))

        failures.failed(OSError("no such file: genau_drive.txt"))

        assert _levels(said) == ["ERROR", "ERROR"]


class TestTheSameOneAgain:
    def test_it_is_not_reported_again_at_error(self, said):
        failures = _failures()
        failures.failed(RuntimeError("the tick broke"))

        for _ in range(500):
            failures.failed(RuntimeError("the tick broke"))

        assert _levels(said) == ["ERROR"] + ["DEBUG"] * 500

    def test_the_repeats_carry_no_traceback(self, said):
        failures = _failures()
        failures.failed(RuntimeError("the tick broke"))
        failures.failed(RuntimeError("the tick broke"))

        assert said.records[-1].exc_info is None


class TestWhenItStops:
    def test_a_tick_that_works_says_how_many_were_swallowed(self, said):
        failures = _failures()
        failures.failed(RuntimeError("the tick broke"))
        for _ in range(4):
            failures.failed(RuntimeError("the tick broke"))

        failures.worked()

        assert _levels(said)[-1] == "ERROR"
        assert "4" in said.records[-1].getMessage()

    def test_a_single_failure_that_recovers_says_nothing_more(self, said):
        failures = _failures()
        failures.failed(RuntimeError("the tick broke"))

        failures.worked()

        assert _levels(said) == ["ERROR"]

    def test_a_tick_that_works_from_the_start_says_nothing(self, said):
        _failures().worked()

        assert said.records == []

    def test_the_next_failure_after_a_recovery_is_reported_again(self, said):
        failures = _failures()
        failures.failed(RuntimeError("the tick broke"))
        failures.worked()

        failures.failed(RuntimeError("the tick broke"))

        assert _levels(said) == ["ERROR", "ERROR"]

    def test_a_new_kind_arriving_says_how_many_the_old_one_swallowed(self, said):
        failures = _failures()
        failures.failed(RuntimeError("the tick broke"))
        for _ in range(9):
            failures.failed(RuntimeError("the tick broke"))

        failures.failed(ValueError("something else"))

        summary = [r.getMessage() for r in said.records if "9" in r.getMessage()]
        assert summary
