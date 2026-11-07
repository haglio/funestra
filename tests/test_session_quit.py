from __future__ import annotations

from pathlib import Path

from funestra.session_quit import SESSION_QUIT, quit_gesture


class TestQuitGesture:
    def test_in_a_session_it_asks_the_dashboard_and_this_funestra_stays_so_the_session_comes_down_whole_and_no_window_leaves_a_gap(self, tmp_path: Path):
        cmd_file = tmp_path / "dashboard_cmd.txt"

        assert quit_gesture(cmd_file) is False
        assert cmd_file.read_text(encoding="utf-8").split() == ["quit"]

    def test_the_word_it_asks_in_is_the_dashboards_own_quit(self):
        assert SESSION_QUIT == "quit"

    def test_it_joins_the_queue_rather_than_replacing_it(self, tmp_path: Path):
        cmd_file = tmp_path / "dashboard_cmd.txt"
        cmd_file.write_text("landscape_next\n", encoding="utf-8")

        quit_gesture(cmd_file)

        assert cmd_file.read_text(encoding="utf-8").split() == ["landscape_next", SESSION_QUIT]

    def test_with_no_session_to_ask_the_close_ends_this_funestra(self):
        assert quit_gesture(None) is True
