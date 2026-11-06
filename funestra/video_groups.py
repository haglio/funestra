from __future__ import annotations

from bisect import insort
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app_support import watch_weights

from .video_families import action_group_key, normalized_text, seed_group_key


def normalize_path_key(path: str) -> str:
    return path.strip().lower()


def scene_tags(record: dict) -> frozenset[str]:
    source = record.get("source_image") or {}
    text = source.get("positive_prompt") or (record.get("video") or {}).get("prompt") or ""
    return frozenset(tag for tag in (normalized_text(part) for part in str(text).split(",")) if tag)


def _tag_overlap(one: frozenset[str], other: frozenset[str]) -> float:
    if not one or not other:
        return 0.0
    return len(one & other) / len(one | other)


@dataclass(frozen=True)
class VideoEntry:
    path: str
    action: str = ""
    action_key: str | None = None
    seed_key: tuple[str, str] | None = None
    scene_tags: frozenset[str] = frozenset()
    from_image: bool = False
    weight: float = 1.0


@dataclass(frozen=True)
class GroupIndex:
    entries: dict[str, VideoEntry]
    action_items: dict[str, list[str]]
    seed_items: dict[str, list[str]]

    def entry(self, path: str) -> VideoEntry:
        return self.entries.get(normalize_path_key(path)) or _UNKNOWN_CLIP

    def contains(self, path: str) -> bool:
        return normalize_path_key(path) in self.entries

    def weight_of(self, path: str) -> float:
        return self.entry(path).weight

    def act_of(self, path: str) -> str:
        return self.entry(path).action

    def learn(self, path: str, record_of: Callable[[str], dict]) -> None:
        if self.contains(path):
            return
        entry = _entry_for(path, record_of(path))
        self.entries[normalize_path_key(path)] = entry
        if entry.action_key is not None:
            insort(self.action_items.setdefault(entry.action_key, []), path)
        if entry.seed_key is not None:
            insort(self.seed_items.setdefault(entry.seed_key[0], []), path)

    def forget(self, path: str) -> None:
        key = normalize_path_key(path)
        if self.entries.pop(key, None) is None:
            return
        for items in (*self.action_items.values(), *self.seed_items.values()):
            items[:] = [item for item in items if normalize_path_key(item) != key]

    def indexed_path(self, key: str, fallback: str = "") -> str:
        entry = self.entries.get(key)
        return entry.path if entry is not None else fallback


_UNKNOWN_CLIP = VideoEntry(path="")


def action_group_items(index: GroupIndex, path: str) -> list[str]:
    key = index.entry(path).action_key
    if key is None:
        return []
    return list(index.action_items[key])


def indexed_act(index: GroupIndex, path: str) -> str:
    return normalized_text(index.act_of(path))


def seed_family_items(index: GroupIndex, path: str) -> list[str]:
    seed_key = index.entry(path).seed_key
    if seed_key is None:
        return []
    family, _seed = seed_key
    action = indexed_act(index, path)
    return [
        item
        for item in index.seed_items[family]
        if indexed_act(index, item) == action
    ]


WIDEN_ADDITIONS = 6


def widened_seed_items(
    index: GroupIndex, path: str, additions: int = WIDEN_ADDITIONS
) -> list[str]:
    key = normalize_path_key(path)
    items = list(seed_family_items(index, path))
    if not any(normalize_path_key(item) == key for item in items):
        items.insert(0, index.indexed_path(key, path))
    seen = {normalize_path_key(item) for item in items} | {key}
    action = indexed_act(index, path)
    mine_entry = index.entry(path)
    ranked = sorted(
        (
            (
                other.from_image == mine_entry.from_image,
                _tag_overlap(mine_entry.scene_tags, other.scene_tags),
                other_key,
            )
            for other_key, other in index.entries.items()
            if other_key not in seen and normalized_text(other.action) == action
        ),
        key=lambda scored: (-scored[0], -scored[1], scored[2]),
    )
    items.extend(index.entries[scored[-1]].path for scored in ranked[:max(additions, 0)])
    return items


def action_label(index: GroupIndex, path: str) -> str:
    key = normalize_path_key(path)
    entry = index.entry(path)
    action, group = entry.action, entry.action_key
    if not action or group is None:
        return action
    twins = [
        item
        for item in index.action_items[group]
        if index.act_of(item) == action
    ]
    if len(twins) <= 1:
        return action
    position = next(
        (number for number, item in enumerate(twins) if normalize_path_key(item) == key), 0
    )
    return f"{action} {position + 1}"


def _entry_for(path: str, record: dict) -> VideoEntry:
    return VideoEntry(
        path=path,
        action=str((record.get("video") or {}).get("action") or "").strip(),
        action_key=action_group_key(record),
        seed_key=seed_group_key(record),
        scene_tags=scene_tags(record),
        from_image=bool(record.get("source_image")),
        weight=watch_weights.weight_of(record),
    )


def build_group_index(video_paths: Iterable[str],
                      record_of: Callable[[str], dict]) -> GroupIndex:
    index = GroupIndex(entries={}, action_items={}, seed_items={})
    for path in video_paths:
        index.learn(path, record_of)
    return index
