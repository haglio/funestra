from __future__ import annotations

from funestra import satellite_hud, video_families
from funestra.video_families import (
    FRAME_OF_VIDEO,
    action_group_key,
    actions_line,
    actions_text,
    filter_keeps,
    seed_group,
    seed_group_and_seed,
)

IMAGE = {
    "positive_prompt": "a lighthouse at dusk",
    "negative_prompt": "fog",
    "model": "Model A",
    "resolution": "1024x1024",
    "aspect_ratio": "1:1",
    "quality": "High",
    "style": "Style A",
    "creativity": "5",
    "seed": "101",
    "created": "2025-01-01",
}


def _from_an_image(*, action: str = "Alpha", video_seed: str = "1", **image) -> dict:
    return {
        "video": {"prompt": f"the {action} move", "model": "Motion A", "action": action,
                  "resolution": "720x720", "aspect_ratio": "1:1", "quality": "720p",
                  "seed": video_seed},
        "source_image": {**IMAGE, **image},
    }


def _from_words(*, action: str = "Alpha", seed: str = "7", prompt: str = "a boat on a lake") -> dict:
    return {"video": {"prompt": prompt, "model": "Motion B", "action": action,
                      "resolution": "1280x720", "aspect_ratio": "16:9", "quality": "720p",
                      "seed": seed, "created": "2025-02-02"}}


def test_videos_animated_from_one_image_are_one_action_group_whatever_they_do():
    assert action_group_key(_from_an_image(action="Alpha", video_seed="1")) == (
        action_group_key(_from_an_image(action="Beta", video_seed="2")))
    assert action_group_key(_from_an_image()) != action_group_key(_from_an_image(seed="999"))


def test_a_video_made_from_words_is_grouped_by_its_prompt_and_seed_whatever_its_act():
    assert action_group_key(_from_words(action="Alpha")) == action_group_key(_from_words(action="Beta"))
    assert action_group_key(_from_words(seed="7")) != action_group_key(_from_words(seed="8"))
    assert action_group_key(_from_words()) != action_group_key(_from_an_image())


def test_a_video_whose_record_holds_no_prompt_and_no_image_joins_no_action_group():
    assert action_group_key({}) is None
    assert action_group_key({"video": {"action": "Alpha", "seed": "1"}}) is None


def test_videos_from_images_that_differ_only_by_seed_are_one_seed_group():
    one, two = seed_group_and_seed(_from_an_image(seed="101")), seed_group_and_seed(
        _from_an_image(seed="202", action="Beta"))

    assert one[0] == two[0]
    assert one[1] != two[1]
    assert seed_group_and_seed(_from_an_image(positive_prompt="a harbor"))[0] != one[0]


def test_a_video_made_from_words_keeps_its_act_in_its_seed_group():
    assert seed_group_and_seed(_from_words(seed="7"))[0] == seed_group_and_seed(_from_words(seed="8"))[0]
    assert seed_group_and_seed(_from_words(action="Alpha"))[0] != (
        seed_group_and_seed(_from_words(action="Beta"))[0])


def test_a_record_with_no_seed_or_no_prompt_has_no_seed_to_vary():
    assert seed_group_and_seed({"video": {"prompt": "a boat on a lake"}}) is None
    assert seed_group_and_seed({"video": {"seed": "7", "action": "Alpha"}}) is None
    assert seed_group_and_seed(_from_an_image(seed="")) is None


def test_the_day_an_image_or_video_was_made_is_no_part_of_its_groups():
    assert seed_group(_from_an_image(created="2025-12-31")) == seed_group(_from_an_image())
    assert action_group_key(_from_an_image(created="2025-12-31")) == (
        action_group_key(_from_an_image()))
    later = _from_words()
    later["video"]["created"] = "2026-06-06"
    assert seed_group(later) == seed_group(_from_words())


def test_case_and_spacing_never_split_a_group():
    assert seed_group(_from_words(prompt="A  Boat on a lake ")) == seed_group(_from_words())


def test_a_seed_group_is_shared_by_every_seed_and_needs_no_seed():
    assert seed_group(_from_an_image(seed="303")) == seed_group_and_seed(_from_an_image())[0]
    assert seed_group(_from_words(seed="")) == seed_group_and_seed(_from_words())[0]


def test_a_record_naming_no_prompt_has_no_seed_group_whatever_its_act():
    assert seed_group({"video": {"action": "Alpha", "duration_seconds": 5}}) is None
    assert seed_group({"video": {"action": "Beta", "seed": "7"}}) is None
    assert seed_group(_from_an_image(positive_prompt="")) is None


def test_the_filter_keeps_text_holding_the_query_whatever_its_case_and_spacing():
    assert filter_keeps("Alpha,  Theta Motion", "alpha")
    assert filter_keeps("Beta Gamma", " BETA   gamma ")


def test_the_filter_keeps_a_query_only_in_the_order_it_was_said():
    assert not filter_keeps("Beta Gamma", "gamma beta")


def test_an_empty_filter_keeps_everything_even_text_with_no_act():
    assert filter_keeps(None, "")
    assert filter_keeps("Alpha", "   ")


def test_a_filter_keeps_nothing_where_no_act_was_recorded():
    assert not filter_keeps(None, "alpha")


def _from_a_videos_starting_frame(**video):
    return {"video": {"prompt": "made from the frame"},
            "source_image": {"positive_prompt": "the frame's own words", "seed": "3",
                             FRAME_OF_VIDEO: _from_words(**video)["video"]}}


def test_a_video_from_a_t2v_videos_starting_frame_shares_that_videos_action_group():
    assert action_group_key(_from_a_videos_starting_frame()) == action_group_key(_from_words())
    assert action_group_key(_from_a_videos_starting_frame(seed="8")) != (
        action_group_key(_from_words()))


def test_a_video_from_a_t2v_videos_starting_frame_keeps_its_seed_group():
    made = _from_a_videos_starting_frame()
    assert seed_group(made) == seed_group(
        {"video": made["video"], "source_image": {"positive_prompt": "the frame's own words"}})


def test_a_records_actions_read_as_its_labels_joined_and_never_the_sites_word():
    assert [actions_text(record) for record in (
        {"video": {"action": "Gamma", "labels": ["alpha", "XYZ"]}},
        {"video": {"action": " Gamma "}},
        {},
    )] == ["alpha, XYZ", "", ""]


def test_a_list_of_labels_reads_as_one_line_in_the_order_given():
    assert actions_line(("beta", "alpha", "XYZ")) == "beta, alpha, XYZ"


def test_the_old_names_for_a_line_of_actions_and_its_filter_answer_until_no_app_spells_them():
    assert video_families.labels_text is video_families.actions_line
    assert satellite_hud.label_is_filtered is satellite_hud.actions_are_filtered
