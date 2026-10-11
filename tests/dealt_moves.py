from __future__ import annotations

from funestra.ken_burns import Move, pan, zoom_in

DRIFT = pan(1.0, -1.0)
CREEP = zoom_in(0.5, 0.5)


class Deals:
    def __init__(self, *moves: Move, from_rest: Move = CREEP) -> None:
        self.moves = moves
        self.rest_move = from_rest
        self.dealt = 0

    def deal(self) -> Move:
        move = self.moves[min(self.dealt, len(self.moves) - 1)]
        self.dealt += 1
        return move

    def from_rest(self) -> Move:
        return self.rest_move
