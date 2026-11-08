from __future__ import annotations

from collections.abc import Iterable

from app_support.video_action import ACTION_KEY, VIDEO_BLOCK, labels_of

IMAGE_IDENTITY_FIELDS = (
    "positive_prompt",
    "negative_prompt",
    "model",
    "resolution",
    "aspect_ratio",
    "quality",
    "style",
    "creativity",
    "seed",
)
VIDEO_BASE_FIELDS = (
    "prompt",
    "model",
    "resolution",
    "aspect_ratio",
    "quality",
)
_IMAGE_SEED_GROUP_FIELDS = tuple(field for field in IMAGE_IDENTITY_FIELDS if field != "seed")
_VIDEO_SEED_GROUP_FIELDS = (*VIDEO_BASE_FIELDS, "action")
FRAME_OF_VIDEO = "frame_of_video"


def normalized_text(value: object) -> str:
    return " ".join(str(value or "").split()).lower()


def labels_text(labels: Iterable[str]) -> str:
    return ", ".join(labels)


def actions_text(record: dict) -> str:
    return (labels_text(labels_of(record))
            or str((record.get(VIDEO_BLOCK) or {}).get(ACTION_KEY) or "").strip())


def filter_keeps(text: object, query: object) -> bool:
    return normalized_text(query) in normalized_text(text)


def _field_key(prefix: str, block: dict, fields: tuple[str, ...]) -> str:
    return prefix + "|" + "|".join(normalized_text(block.get(field)) for field in fields)


def action_group_key(record: dict) -> str | None:
    image = record.get("source_image")
    if not image:
        return _key_of_words(record.get("video") or {})
    frame_of = image.get(FRAME_OF_VIDEO)
    return _key_of_words(frame_of) if frame_of else _field_key("img", image, IMAGE_IDENTITY_FIELDS)


def _key_of_words(video: dict) -> str | None:
    if not video.get("prompt"):
        return None
    return _field_key("t2v", video, (*VIDEO_BASE_FIELDS, "seed"))


def seed_group(record: dict) -> str | None:
    made, prefix, prompt, fields = _what_made(record)
    return _field_key(prefix, made, fields) if made.get(prompt) else None


def seed_group_and_seed(record: dict) -> tuple[str, str] | None:
    made = _what_made(record)[0]
    group = seed_group(record)
    if group is None or not made.get("seed"):
        return None
    return group, normalized_text(made.get("seed"))


def _what_made(record: dict) -> tuple[dict, str, str, tuple[str, ...]]:
    image = record.get("source_image")
    if image:
        return image, "img", "positive_prompt", _IMAGE_SEED_GROUP_FIELDS
    return record.get("video") or {}, "t2v", "prompt", _VIDEO_SEED_GROUP_FIELDS


seed_family = seed_group
seed_group_key = seed_group_and_seed
