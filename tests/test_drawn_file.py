"""Which file each frame an offscreen engine draws shows, across a switch of file.

mpv opens the next file while the last one's frame is still up, redraws that
frame along the way, and may hand over one last frame of it after the switch
was asked for; it says it has started the new file at about the moment it hands
over that file's first frame, and a host can draw the frame first.  A host that
wraps a frame by its file -- a headset wrapping a VR video round the viewer --
must never show one file's frame as another's.
"""
from __future__ import annotations

from funestra.drawn_file import DrawnFile

WIDE = "C:/videos/wide.mp4"
FLAT = "C:/videos/flat.mp4"
OTHER = "C:/videos/other.mp4"


def _showing(path: str) -> DrawnFile:
    drawn = DrawnFile()
    drawn.asked_for(path)
    drawn.opened(path)
    drawn.started(path)
    return drawn


def test_a_new_frame_of_the_file_on_screen_is_shown_as_that_file():
    drawn = _showing(WIDE)

    assert drawn.drawn(new_frame=True) == WIDE


def test_nothing_drawn_while_the_next_file_opens_is_shown():
    drawn = _showing(WIDE)
    drawn.asked_for(FLAT)

    assert drawn.drawn(new_frame=True) is None
    drawn.opened(FLAT)
    assert drawn.drawn(new_frame=False) is None


def test_the_next_files_frame_drawn_before_its_start_is_heard_goes_out_again_once_it_is():
    drawn = _showing(WIDE)
    drawn.asked_for(FLAT)
    drawn.opened(FLAT)
    assert drawn.drawn(new_frame=True) is None

    drawn.started(FLAT)

    assert drawn.owed
    assert drawn.drawn(new_frame=False) == FLAT


def test_a_last_frame_of_the_old_file_is_not_taken_for_the_next_ones():
    drawn = _showing(WIDE)
    drawn.asked_for(FLAT)
    assert drawn.drawn(new_frame=True) is None

    drawn.opened(FLAT)
    drawn.started(FLAT)

    assert not drawn.owed


def test_a_frame_mpv_announces_is_owed_until_it_is_drawn():
    drawn = _showing(WIDE)

    drawn.announced()
    assert drawn.owed
    drawn.drawn(new_frame=True)

    assert not drawn.owed


def test_a_quick_second_ask_waits_for_its_own_file_and_not_the_one_it_replaced():
    drawn = _showing(WIDE)
    drawn.asked_for(OTHER)
    drawn.asked_for(FLAT)

    drawn.opened(OTHER)
    drawn.started(OTHER)

    assert drawn.drawn(new_frame=True) is None


def test_a_file_mpv_moves_on_to_by_itself_is_shown_as_that_file_once_it_starts():
    drawn = _showing(WIDE)

    drawn.opened(OTHER)
    drawn.started(OTHER)

    assert drawn.drawn(new_frame=True) == OTHER
