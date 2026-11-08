from __future__ import annotations

from funestra.video_groups import (
    GroupIndex,
    action_group_items,
    action_label,
    build_group_index,
    normalize_path_key,
    seed_group_items,
    widened_seed_items,
)

SOURCE_IMAGE = {
    "positive_prompt": "two cute dolls, rainbow bedroom",
    "negative_prompt": "tan lines",
    "model": "X Sweet",
    "resolution": "1728x1344",
    "aspect_ratio": "9:7",
    "quality": "Best",
    "seed": "3092817138",
    "style": "Default",
    "creativity": "7",
}


def _i2v(*, action: str, video_seed: str, image_overrides: dict | None = None) -> dict:
    return {
        "video": {"prompt": f"prompt for {action}", "model": "Realism", "action": action,
                  "resolution": "720x560", "aspect_ratio": "9:7", "quality": "720p",
                  "seed": video_seed},
        "source_image": {**SOURCE_IMAGE, **(image_overrides or {})},
    }


def _t2v(action: str, seed: str, prompt: str = "scene") -> dict:
    return {"video": {"prompt": prompt, "action": action, "seed": seed}}


def _paths(records: dict[str, dict]) -> dict[str, str]:
    return {name: f"C:/library/{name}.mp4" for name in records}


def _index(records: dict[str, dict]) -> tuple[GroupIndex, dict[str, str]]:
    paths = _paths(records)
    filed = {path: records[name] for name, path in paths.items()}
    return build_group_index(paths.values(), filed.__getitem__), paths


def test_a_path_is_keyed_whatever_its_case_and_the_space_around_it():
    assert normalize_path_key("  C:/Library/One.MP4 ") == "c:/library/one.mp4"


def test_the_index_groups_by_action_and_seed_and_keeps_a_video_with_no_record():
    index, paths = _index({
        "one_zeta": _i2v(action="Zeta Massage", video_seed="1"),
        "one_alpha": _i2v(action="Alpha", video_seed="2"),
        "two_alpha": _i2v(action="Alpha", video_seed="3", image_overrides={"seed": "999"}),
        "no_record": {},
    })

    one_key = index.entry(paths["one_zeta"]).action_key
    assert sorted(index.action_items[one_key]) == sorted([paths["one_zeta"], paths["one_alpha"]])
    group, seed = index.entry(paths["one_alpha"]).seed_key
    assert set(index.seed_items[group]) == {
        paths["one_zeta"], paths["one_alpha"], paths["two_alpha"]}
    assert seed != index.entry(paths["two_alpha"]).seed_key[1]
    assert index.entry(paths["no_record"]).action_key is None
    assert index.contains(paths["no_record"])
    assert not index.contains("C:/library/new_arrival.mp4")


def test_the_index_holds_one_entry_per_video():
    index, paths = _index({
        "filed": {**_i2v(action="Alpha", video_seed="1"), "watch": {"weight": 4.0}},
        "no_record": {},
    })

    entry = index.entry(paths["filed"])
    assert (entry.path, entry.action, entry.weight, entry.from_image) == (
        paths["filed"], "Alpha", 4.0, True)
    assert entry.action_key is not None
    assert entry.seed_key is not None
    assert entry.scene_tags == frozenset({"two cute dolls", "rainbow bedroom"})
    bare = index.entry(paths["no_record"])
    assert (bare.path, bare.action, bare.weight, bare.from_image, bare.scene_tags) == (
        paths["no_record"], "", 1.0, False, frozenset())
    assert index.entry("C:/never/indexed.mp4").path == ""
    assert index.weight_of(paths["filed"]) == 4.0
    assert index.weight_of(paths["no_record"]) == 1.0


def test_a_video_learned_after_the_build_stands_in_its_groups_as_if_built_in():
    records = {
        "one_zeta": _i2v(action="Zeta Massage", video_seed="1"),
        "one_alpha": _i2v(action="Alpha", video_seed="2"),
        "two_alpha": _i2v(action="Alpha", video_seed="3", image_overrides={"seed": "9"}),
    }
    paths = _paths(records)
    filed = {path: records[name] for name, path in paths.items()}
    index = build_group_index([paths["one_zeta"], paths["two_alpha"]], filed.__getitem__)

    index.learn(paths["one_alpha"], filed.__getitem__)

    assert index == build_group_index(paths.values(), filed.__getitem__)


def test_a_video_already_known_is_not_read_again():
    index, paths = _index({"one": _t2v("Alpha", "1")})

    def never_read(path: str) -> dict:
        raise AssertionError(path)

    index.learn(paths["one"], never_read)

    assert index.act_of(paths["one"]) == "Alpha"


def test_a_forgotten_video_leaves_its_groups():
    index, paths = _index({"one": _t2v("Alpha", "1"), "twirl": _t2v("Twirling", "1")})

    index.forget(paths["twirl"])
    index.forget(paths["twirl"])

    assert not index.contains(paths["twirl"])
    assert action_group_items(index, paths["one"]) == [paths["one"]]


def test_a_known_key_gives_back_the_path_as_it_was_learned():
    index, paths = _index({"One": _t2v("Alpha", "1")})

    assert index.indexed_path(normalize_path_key(paths["One"])) == paths["One"]
    assert index.indexed_path("c:/never/indexed.mp4", "C:/fallback.mp4") == "C:/fallback.mp4"


def test_action_group_items_are_the_same_seeds_other_actions():
    index, paths = _index({
        "one": _t2v("Alpha", "1"),
        "twirl": _t2v("Twirling", "1"),
        "other": _t2v("Alpha", "2"),
    })

    assert sorted(action_group_items(index, paths["one"])) == sorted(
        [paths["one"], paths["twirl"]])
    assert index.act_of(paths["one"]) == "Alpha"
    assert action_group_items(index, "C:/never/indexed.mp4") == []


def test_seed_group_items_are_the_same_action_under_other_seeds():
    index, paths = _index({
        "one_a": _t2v("Alpha", "1"),
        "one_b": _t2v("Alpha", "2"),
        "twirl": _t2v("Twirling", "1"),
    })

    assert sorted(seed_group_items(index, paths["one_a"])) == sorted(
        [paths["one_a"], paths["one_b"]])
    assert seed_group_items(index, "C:/never/indexed.mp4") == []


def test_seed_group_items_pin_the_action_for_a_video_made_from_an_image():
    def i2v(action: str, image_seed: str) -> dict:
        return {"video": {"prompt": f"do {action}", "action": action, "seed": "77"},
                "source_image": {"positive_prompt": "made up", "seed": image_seed}}

    index, paths = _index({
        "one_a": i2v("Alpha", "1"),
        "one_b": i2v("Alpha", "2"),
        "twirl_b": i2v("Twirling", "2"),
    })

    assert sorted(seed_group_items(index, paths["one_a"])) == sorted(
        [paths["one_a"], paths["one_b"]])


def test_widened_seed_items_add_the_most_similar_videos_capped():
    index, paths = _index({
        "cur": _t2v("Alpha", "1", prompt="a, b, c, d"),
        "sister": _t2v("Alpha", "2", prompt="a, b, c, d"),
        "near": _t2v("Alpha", "3", prompt="a, b, c, e"),
        "far": _t2v("Alpha", "4", prompt="x, y, z"),
    })

    assert sorted(widened_seed_items(index, paths["cur"], additions=1)) == sorted(
        [paths["cur"], paths["sister"], paths["near"]])


def test_widened_seed_items_never_leave_the_videos_own_action():
    index, paths = _index({
        "cur": _t2v("Alpha", "1", prompt="a, b, c"),
        "other_action": _t2v("Theta", "2", prompt="a, b, c"),
        "same_action": _t2v("Alpha", "3", prompt="a, x, y"),
    })

    assert widened_seed_items(index, paths["cur"], additions=6) == [
        paths["cur"], paths["same_action"]]


def test_widened_seed_items_come_up_empty_on_a_one_of_a_kind_action():
    index, paths = _index({
        "solo": _t2v("Zeta", "1", prompt="a, b, c"),
        "near": _t2v("Alpha", "2", prompt="a, b, c"),
    })

    assert widened_seed_items(index, paths["solo"], additions=6) == [paths["solo"]]


def test_widened_seed_items_read_one_action_spelled_two_ways_as_one_action():
    index, paths = _index({
        "cur": _t2v("XYZ Alpha", "1", prompt="a, b, c"),
        "other_casing": _t2v("Xyz Alpha", "2", prompt="a, b, c"),
    })

    assert widened_seed_items(index, paths["cur"]) == [paths["cur"], paths["other_casing"]]


def test_widened_seed_items_prefer_their_own_kind_of_making():
    def i2v(action: str, seed: str, prompt: str) -> dict:
        return {"video": {"prompt": f"do {action}", "action": action, "seed": seed},
                "source_image": {"positive_prompt": prompt, "seed": seed}}

    index, paths = _index({
        "cur": i2v("Delta", "1", "a, b, c"),
        "t2v_kin": _t2v("Delta", "2", prompt="a, b, c"),
        "i2v_kin": i2v("Delta", "3", "a, b, d"),
    })

    assert widened_seed_items(index, paths["cur"], additions=1) == [
        paths["cur"], paths["i2v_kin"]]
    assert widened_seed_items(index, paths["t2v_kin"], additions=1)[1:] != []


def test_a_widening_asked_of_a_video_not_among_its_own_seeds_still_leads_with_it():
    index, paths = _index({"bare": {"video": {"action": "Alpha"}},
                           "kin": {"video": {"action": "Alpha"}}})

    assert widened_seed_items(index, paths["bare"], additions=1) == [paths["bare"], paths["kin"]]


def test_action_label_numbers_the_videos_of_one_action_in_a_group():
    index, paths = _index({
        "one": _t2v("Alpha", "1"),
        "two": _t2v("Alpha", "1"),
        "twirl": _t2v("Twirling", "1"),
    })

    assert {action_label(index, paths[name]) for name in ("one", "two")} == {
        "Alpha 1", "Alpha 2"}
    assert action_label(index, paths["twirl"]) == "Twirling"
    assert action_label(index, "C:/never/indexed.mp4") == ""


def test_a_videos_labels_stand_as_its_action_ahead_of_the_sites_word():
    index, paths = _index({"labeled": {"video": {"prompt": "scene", "seed": "1", "action": "Gamma",
                                                 "labels": ["alpha", "beta"]}}})

    assert action_label(index, paths["labeled"]) == "alpha, beta"
