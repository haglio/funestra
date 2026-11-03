from __future__ import annotations

from pathlib import Path

from funestra.funscript import Funscript
from funestra.funscript_jumps import FunscriptJumps
from funestra.modes import MessageLevel

_TWO_RUNS = Funscript(actions=[
    (10000, 0), (10300, 100), (10600, 0),
    (40000, 0), (40300, 100), (40600, 0),
])
_PROMPT = Funscript(actions=[(0, 0), (300, 100), (600, 0), (900, 100)])
_LATE = Funscript(actions=[(60000, 0), (60300, 100), (60600, 0)])


class FakeSession:
    def __init__(self, playlist, *, index: int = 0, funscripts=None) -> None:
        self.playlist = [video for video, _script in playlist]
        self._scripts = dict(playlist)
        self.index = index
        self.position_ms = 0.0
        self.seeks: list[float] = []
        self.loads: list[int] = []
        self._funscripts = funscripts or {}

    def funscript_of(self, video):
        return self._scripts.get(video)

    @property
    def current_funscript(self):
        return self._funscripts.get(self._scripts.get(self.playlist[self.index]))

    def load(self, index: int) -> None:
        self.index = index % len(self.playlist)
        self.loads.append(self.index)
        self.position_ms = 0.0

    def seek_to(self, position_ms: float) -> None:
        self.seeks.append(position_ms)
        self.position_ms = position_ms


class FakeNotices:
    def __init__(self) -> None:
        self.said: list[tuple[str, str]] = []

    def say(self, message: str, *, level: MessageLevel) -> None:
        self.said.append((message, level))


def _jumps(session):
    messages = FakeNotices()
    return FunscriptJumps(session, messages), messages


def _scripted(tmp_path: Path, name: str) -> tuple[Path, Path]:
    return tmp_path / f"{name}.mp4", tmp_path / f"{name}.funscript"


class TestJumpToFunscript:
    def test_a_lull_is_skipped_to_where_the_action_resumes(self, tmp_path):
        video, script = _scripted(tmp_path, "alpha")
        session = FakeSession([(video, script)], funscripts={script: _TWO_RUNS})
        session.position_ms = 25000.0
        jumps, messages = _jumps(session)

        jumps.jump_to_funscript()

        assert session.seeks == [40000]
        assert messages.said == [("funscript jump", MessageLevel.HIGHLIGHT)]

    def test_the_quiet_lead_in_counts_as_a_lull(self, tmp_path):
        video, script = _scripted(tmp_path, "alpha")
        session = FakeSession([(video, script)], funscripts={script: _LATE})
        jumps, _messages = _jumps(session)

        jumps.jump_to_funscript()

        assert session.seeks == [60000]

    def test_nothing_scripted_ahead_says_so_and_stays_put(self, tmp_path):
        video, script = _scripted(tmp_path, "alpha")
        session = FakeSession([(video, script)], funscripts={script: _TWO_RUNS})
        session.position_ms = 50000.0
        jumps, messages = _jumps(session)

        jumps.jump_to_funscript()

        assert session.seeks == []
        assert messages.said == [("no funscripting ahead", MessageLevel.WARNING)]

    def test_an_unscripted_clip_has_nowhere_to_jump(self, tmp_path):
        video = tmp_path / "beta.mp4"
        session = FakeSession([(video, None)])
        jumps, messages = _jumps(session)

        jumps.jump_to_funscript()

        assert session.seeks == []
        assert messages.said == [("no funscripting ahead", MessageLevel.WARNING)]

    def test_it_never_goes_backward_into_the_run_already_playing(self, tmp_path):
        video, script = _scripted(tmp_path, "alpha")
        session = FakeSession([(video, script)], funscripts={script: _TWO_RUNS})
        session.position_ms = 10300.0
        jumps, _messages = _jumps(session)

        jumps.jump_to_funscript()

        assert session.seeks == [40000]


class TestNextFunscripted:
    def test_skips_the_unscripted_clips_between_here_and_the_next_script(self, tmp_path):
        video0, script0 = _scripted(tmp_path, "alpha")
        video1 = tmp_path / "beta.mp4"
        clip2, script2 = _scripted(tmp_path, "gamma")
        session = FakeSession(
            [(video0, script0), (video1, None), (clip2, script2)],
            funscripts={script0: _TWO_RUNS, script2: _LATE},
        )
        jumps, messages = _jumps(session)

        jumps.next_funscripted()

        assert session.loads == [2]
        assert messages.said == [("next funscripted", MessageLevel.HIGHLIGHT)]

    def test_lands_where_the_new_clip_s_action_begins(self, tmp_path):
        video0 = tmp_path / "alpha.mp4"
        video1, script1 = _scripted(tmp_path, "beta")
        session = FakeSession(
            [(video0, None), (video1, script1)], funscripts={script1: _LATE},
        )
        jumps, _messages = _jumps(session)

        jumps.next_funscripted()

        assert session.seeks == [60000]

    def test_a_clip_scripted_from_the_top_is_not_seeked_into(self, tmp_path):
        video0 = tmp_path / "alpha.mp4"
        video1, script1 = _scripted(tmp_path, "beta")
        session = FakeSession(
            [(video0, None), (video1, script1)], funscripts={script1: _PROMPT},
        )
        jumps, _messages = _jumps(session)

        jumps.next_funscripted()

        assert session.loads == [1]
        assert session.seeks == []

    def test_wraps_past_the_end_to_reach_a_script_behind_us(self, tmp_path):
        video0, script0 = _scripted(tmp_path, "alpha")
        video1 = tmp_path / "beta.mp4"
        clip2 = tmp_path / "gamma.mp4"
        session = FakeSession(
            [(video0, script0), (video1, None), (clip2, None)],
            index=1, funscripts={script0: _LATE},
        )
        jumps, _messages = _jumps(session)

        jumps.next_funscripted()

        assert session.loads == [0]

    def test_the_clip_on_screen_is_never_the_answer(self, tmp_path):
        video0 = tmp_path / "alpha.mp4"
        video1, script1 = _scripted(tmp_path, "beta")
        session = FakeSession(
            [(video0, None), (video1, script1)], index=1,
            funscripts={script1: _TWO_RUNS},
        )
        jumps, messages = _jumps(session)

        jumps.next_funscripted()

        assert session.loads == []
        assert session.seeks == []
        assert messages.said == [("no other funscripted video", MessageLevel.WARNING)]

    def test_an_entirely_unscripted_playlist_says_so(self, tmp_path):
        session = FakeSession([
            (tmp_path / "alpha.mp4", None), (tmp_path / "beta.mp4", None),
        ])
        jumps, messages = _jumps(session)

        jumps.next_funscripted()

        assert session.loads == []
        assert messages.said == [("no other funscripted video", MessageLevel.WARNING)]
