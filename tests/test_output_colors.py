from __future__ import annotations

import logging
from types import SimpleNamespace

from test_mpv_control import FakeMpv

from funestra import mpv_engine, output_colors
from funestra.mpv_engine import MpvEngine

HDR_TARGET = {"w": 2560, "h": 1440, "gamma": "pq", "primaries": "bt.2020", "sig-peak": 4.93,
              "max-luma": 1000.0}


def an_engine_over(mpv: FakeMpv, monkeypatch) -> MpvEngine:
    monkeypatch.setattr(mpv_engine, "_import_mpv", lambda: SimpleNamespace(MPV=lambda **_: mpv))
    return MpvEngine(4242)


def said(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records
            if record.name == output_colors.__name__ and record.levelno == logging.INFO]


def test_the_engine_logs_what_colors_its_video_output_aims_at_on_which_display(
        monkeypatch, caplog):
    mpv = FakeMpv()
    an_engine_over(mpv, monkeypatch)

    with caplog.at_level(logging.INFO, logger=output_colors.__name__):
        mpv.report("current-vo", "gpu")
        mpv.report("current-gpu-context", "d3d11")
        mpv.report("display-names", ["\\\\.\\DISPLAY1"])
        mpv.report("video-target-params", HDR_TARGET)

    assert said(caplog)[-1] == (
        "Video output gpu on d3d11, display \\\\.\\DISPLAY1: transfer pq, primaries bt.2020, "
        "peak 4.93 (1000 cd/m2)")


def test_the_engine_logs_nothing_until_mpv_has_a_target_for_its_output(monkeypatch, caplog):
    mpv = FakeMpv()
    an_engine_over(mpv, monkeypatch)

    with caplog.at_level(logging.INFO, logger=output_colors.__name__):
        mpv.report("current-vo", "gpu")
        mpv.report("display-names", ["\\\\.\\DISPLAY2"])
        mpv.report("video-target-params", None)

    assert said(caplog) == []


def test_a_resize_that_keeps_the_colors_logs_no_second_line(monkeypatch, caplog):
    mpv = FakeMpv()
    an_engine_over(mpv, monkeypatch)

    with caplog.at_level(logging.INFO, logger=output_colors.__name__):
        mpv.report("video-target-params", HDR_TARGET)
        mpv.report("video-target-params", {**HDR_TARGET, "w": 1280, "h": 720})

    assert len(said(caplog)) == 1


def test_moving_to_another_display_logs_the_colors_again(monkeypatch, caplog):
    mpv = FakeMpv()
    an_engine_over(mpv, monkeypatch)

    with caplog.at_level(logging.INFO, logger=output_colors.__name__):
        mpv.report("display-names", ["\\\\.\\DISPLAY1"])
        mpv.report("video-target-params", HDR_TARGET)
        mpv.report("display-names", ["\\\\.\\DISPLAY2"])
        mpv.report("video-target-params", {**HDR_TARGET, "gamma": "srgb", "primaries": "bt.709",
                                            "sig-peak": 1.0, "max-luma": 203.0})

    assert said(caplog)[1:] == [
        "Video output ? on ?, display \\\\.\\DISPLAY2: transfer pq, primaries bt.2020, "
        "peak 4.93 (1000 cd/m2)",
        "Video output ? on ?, display \\\\.\\DISPLAY2: transfer srgb, primaries bt.709, "
        "peak 1.00 (203 cd/m2)",
    ]


def test_an_on_screen_funestra_renders_sdr_colors_on_any_monitor(monkeypatch):
    asked = {}
    monkeypatch.setattr(mpv_engine, "_import_mpv", lambda: SimpleNamespace(
        MPV=lambda **options: asked.update(options) or FakeMpv()))

    MpvEngine(4242)

    assert (asked["d3d11_output_csp"], asked["target_colorspace_hint"]) == ("srgb", "no")
