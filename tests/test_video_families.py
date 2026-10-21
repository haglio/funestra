from __future__ import annotations

from funestra.video_families import action_group_key, seed_family, seed_group_key

PICTURE = {
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


def _from_a_picture(*, action: str = "Alpha", video_seed: str = "1", **picture) -> dict:
    return {
        "video": {"prompt": f"the {action} move", "model": "Motion A", "action": action,
                  "resolution": "720x720", "aspect_ratio": "1:1", "quality": "720p",
                  "seed": video_seed},
        "source_image": {**PICTURE, **picture},
    }


def _from_words(*, action: str = "Alpha", seed: str = "7", prompt: str = "a boat on a lake") -> dict:
    return {"video": {"prompt": prompt, "model": "Motion B", "action": action,
                      "resolution": "1280x720", "aspect_ratio": "16:9", "quality": "720p",
                      "seed": seed, "created": "2025-02-02"}}


def test_videos_animated_from_one_picture_are_one_action_group_whatever_they_do():
    assert action_group_key(_from_a_picture(action="Alpha", video_seed="1")) == (
        action_group_key(_from_a_picture(action="Beta", video_seed="2")))
    assert action_group_key(_from_a_picture()) != action_group_key(_from_a_picture(seed="999"))


def test_a_video_made_from_words_is_grouped_by_its_prompt_and_seed_whatever_its_act():
    assert action_group_key(_from_words(action="Alpha")) == action_group_key(_from_words(action="Beta"))
    assert action_group_key(_from_words(seed="7")) != action_group_key(_from_words(seed="8"))
    assert action_group_key(_from_words()) != action_group_key(_from_a_picture())


def test_a_video_whose_record_holds_no_prompt_and_no_picture_joins_no_action_group():
    assert action_group_key({}) is None
    assert action_group_key({"video": {"action": "Alpha", "seed": "1"}}) is None


def test_videos_from_pictures_that_differ_only_by_seed_are_one_seed_family():
    one, two = seed_group_key(_from_a_picture(seed="101")), seed_group_key(
        _from_a_picture(seed="202", action="Beta"))

    assert one[0] == two[0]
    assert one[1] != two[1]
    assert seed_group_key(_from_a_picture(positive_prompt="a harbor"))[0] != one[0]


def test_a_video_made_from_words_keeps_its_act_in_its_seed_family():
    assert seed_group_key(_from_words(seed="7"))[0] == seed_group_key(_from_words(seed="8"))[0]
    assert seed_group_key(_from_words(action="Alpha"))[0] != (
        seed_group_key(_from_words(action="Beta"))[0])


def test_a_record_with_no_seed_or_no_prompt_has_no_seed_to_vary():
    assert seed_group_key({"video": {"prompt": "a boat on a lake"}}) is None
    assert seed_group_key({"video": {"seed": "7", "action": "Alpha"}}) is None
    assert seed_group_key(_from_a_picture(seed="")) is None


def test_the_day_a_picture_or_video_was_made_is_no_part_of_its_family():
    assert seed_family(_from_a_picture(created="2025-12-31")) == seed_family(_from_a_picture())
    assert action_group_key(_from_a_picture(created="2025-12-31")) == (
        action_group_key(_from_a_picture()))
    later = _from_words()
    later["video"]["created"] = "2026-06-06"
    assert seed_family(later) == seed_family(_from_words())


def test_case_and_spacing_never_split_a_family():
    assert seed_family(_from_words(prompt="A  Boat on a lake ")) == seed_family(_from_words())


def test_a_seed_family_is_the_seed_groups_family_and_needs_no_seed():
    assert seed_family(_from_a_picture(seed="303")) == seed_group_key(_from_a_picture())[0]
    assert seed_family(_from_words(seed="")) == seed_group_key(_from_words())[0]


def test_a_record_naming_no_prompt_has_no_seed_family_whatever_its_act():
    assert seed_family({"video": {"action": "Alpha", "duration_seconds": 5}}) is None
    assert seed_family({"video": {"action": "Beta", "seed": "7"}}) is None
    assert seed_family(_from_a_picture(positive_prompt="")) is None
