from __future__ import annotations

import os
from pathlib import Path

import pytest
from app_support.file_channel import publish_whole, write_flag

from funestra import written_file
from funestra.written_file import STAMPED_TOO_LATELY_TO_TELL_NS, PausedFlag, WrittenFile


class LongAfterTheFileWasStamped:
    def __init__(self, path: Path) -> None:
        self._path = path

    def __call__(self) -> int:
        return self._path.stat().st_mtime_ns + 10 * STAMPED_TOO_LATELY_TO_TELL_NS


class JustAfterTheFileWasStamped(LongAfterTheFileWasStamped):
    def __call__(self) -> int:
        return self._path.stat().st_mtime_ns + STAMPED_TOO_LATELY_TO_TELL_NS // 2


def _a_file_long_written(tmp_path: Path) -> WrittenFile:
    path = tmp_path / "hud.json"
    return WrittenFile(path, now_ns=LongAfterTheFileWasStamped(path))


def test_a_file_reads_as_perhaps_written_until_it_has_been_read(tmp_path):
    file = _a_file_long_written(tmp_path)
    publish_whole(file.path, "one")

    assert file.may_have_been_written()
    assert file.may_have_been_written()
    file.was_read()

    assert not file.may_have_been_written()


def test_a_second_write_is_told_from_the_first_though_windows_stamped_both_with_one_time(tmp_path):
    file = _a_file_long_written(tmp_path)
    publish_whole(file.path, "one")
    first = file.path.stat()
    file.may_have_been_written()
    file.was_read()

    publish_whole(file.path, "two")
    os.utime(file.path, ns=(first.st_atime_ns, first.st_mtime_ns))

    assert file.may_have_been_written()


def test_a_file_stamped_too_lately_to_tell_two_writes_apart_goes_on_reading_as_perhaps_written(
        tmp_path):
    path = tmp_path / "hud.json"
    file = WrittenFile(path, now_ns=JustAfterTheFileWasStamped(path))
    path.write_text("one", encoding="utf-8")

    file.may_have_been_written()
    file.was_read()

    assert file.may_have_been_written()


def test_a_file_taken_away_reads_as_perhaps_written_once_and_holds_nothing(tmp_path):
    file = _a_file_long_written(tmp_path)
    publish_whole(file.path, "one")
    file.may_have_been_written()
    file.was_read()

    file.path.unlink()

    assert file.may_have_been_written()
    assert not file.holds_something
    file.was_read()
    assert not file.may_have_been_written()


class _CountedReads:
    def __init__(self, monkeypatch) -> None:
        self.paths: list[Path] = []
        real = written_file.read_whole
        monkeypatch.setattr(written_file, "read_whole",
                            lambda path: self.paths.append(path) or real(path))


@pytest.fixture
def reads(monkeypatch) -> list[Path]:
    return _CountedReads(monkeypatch).paths


def _a_flag(tmp_path: Path) -> PausedFlag:
    path = tmp_path / "paused.txt"
    return PausedFlag(path, now_ns=LongAfterTheFileWasStamped(path))


def test_a_paused_flag_is_opened_once_however_many_passes_ask_for_it(tmp_path, reads):
    flag = _a_flag(tmp_path)
    write_flag(tmp_path / "paused.txt", True)

    answers = {flag.read() for _ in range(60)}

    assert (answers, len(reads)) == ({True}, 1)


def test_a_paused_flag_follows_each_write(tmp_path):
    flag = _a_flag(tmp_path)
    heard = [flag.read()]
    for paused in (True, False, True):
        write_flag(tmp_path / "paused.txt", paused)
        heard.append(flag.read())

    assert heard == [False, True, False, True]


def test_a_paused_flag_written_twice_in_place_inside_one_tick_of_the_file_clock_is_followed(
        tmp_path):
    path = tmp_path / "paused.txt"
    flag = PausedFlag(path, now_ns=JustAfterTheFileWasStamped(path))
    path.write_text("0", encoding="utf-8")
    one_stamp = path.stat()
    heard = [flag.read()]

    path.write_text("1", encoding="utf-8")
    os.utime(path, ns=(one_stamp.st_atime_ns, one_stamp.st_mtime_ns))
    heard.append(flag.read())

    assert heard == [False, True]


def test_a_paused_flag_that_could_not_be_opened_keeps_its_answer_and_is_read_again(
        tmp_path, monkeypatch):
    flag = _a_flag(tmp_path)
    write_flag(tmp_path / "paused.txt", True)
    flag.read()
    write_flag(tmp_path / "paused.txt", False)
    real = written_file.read_whole

    def held(_path):
        raise PermissionError("held by its writer")

    monkeypatch.setattr(written_file, "read_whole", held)
    while_held = flag.read()
    monkeypatch.setattr(written_file, "read_whole", real)

    assert (while_held, flag.read()) == (True, False)


def test_no_paused_flag_reads_as_playing(tmp_path):
    assert _a_flag(tmp_path).read() is False
