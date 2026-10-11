"""The file channel the Funestras import is app_support's, by the same names."""
from __future__ import annotations

from app_support import file_channel as the_familys

from funestra import file_channel


def test_every_name_the_funestras_import_is_app_supports_own():
    # Re-exported, not copied: a second implementation is how the broker's
    # drifted into a read-then-truncate with a gap one verb wide.
    for name in file_channel.__all__:
        assert getattr(file_channel, name) is getattr(the_familys, name), name
