from __future__ import annotations

from pathlib import Path

from funestra.funestra import Channels
from funestra.program.cli import build_parser
from funestra.program.launch import PROGRAM_MODULE, Asked, launch_command
from funestra.program.placement import WindowPlacement

_PYTHON = Path("C:/made_up/venv/Scripts/python.exe")
_CHANNELS = Channels(playlist=Path("state/playlist.tsv"), command=Path("state/cmd.txt"),
                     dashboard_cmd=Path("state/asks.txt"), osr2_port=50558)
_PLACEMENT = WindowPlacement(x=-1440, y=0, width=1440, height=2560, title="Made Up Funestra")


def test_the_command_runs_the_funestra_program_on_the_interpreter_it_is_handed():
    command = launch_command(_PYTHON, _CHANNELS, _PLACEMENT)

    assert command[:3] == [str(_PYTHON), "-m", PROGRAM_MODULE]


def test_an_app_with_a_program_of_its_own_names_its_module():
    command = launch_command(_PYTHON, _CHANNELS, _PLACEMENT, module="satellite")

    assert command[:3] == [str(_PYTHON), "-m", "satellite"]


def test_the_program_reads_back_the_channels_and_the_place_the_command_was_built_from():
    args = build_parser().parse_args(launch_command(_PYTHON, _CHANNELS, _PLACEMENT)[3:])

    assert WindowPlacement.from_args(args) == _PLACEMENT
    assert (args.playlist, args.command, args.dashboard_cmd, args.osr2_port) == (
        _CHANNELS.playlist, _CHANNELS.command, _CHANNELS.dashboard_cmd, 50558)
    assert (args.hidden, args.keys, args.ends_with, args.no_audio) == (False, False, None, False)


def test_what_else_the_app_asks_of_the_program_rides_on_the_command():
    asked = Asked(hidden=True, keys=True, ends_with=4321, no_audio=True)

    args = build_parser().parse_args(launch_command(_PYTHON, _CHANNELS, _PLACEMENT, asked)[3:])

    assert (args.hidden, args.keys, args.ends_with, args.no_audio) == (True, True, 4321, True)
