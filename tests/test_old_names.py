from __future__ import annotations

from PIL import Image, ImageDraw

from funestra import (
    console,
    console_hud,
    device_panel,
    hud,
    hud_button,
    hud_marks,
    main_hud,
    main_hud_painter,
    modes,
    notices,
    robot_hand,
    timeline,
    volume,
)


def test_the_old_names_answer_until_the_apps_have_moved():
    assert console.ConsoleModel is console.MainHudModel
    assert console.console_text is console.main_hud_text
    assert console.parse_console is console.parse_main_hud
    assert console.read_console is console.read_main_hud
    assert console_hud.ConsoleHud is console_hud.MainHud
    assert console_hud.ConsolePainter is console_hud.MainHudPainter
    assert hud_marks.SHARED_MARK is hud_marks.SHARED_ICON
    assert hud_marks.shared_mark is hud_marks.shared_icon
    assert hud_marks.shared_mark_name is hud_marks.shared_icon_name
    assert notices.NoticeWriter is notices.MessageWriter
    assert timeline.TIMELINE_HEIGHT is timeline.SCRUBBER_HEIGHT
    assert device_panel.DevicePanel is device_panel.Osr2ControlsHost
    assert hud.draw_mark is hud.draw_icon
    assert modes.NoticeLevel is modes.MessageLevel
    assert robot_hand.set_dials is robot_hand.set_bars
    assert volume.CHIP_H is volume.VOLUME_CONTROL_H
    assert volume.chip_xy is volume.volume_control_xy


def test_a_button_and_a_hud_answer_to_their_old_keywords_until_the_apps_have_moved():
    button = hud_button.Button("go", glyph="Go", tooltip="")
    assert button.glyph == button.icon == "Go"
    model = main_hud.MainHudModel()
    assert main_hud_painter.MainHud(console=model).console is model


def test_drawing_a_button_answers_to_its_old_font_keyword():
    image = Image.new("RGBA", (40, 40))
    font = hud.load_font(10)
    hud.draw_button(image, ImageDraw.Draw(image), (0, 0, 40, 40), hud_button.Button("go", "Go", ""),
                    hovered=False, glyph_font=font, word_font=font)
