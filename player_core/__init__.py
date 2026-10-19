"""The name this package went by until the Player became the Funestra.

Branches written before then still import ``player_core.<module>``; each such
import reaches the very module :mod:`funestra` holds, so a patch made through
either name lands on both.
"""
from __future__ import annotations

from funestra.renamed import answer_as

__getattr__ = answer_as(__name__)
