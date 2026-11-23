from __future__ import annotations

import logging
import threading

import pytest
from app_support.threading_utils import wait_until

from funestra import off_the_loop
from funestra.off_the_loop import AtOnce, BehindTheLoop


@pytest.fixture(params=[AtOnce, BehindTheLoop])
def worker(request):
    made = request.param()
    yield made
    made.close()


def test_a_text_published_is_in_its_file_once_the_worker_closes(worker, tmp_path):
    worker.publish(tmp_path / "status.txt", "video=one\n")

    worker.close()

    assert (tmp_path / "status.txt").read_text(encoding="utf-8") == "video=one\n"


def test_commands_asked_reach_the_command_file_in_the_order_asked(worker, tmp_path):
    for command in ("portrait_next", "portrait_lock", "portrait_next"):
        worker.ask(tmp_path / "dashboard_cmd.txt", command)

    worker.close()

    assert (tmp_path / "dashboard_cmd.txt").read_text(encoding="utf-8").split() == [
        "portrait_next", "portrait_lock", "portrait_next"]


def test_what_a_job_made_is_handed_back_when_the_loop_asks_for_what_is_done(worker):
    handed_back: list[int] = []
    worker.do(lambda: 6 * 7, handed_back.append)

    worker.close()
    worker.deliver()

    assert handed_back == [42]


def test_a_job_with_nothing_to_hand_back_is_still_done(worker, tmp_path):
    worker.do((tmp_path / "made").mkdir)

    worker.close()

    assert (tmp_path / "made").is_dir()


class TestBehindTheLoop:
    def test_the_caller_never_does_the_work_itself(self):
        worker = BehindTheLoop()
        ran_on: list[str] = []
        worker.do(lambda: ran_on.append(threading.current_thread().name))

        worker.close()

        assert ran_on == ["funestra-off-the-loop"]

    def test_what_a_job_made_is_handed_back_on_the_thread_that_asks_for_it(self):
        worker = BehindTheLoop()
        handed_back_on: list[str] = []
        worker.do(lambda: None,
                  lambda _made: handed_back_on.append(threading.current_thread().name))
        worker.close()

        worker.deliver()

        assert handed_back_on == [threading.current_thread().name]

    def test_texts_for_one_file_that_pile_up_behind_a_slow_write_are_written_as_the_newest_alone(
            self, tmp_path, monkeypatch):
        worker = BehindTheLoop()
        the_first_write_may_go = threading.Event()
        written: list[str] = []

        def slow(path, text):
            the_first_write_may_go.wait()
            written.append(text)
            return True

        monkeypatch.setattr(off_the_loop, "publish_whole", slow)
        for text in ("one", "two", "three", "four"):
            worker.publish(tmp_path / "status.txt", text)
        the_first_write_may_go.set()

        worker.close()

        assert written[-1] == "four"
        assert len(written) <= 2

    def test_a_job_that_fails_is_logged_and_the_next_one_still_runs(self, tmp_path, caplog):
        caplog.set_level(logging.ERROR, logger="funestra.off_the_loop")
        worker = BehindTheLoop()

        def fails() -> None:
            raise ValueError("made-up failure")

        worker.do(fails)
        worker.publish(tmp_path / "status.txt", "after")
        worker.close()

        assert (tmp_path / "status.txt").read_text(encoding="utf-8") == "after"
        assert [record.getMessage() for record in caplog.records] == [
            "A job handed off a Funestra's loop failed"]

    def test_what_it_follows_is_read_on_a_thread_of_its_own_never_the_loops(self):
        read_on: list[str] = []
        worker = BehindTheLoop()
        take = worker.follow(lambda: read_on.append(threading.current_thread().name))

        wait_until(lambda: read_on)
        take()
        worker.close()

        assert set(read_on) == {"funestra-listening"}

    def test_everything_it_follows_is_read_on_one_thread_in_the_order_it_was_handed(self):
        read: list[str] = []
        worker = BehindTheLoop()
        worker.follow(lambda: read.append("first"))
        worker.follow(lambda: read.append("second"))

        wait_until(lambda: len(read) >= 4)
        worker.close()

        assert read[:4] == ["first", "second", "first", "second"]

    def test_a_read_that_fails_is_logged_and_the_next_one_still_runs(self, caplog):
        caplog.set_level(logging.ERROR, logger="funestra.off_the_loop")
        worker = BehindTheLoop()
        reads = iter([ValueError("made-up failure"), "heard"])

        def read() -> str:
            made = next(reads, None)
            if isinstance(made, Exception):
                raise made
            return made

        take = worker.follow(read)
        taken: list[str] = []
        wait_until(lambda: taken.extend(take()) or taken)
        worker.close()

        assert taken == ["heard"]
        assert [record.getMessage() for record in caplog.records] == [
            "A file a Funestra follows could not be read"]

    def test_closing_stops_following(self):
        before = set(threading.enumerate())
        worker = BehindTheLoop()
        worker.follow(lambda: None)

        worker.close()

        assert set(threading.enumerate()) <= before

    def test_closing_a_worker_that_was_handed_nothing_starts_no_thread(self):
        before = threading.active_count()

        BehindTheLoop().close()

        assert threading.active_count() == before


def test_what_is_heard_is_taken_in_the_order_it_was_heard_and_nothing_heard_is_left_out(worker):
    heard = iter(["one", None, "two", "three"])
    take = worker.follow(lambda: next(heard, None))
    taken: list[str] = []

    wait_until(lambda: taken.extend(take()) or len(taken) >= 3)

    assert taken == ["one", "two", "three"]
