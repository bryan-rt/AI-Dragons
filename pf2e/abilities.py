"""Ability scores and modifier computation.

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2100)
"""

from __future__ import annotations

from dataclasses import dataclass

from pf2e.types import Ability

_ABILITY_FIELD_MAP: dict[Ability, str] = {
    Ability.STR: "str_",
    Ability.DEX: "dex",
    Ability.CON: "con",
    Ability.INT: "int_",
    Ability.WIS: "wis",
    Ability.CHA: "cha",
}


@dataclass(frozen=True)
class AbilityScores:
    """The six ability scores for a character.

    Stores raw scores (10, 16, 18, etc.). Use mod() to get the modifier.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2100)
    """
    str_: int
    dex: int
    con: int
    int_: int
    wis: int
    cha: int

    def score(self, ability: Ability) -> int:
        """Return the raw score for the given ability."""
        return getattr(self, _ABILITY_FIELD_MAP[ability])

    def mod(self, ability: Ability) -> int:
        """Return the ability modifier: (score - 10) // 2.

        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2100)
        """
        return (self.score(ability) - 10) // 2
