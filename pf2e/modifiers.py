"""Modifier assembly — BonusTracker and stacking rules.

PF2e stacking rules (AoN: https://2e.aonprd.com/Rules.aspx?ID=2099):
- Circumstance, Status, Item: highest bonus only, worst (most negative) penalty only.
- Proficiency: treated as untyped for stacking (only one source expected).
- Untyped: bonuses don't stack by convention (only one expected), penalties ALL stack.
"""

from __future__ import annotations

from enum import Enum, auto


class BonusType(Enum):
    """Modifier types that determine stacking behavior.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2099)
    """
    CIRCUMSTANCE = auto()
    STATUS = auto()
    ITEM = auto()
    PROFICIENCY = auto()
    UNTYPED = auto()


# Types where only the highest bonus and worst penalty apply
_TYPED_BONUS_TYPES = frozenset({BonusType.CIRCUMSTANCE, BonusType.STATUS, BonusType.ITEM})


class BonusTracker:
    """Accumulates modifiers and applies PF2e stacking rules.

    Usage:
        t = BonusTracker()
        t.add(BonusType.CIRCUMSTANCE, 2, "cover")
        t.add(BonusType.CIRCUMSTANCE, 2, "raise shield")
        t.total()  # 2, not 4 — highest circumstance bonus only

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2099)
    """

    def __init__(self) -> None:
        # For typed bonuses/penalties: track best bonus and worst penalty per type
        self._typed_bonuses: dict[BonusType, int] = {}
        self._typed_penalties: dict[BonusType, int] = {}
        # For untyped/proficiency: accumulate directly
        self._untyped_total: int = 0

    def add(self, bonus_type: BonusType, value: int, source: str = "") -> None:
        """Add a modifier. Source is for documentation/debugging."""
        if bonus_type in _TYPED_BONUS_TYPES:
            if value > 0:
                self._typed_bonuses[bonus_type] = max(
                    self._typed_bonuses.get(bonus_type, 0), value
                )
            elif value < 0:
                self._typed_penalties[bonus_type] = min(
                    self._typed_penalties.get(bonus_type, 0), value
                )
        else:
            # UNTYPED and PROFICIENCY: all values accumulate
            self._untyped_total += value

    def total(self) -> int:
        """Compute the final modifier after stacking rules."""
        result = self._untyped_total
        for v in self._typed_bonuses.values():
            result += v
        for v in self._typed_penalties.values():
            result += v
        return result
