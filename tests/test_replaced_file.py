from __future__ import annotations

import os
from pathlib import Path

import pytest
from app_support.file_channel import publish_whole, write_flag

from funestra import replaced_file
from funestra.replaced_file import PausedFlag, ReplacedFile


def test_a_file_never_read_reads_as_replaced_until_the_read_is_kept(tmp_path):
    file = ReplacedFile(tmp_path / "hud.json")
    publish_whole(file.path, "one")

    assert file.replaced()
    assert file.replaced()
    file.was_read()

    assert not file.replaced()


def test_a_second_write_reads_as_replaced_though_windows_stamped_both_with_one_time(tmp_path):
    file = ReplacedFile(tmp_path / "hud.json")
    publish_whole(file.path, "one")
    first = file.path.stat()
    file.replaced()
    file.was_read()

    publish_whole(file.path, "two")
    os.utime(file.path, ns=(first.st_atime_ns, first.st_mtime_ns))

    assert file.replaced()


def test_a_file_taken_away_reads_as_replaced_once_and_holds_nothing(tmp_path):
    file = ReplacedFile(tmp_path / "hud.json")
    publish_whole(file.path, "one")
    file.replaced()
    file.was_read()

    file.path.unlink()

    assert file.replaced()
    assert not file.holds_something
    file.was_read()
    assert not file.replaced()


class _CountedReads:
    def __init__(self, monkeypatch) -> None:
        self.paths: list[Path] = []
        real = replaced_file.read_whole
        monkeypatch.setattr(replaced_file, "read_whole",
                            lambda path: self.paths.append(path) or real(path))


@pytest.fixture
def reads(monkeypatch) -> list[Path]:
    return _CountedReads(monkeypatch).paths


def test_a_paused_flag_is_opened_once_however_many_passes_ask_for_it(tmp_path, reads):
    flag = PausedFlag(tmp_path / "paused.txt")
    write_flag(tmp_path / "paused.txt", True)

    answers = {flag.read() for _ in range(60)}

    assert (answers, len(reads)) == ({True}, 1)


def test_a_paused_flag_follows_each_write(tmp_path):
    flag = PausedFlag(tmp_path / "paused.txt")
    heard = [flag.read()]
    for paused in (True, False, True):
        write_flag(tmp_path / "paused.txt", paused)
        heard.append(flag.read())

    assert heard == [False, True, False, True]


def test_a_paused_flag_that_could_not_be_opened_keeps_its_answer_and_is_read_again(
        tmp_path, monkeypatch):
    flag = PausedFlag(tmp_path / "paused.txt")
    write_flag(tmp_path / "paused.txt", True)
    flag.read()
    write_flag(tmp_path / "paused.txt", False)
    real = replaced_file.read_whole

    def held(_path):
        raise PermissionError("held by its writer")

    monkeypatch.setattr(replaced_file, "read_whole", held)
    while_held = flag.read()
    monkeypatch.setattr(replaced_file, "read_whole", real)

    assert (while_held, flag.read()) == (True, False)


def test_no_paused_flag_reads_as_playing(tmp_path):
    assert PausedFlag(tmp_path / "paused.txt").read() is False
