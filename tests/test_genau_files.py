from __future__ import annotations

import logging

from funestra.file_channel import append_command
from funestra.genau_files import GenauFiles
from funestra.genau_status import GENAU_STATUS_FILENAME

LOG = logging.getLogger(__name__)


def test_the_commands_come_out_once_in_the_case_they_were_written(tmp_path):
    files = GenauFiles(tmp_path / "genau_cmd.txt", tmp_path / "genau_paused.txt")
    append_command(files.command, "PLAY_FILE Made Up.mp4")
    append_command(files.command, "NEXT")

    assert files.commands(LOG) == ["PLAY_FILE Made Up.mp4", "NEXT"]
    assert files.commands(LOG) == []


def test_the_room_is_paused_when_its_file_says_so_and_not_when_there_is_none(tmp_path):
    files = GenauFiles(tmp_path / "genau_cmd.txt", tmp_path / "genau_paused.txt")
    assert files.room_is_paused(LOG) is False

    files.paused.write_text("1", encoding="utf-8")

    assert files.room_is_paused(LOG) is True


def test_with_no_status_file_named_the_status_goes_beside_the_command_file(tmp_path):
    unnamed = GenauFiles(tmp_path / "genau_cmd.txt", tmp_path / "genau_paused.txt")
    named = GenauFiles(tmp_path / "genau_cmd.txt", tmp_path / "genau_paused.txt",
                       status=tmp_path / "elsewhere.txt")

    assert unnamed.status_file == tmp_path / GENAU_STATUS_FILENAME
    assert named.status_file == tmp_path / "elsewhere.txt"
