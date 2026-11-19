from __future__ import annotations

from funestra.main_hud import ModeHud
from funestra.pointer import OMNIPAUSE_TOGGLE
from funestra.runs_here import NOBODY, RunsHere


class Runner:
    def __init__(self, answers: str = "", **status: str) -> None:
        self.answers = answers
        self.status = status
        self.commands: list[str] = []
        self.ticks = 0
        self.showing: list[bool] = []
        self.closed = False

    def apply_command(self, command: str) -> bool:
        self.commands.append(command)
        return bool(self.answers) and command.startswith(self.answers)

    def tick(self) -> None:
        self.ticks += 1

    def status_fields(self) -> dict[str, str]:
        return self.status

    def top_block(self) -> ModeHud:
        return ModeHud(video=self.answers)

    def set_showing(self, showing: bool) -> None:
        self.showing.append(showing)

    def close(self) -> None:
        self.closed = True


def _two():
    kino, genau = Runner("KINO_", length_mode="clips"), Runner("GENAU_", flick="alpha")
    return RunsHere({"kino": kino, "genau": genau}), kino, genau


def test_the_first_one_named_has_the_window_and_is_told_so():
    runs, kino, genau = _two()

    assert (runs.showing, runs.front, kino.showing, genau.showing) == ("kino", kino, [True], [])


def test_showing_another_tells_the_one_leaving_and_the_one_arriving():
    runs, kino, genau = _two()

    assert runs.show("genau") is True

    assert (runs.showing, runs.front, kino.showing, genau.showing) == (
        "genau", genau, [True, False], [True])


def test_showing_the_one_already_up_tells_nobody_again():
    runs, kino, _genau = _two()

    assert runs.show("kino") is True

    assert kino.showing == [True]


def test_showing_a_name_nothing_here_answers_to_is_refused():
    runs, kino, _genau = _two()

    assert runs.show("slideshow") is False

    assert (runs.showing, kino.showing) == ("kino", [True])


def test_a_command_goes_down_the_row_until_one_answers_it():
    runs, kino, genau = _two()

    assert runs.apply("KINO_THING") is True
    assert runs.apply("GENAU_THING") is True
    assert runs.apply("NEXT") is False

    assert kino.commands == ["KINO_THING", "GENAU_THING", "NEXT"]
    assert genau.commands == ["GENAU_THING", "NEXT"]


def test_a_press_on_the_item_asks_what_runs_here_to_pause():
    runs, kino, _genau = _two()

    runs.ask_to_pause()

    assert kino.commands == [OMNIPAUSE_TOGGLE]


def test_every_one_takes_its_pass_whoever_has_the_window():
    runs, kino, genau = _two()

    runs.tick()

    assert (kino.ticks, genau.ticks) == (1, 1)


def test_the_status_is_every_one_s_fields_together():
    runs, _kino, _genau = _two()

    assert runs.status_fields() == {"length_mode": "clips", "flick": "alpha"}


def test_closing_closes_every_one():
    runs, kino, genau = _two()

    runs.close()

    assert (kino.closed, genau.closed, runs["genau"]) == (True, True, genau)


def test_a_window_nothing_runs_on_has_a_nobody_that_answers_nothing():
    runs = RunsHere({})

    assert runs.showing == NOBODY
    assert runs.apply("NEXT") is False
    assert runs.status_fields() == {}
    assert runs.front.top_block() == ModeHud()
    assert runs.front.own_frame() is None
    runs.tick()
    runs.close()


class Readying(Runner):
    def __init__(self, answers: str = "") -> None:
        super().__init__(answers)
        self.ready = False

    def ready_to_show(self) -> bool:
        return self.ready


def test_one_not_ready_to_show_takes_the_window_on_the_pass_it_is_ready():
    kino, genau = Runner("KINO_"), Readying("GENAU_")
    runs = RunsHere({"kino": kino, "genau": genau})

    assert runs.show("genau") is True
    runs.tick()
    held = (runs.showing, list(kino.showing), list(genau.showing))
    genau.ready = True
    runs.tick()

    assert held == ("kino", [True], [])
    assert (runs.showing, kino.showing, genau.showing) == ("genau", [True, False], [True])


def test_showing_another_while_one_gets_ready_forgets_the_one_getting_ready():
    kino, genau = Runner("KINO_"), Readying("GENAU_")
    runs = RunsHere({"kino": kino, "genau": genau})

    runs.show("genau")
    runs.show("kino")
    genau.ready = True
    runs.tick()

    assert (runs.showing, genau.showing) == ("kino", [])
