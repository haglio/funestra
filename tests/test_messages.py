from __future__ import annotations

from funestra.messages import MessageWriter
from funestra.modes import MessageLevel


def _read(path):
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def test_the_record_it_writes_is_what_fun_time_parses(tmp_path):
    path = tmp_path / "main_player_notice.txt"

    MessageWriter(path, clock=lambda: 1234.5).say("no full video", level=MessageLevel.NORMAL)

    written = path.read_text(encoding="utf-8")
    assert written.splitlines() == [
        "seq=1234.500", "level=notice", "message=no full video"]
    assert written.endswith("\n"), "the last record is terminated like the others"


def test_say_publishes_the_message_and_level(tmp_path):
    path = tmp_path / "state" / "main_player_notice.txt"

    MessageWriter(path, clock=lambda: 10.0).say("full video not available", level=MessageLevel.WARNING)

    assert _read(path) == {"seq": "10.000", "level": "warning",
                           "message": "full video not available"}


def test_each_say_advances_the_sequence(tmp_path):
    path = tmp_path / "main_player_notice.txt"
    ticks = iter([10.0, 20.0])
    writer = MessageWriter(path, clock=lambda: next(ticks))
    writer.say("first", level=MessageLevel.NORMAL)
    writer.say("second", level=MessageLevel.NORMAL)

    assert _read(path) == {"seq": "20.000", "level": "notice", "message": "second"}


def test_a_restarted_writer_still_reads_as_newer(tmp_path):
    path = tmp_path / "main_player_notice.txt"
    MessageWriter(path, clock=lambda: 100.0).say("before the restart", level=MessageLevel.NORMAL)
    MessageWriter(path, clock=lambda: 101.0).say("after the restart", level=MessageLevel.NORMAL)

    assert float(_read(path)["seq"]) > 100.0


def test_without_a_path_it_is_inert(tmp_path):
    MessageWriter(None).say("nothing doing", level=MessageLevel.NORMAL)

    assert list(tmp_path.iterdir()) == []
