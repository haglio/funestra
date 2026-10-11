"""A boolean two parts of the app share."""
from __future__ import annotations

from funestra.flag import Flag


class TestTheValue:
    def test_it_starts_off_unless_told_otherwise(self):
        assert Flag().on is False
        assert Flag(on=True).on is True

    def test_it_is_moved_by_writing_to_it(self):
        flag = Flag()

        flag.on = True

        assert flag.on is True
