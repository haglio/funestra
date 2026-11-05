from __future__ import annotations

from app_support import file_channel as the_familys

from funestra import file_channel


def test_every_name_the_funestras_import_is_app_supports_own_never_a_copy_since_a_copy_once_drifted_into_losing_verbs():
    handed_on = [name for name in vars(file_channel) if not name.startswith("_")]

    assert handed_on
    for name in handed_on:
        assert getattr(file_channel, name) is getattr(the_familys, name), name
