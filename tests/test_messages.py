from __future__ import annotations

from funestra.messages import MessageReader, MessageWriter, SaidMessage, read_message
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


def test_a_message_that_answers_what_was_said_carries_its_mark(tmp_path):
    path = tmp_path / "origenerator_portrait_notice.txt"

    MessageWriter(path, clock=lambda: 5.0).say("Locked", level=MessageLevel.NORMAL, mark="mic")

    assert _read(path) == {"seq": "5.000", "level": "notice", "message": "Locked", "mark": "mic"}


def test_what_it_writes_reads_back_whole(tmp_path):
    path = tmp_path / "origenerator_portrait_notice.txt"

    MessageWriter(path, clock=lambda: 5.0).say("couldn't delete that one", level=MessageLevel.ERROR,
                                              mark="trash")

    assert read_message(path) == SaidMessage(5.0, MessageLevel.ERROR, "couldn't delete that one",
                                             "trash")


def test_a_message_written_before_marks_reads_with_none(tmp_path):
    path = tmp_path / "main_player_notice.txt"
    path.write_text("seq=3\nlevel=warning\nmessage=full video not available\n", encoding="utf-8")

    assert read_message(path) == SaidMessage(3.0, MessageLevel.WARNING, "full video not available")


def test_a_level_it_does_not_know_reads_as_an_ordinary_message(tmp_path):
    path = tmp_path / "main_player_notice.txt"
    path.write_text("seq=3\nlevel=shouting\nmessage=hi\n", encoding="utf-8")

    assert read_message(path).level is MessageLevel.NORMAL


def test_a_missing_file_reads_as_nothing_said(tmp_path):
    assert read_message(tmp_path / "nope.txt") == SaidMessage()


def test_a_malformed_sequence_reads_as_nothing_said(tmp_path):
    path = tmp_path / "main_player_notice.txt"
    path.write_text("seq=nonsense\nmessage=hi\n", encoding="utf-8")

    assert read_message(path) == SaidMessage()


def test_a_message_said_before_the_reader_opened_is_not_new(tmp_path):
    path = tmp_path / "portrait_notice.txt"
    MessageWriter(path, clock=lambda: 500.0).say("stale from last time", level=MessageLevel.NORMAL)

    assert MessageReader(path).take_new() is None


def test_a_new_message_is_taken_once(tmp_path):
    path = tmp_path / "portrait_notice.txt"
    reader = MessageReader(path)
    MessageWriter(path, clock=lambda: 1.0).say("Videos only", level=MessageLevel.NORMAL)

    assert (reader.take_new(), reader.take_new()) == (
        SaidMessage(1.0, MessageLevel.NORMAL, "Videos only"), None)


def test_a_message_older_than_the_last_one_taken_is_not_new(tmp_path):
    path = tmp_path / "portrait_notice.txt"
    reader = MessageReader(path)
    MessageWriter(path, clock=lambda: 2.0).say("F-mode on", level=MessageLevel.NORMAL)
    reader.take_new()
    MessageWriter(path, clock=lambda: 1.0).say("F-mode off", level=MessageLevel.NORMAL)

    assert reader.take_new() is None


def test_an_empty_message_is_taken_as_nothing_to_say(tmp_path):
    path = tmp_path / "portrait_notice.txt"
    reader = MessageReader(path)
    MessageWriter(path, clock=lambda: 1.0).say("", level=MessageLevel.NORMAL)

    assert reader.take_new() is None
