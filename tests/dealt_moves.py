from __future__ import annotations

from funestra.ken_burns import Move, pan, zoom_in

DRIFT = pan(1.0, -1.0)
CREEP = zoom_in(0.5, 0.5)


class Deals:
    def __init__(self, *moves: Move, from_rest: Move = CREEP, stops: tuple | None = None) -> None:
        self.moves = moves
        self.rest_move = from_rest
        self.dealt = 0
        self.closed_up_on: list[tuple] = []
        self.stops = None if stops is None else list(stops)
        self.offered: list[tuple] = []

    def stop_among(self, places: tuple) -> tuple | None:
        self.offered.append(places)
        if self.stops is None:
            return places[0] if places else None
        return self.stops.pop(0)

    def deal(self) -> Move:
        move = self.moves[min(self.dealt, len(self.moves) - 1)]
        self.dealt += 1
        return move

    def from_rest(self) -> Move:
        return self.rest_move

    def close_up(self, frame, place) -> Move:
        self.closed_up_on.append(place)
        return Move(frame(place), frame(place))
