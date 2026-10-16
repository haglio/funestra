"""Getting to the scripted parts of what a Funestra plays: past this clip's
lull, or on to the next clip in its list that has scripting at all."""
from __future__ import annotations

import logging

from .modes import NoticeLevel

__all__: list[str] = []

logger = logging.getLogger(__name__)


class FunscriptJumps:
    def __init__(self, playback, notices) -> None:
        self._playback = playback
        self._notices = notices

    def jump_to_funscript(self) -> None:
        funscript = self._playback.current_funscript
        target = (
            None if funscript is None
            else funscript.next_active_ms(int(self._playback.position_ms))
        )
        if target is None:
            self._notices.say("no funscripting ahead", level=NoticeLevel.WARNING)
            return
        self._playback.seek_to(target)
        self._notices.say("funscript jump", level=NoticeLevel.HIGHLIGHT)

    def next_funscripted(self) -> None:
        entry = self._next_funscripted_entry()
        if entry is None:
            self._notices.say("no other funscripted video", level=NoticeLevel.WARNING)
            return
        index, clip = entry
        self._playback.load(index)
        funscript = self._playback.current_funscript
        onset = None if funscript is None else funscript.first_real_event_ms
        if onset is not None:
            self._playback.seek_to(onset)
        logger.info("Next funscripted: %s", clip.name)
        self._notices.say("next funscripted", level=NoticeLevel.HIGHLIGHT)

    def _next_funscripted_entry(self):
        playlist = self._playback.playlist
        current = self._playback.index
        for offset in range(1, len(playlist) + 1):
            index = (current + offset) % len(playlist)
            clip = playlist[index]
            if self._playback.funscript_of(clip) is not None and index != current:
                return index, clip
        return None
