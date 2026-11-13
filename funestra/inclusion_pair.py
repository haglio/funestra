from __future__ import annotations

from dataclasses import dataclass, replace

from funestra.hud_button import Button
from funestra.hud_controls import lit_or_remembered

Included = tuple[bool, bool]
BOTH: Included = (True, True)


@dataclass(frozen=True)
class Kind:
    word: str
    mark: str
    named: str

    def name(self, things: str) -> str:
        return self.named.format(things=things)


@dataclass(frozen=True, eq=False)
class InclusionPair:
    first: Kind
    second: Kind
    commands: dict[Included, str]

    @property
    def asked(self) -> dict[str, Included]:
        return {command: included for included, command in self.commands.items()}

    def buttons(self, included: Included, *, remembered: bool,
                things: str = "videos") -> tuple[Button, Button]:
        first, second = included
        return (
            replace(_inclusion_button(self.commands[(not first, second)], self.first, things,
                                      on=first, remembered=remembered), group_break=True),
            _inclusion_button(self.commands[(first, not second)], self.second, things,
                              on=second, remembered=remembered),
        )

    def flash(self, included: Included) -> str:
        if included == BOTH:
            return f"{self.first.word} + {self.second.word}"
        kept = self._the_one_kept(included)
        return f"{kept.word} only" if kept else ""

    def title_word(self, included: Included) -> str:
        kept = self._the_one_kept(included)
        return kept.word if kept else ""

    def _the_one_kept(self, included: Included) -> Kind | None:
        first, second = included
        if first == second:
            return None
        return self.first if first else self.second


def _inclusion_button(command: str, kind: Kind, things: str, *, on: bool,
                      remembered: bool) -> Button:
    named = kind.name(things)
    tooltip = f"Including {named}" if on else f"Not including {named}"
    return Button(command, kind.mark, tooltip, **lit_or_remembered(on, remembered))


@dataclass(frozen=True)
class Narrowed:
    says: str
    warns: bool = False
    holds_what_is_on_screen: bool = False


def including_no_other(things: str) -> str:
    return f"Including no other {things}"


def answer_to_a_narrowing(says: str, *, nothing_left: bool, things: str) -> Narrowed:
    if nothing_left:
        return Narrowed(including_no_other(things), warns=True, holds_what_is_on_screen=True)
    return Narrowed(says)
