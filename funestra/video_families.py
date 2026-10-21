"""Which of the library's videos belong together, read off their records."""
from __future__ import annotations

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
_PICTURE_FAMILY_FIELDS = tuple(field for field in IMAGE_IDENTITY_FIELDS if field != "seed")
_VIDEO_FAMILY_FIELDS = (*VIDEO_BASE_FIELDS, "action")


def normalized_text(value: object) -> str:
    return " ".join(str(value or "").split()).lower()


def _field_key(prefix: str, block: dict, fields: tuple[str, ...]) -> str:
    return prefix + "|" + "|".join(normalized_text(block.get(field)) for field in fields)


def action_group_key(record: dict) -> str | None:
    picture = record.get("source_image")
    if picture:
        return _field_key("img", picture, IMAGE_IDENTITY_FIELDS)
    video = record.get("video") or {}
    if not video.get("prompt"):
        return None
    return _field_key("t2v", video, (*VIDEO_BASE_FIELDS, "seed"))


def seed_family(record: dict) -> str | None:
    made, prefix, prompt, fields = _what_made(record)
    return _field_key(prefix, made, fields) if made.get(prompt) else None


def seed_group_key(record: dict) -> tuple[str, str] | None:
    made = _what_made(record)[0]
    family = seed_family(record)
    if family is None or not made.get("seed"):
        return None
    return family, normalized_text(made.get("seed"))


def _what_made(record: dict) -> tuple[dict, str, str, tuple[str, ...]]:
    picture = record.get("source_image")
    if picture:
        return picture, "img", "positive_prompt", _PICTURE_FAMILY_FIELDS
    return record.get("video") or {}, "t2v", "prompt", _VIDEO_FAMILY_FIELDS
