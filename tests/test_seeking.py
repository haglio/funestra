from __future__ import annotations

import logging

from funestra.seeking import GIVE_UP_AFTER, OwedSeek, seek_if_taken


class _Engine:
    def __init__(self, *, refusals: int = 0, duration_ms: float = 5_000.0) -> None:
        self.refusals = refusals
        self.duration_ms = duration_ms
        self.seeks: list[float] = []

    def seek_ms(self, ms: float) -> None:
        if self.refusals:
            self.refusals -= 1
            raise SystemError("Error running mpv command", -12)
        self.seeks.append(ms)


class TestASeekMpvMayRefuse:
    def test_a_taken_seek_lands_and_says_so(self):
        engine = _Engine()

        assert seek_if_taken(engine, 1_200.0) is True
        assert engine.seeks == [1_200.0]

    def test_a_refused_seek_lands_nowhere_and_says_so(self):
        engine = _Engine(refusals=1)

        assert seek_if_taken(engine, 1_200.0) is False
        assert engine.seeks == []


class TestASeekOwedToTheFileOnScreen:
    def _pay(self, owed: OwedSeek, engine: _Engine, times: int = 1) -> None:
        for _ in range(times):
            owed.pay(engine, lambda ms: seek_if_taken(engine, ms))

    def test_is_asked_for_each_tick_until_mpv_takes_it(self):
        engine = _Engine(refusals=2)
        owed = OwedSeek()
        owed.owe(900.0)

        self._pay(owed, engine, times=3)

        assert engine.seeks == [900.0]

    def test_once_taken_it_is_not_asked_for_again(self):
        engine = _Engine()
        owed = OwedSeek()
        owed.owe(900.0)

        self._pay(owed, engine, times=3)

        assert engine.seeks == [900.0]

    def test_waits_for_the_file_to_report_a_duration(self):
        engine = _Engine(duration_ms=0.0)
        owed = OwedSeek()
        owed.owe(900.0)

        self._pay(owed, engine)
        engine.duration_ms = 5_000.0
        self._pay(owed, engine)

        assert engine.seeks == [900.0]

    def test_nothing_owed_asks_for_nothing(self):
        engine = _Engine()
        owed = OwedSeek()
        owed.owe(None)

        self._pay(owed, engine)

        assert engine.seeks == []

    def test_is_let_go_with_a_warning_once_mpv_has_refused_it_long_enough(self, caplog):
        engine = _Engine(refusals=GIVE_UP_AFTER + 5)
        owed = OwedSeek()
        owed.owe(900.0)

        with caplog.at_level(logging.WARNING, logger="funestra.seeking"):
            self._pay(owed, engine, times=GIVE_UP_AFTER + 5)

        assert engine.seeks == []
        assert engine.refusals == 5
        assert "never took the seek to 900 ms" in caplog.text
