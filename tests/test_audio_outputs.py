"""Which sound output a Funestra takes when it is told a device by name."""
from __future__ import annotations

from funestra import audio_outputs
from funestra.audio_outputs import Endpoint, Output, pick_output, software_outputs

HEADSET = "Headphones (Example Headset)"
STREAMING = "Speakers (Example AirLink)"


def named(*labels):
    """The outputs as a mixer that opens a device by the system's own name lists them."""
    return [Output(label, label) for label in labels]


def test_the_output_a_real_device_answers_wins_over_a_software_one_listed_first():
    picked = pick_output(named(STREAMING, HEADSET), "example", software=[STREAMING])

    assert picked.handle == HEADSET


def test_a_software_output_is_still_taken_when_it_is_the_only_one_named():
    picked = pick_output(named(HEADSET, STREAMING), "airlink", software=[STREAMING])

    assert picked.handle == STREAMING


def test_a_name_no_output_carries_picks_none_so_the_system_default_plays():
    assert pick_output(named(HEADSET, STREAMING), "Nowhere", software=[]) is None


def test_the_name_is_matched_whatever_its_case_and_the_space_around_it():
    assert pick_output(named(HEADSET), "  EXAMPLE HEADSET ", software=[]).handle == HEADSET


def test_no_name_picks_none():
    assert pick_output(named(HEADSET), None, software=[]) is None
    assert pick_output(named(HEADSET), "   ", software=[]) is None


def test_an_output_can_be_named_by_what_the_engine_opens_it_by():
    outputs = [Output(HEADSET, "sys/{headset-id}"), Output(STREAMING, "sys/{streaming-id}")]

    assert pick_output(outputs, "{streaming-id}", software=[]).label == STREAMING


def test_unless_told_the_software_outputs_it_asks_the_system(monkeypatch):
    monkeypatch.setattr(audio_outputs, "software_outputs", lambda: frozenset({STREAMING}))

    assert pick_output(named(STREAMING, HEADSET), "example").handle == HEADSET


def test_an_output_no_real_device_answers_is_named_as_software():
    airlink = Endpoint(active=True, description="Speakers", adapter="Example AirLink",
                       bus="ROOT")

    assert software_outputs([airlink]) == {STREAMING}


def test_an_output_on_a_bus_is_not_software():
    headset = Endpoint(active=True, description="Headphones", adapter="Example Headset",
                       bus="USB")

    assert software_outputs([headset]) == set()


def test_a_software_output_that_is_gone_leaves_a_live_device_of_its_name_alone():
    gone = Endpoint(active=False, description="Headphones", adapter="Example Headset",
                    bus="ROOT")
    live = Endpoint(active=True, description="Headphones", adapter="Example Headset",
                    bus="USB")

    assert software_outputs([gone, live]) == set()
