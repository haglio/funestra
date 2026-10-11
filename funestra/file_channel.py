"""The file channel, as the Funestras import it.

It lives in :mod:`app_support.file_channel` now: the broker steers by the same
files and is no Funestra, so the calls moved to the one package every repo
installs, and the names of the files themselves are spelled once in
:mod:`app_support.state_files`.  Re-exported here so no Funestra had to change.
"""
from __future__ import annotations

from app_support.file_channel import (
    append_command,
    consume_command_file,
    publish_whole,
    read_paused_state,
)

__all__ = ["append_command", "consume_command_file", "publish_whole", "read_paused_state"]
