"""Roll foundation types for PF2e Remaster.

Provides RollType, FortuneState, and flat_check — leaf module with
zero imports from other pf2e/ modules.

AoN references:
  RollType:      https://2e.aonprd.com/Rules.aspx?ID=2284
  Flat checks:   https://2e.aonprd.com/Rules.aspx?ID=2169
  Fortune/Misfortune: https://2e.aonprd.com/Rules.aspx?ID=2849
"""

from __future__ import annotations

from enum import Enum


class RollType(Enum):
    """Whether a roll is a standard d20 roll or a flat check.

    Standard rolls add modifiers and are affected by fortune/misfortune.
    Flat checks use only the raw d20 result against a DC, with no modifiers.
    https://2e.aonprd.com/Rules.aspx?ID=2284
    """
    STANDARD = "standard"
    FLAT = "flat"


class FortuneState(Enum):
    """Fortune/misfortune state for a roll.

    FORTUNE = roll twice, take higher.
    MISFORTUNE = roll twice, take lower.
    CANCELLED = both apply, they cancel out (roll once normally).
    NORMAL = neither applies.

    https://2e.aonprd.com/Rules.aspx?ID=2849
    """
    NORMAL = "normal"
    FORTUNE = "fortune"
    MISFORTUNE = "misfortune"
    CANCELLED = "cancelled"

    @staticmethod
    def combine(has_fortune: bool, has_misfortune: bool) -> FortuneState:
        """Combine fortune and misfortune sources into a single state.

        Per PF2e rules, if you have both fortune and misfortune effects,
        they cancel each other out and you roll normally.
        https://2e.aonprd.com/Rules.aspx?ID=2849
        """
        if has_fortune and has_misfortune:
            return FortuneState.CANCELLED
        if has_fortune:
            return FortuneState.FORTUNE
        if has_misfortune:
            return FortuneState.MISFORTUNE
        return FortuneState.NORMAL


def flat_check(dc: int) -> float:
    """Return probability of succeeding on a flat check against the given DC.

    Flat checks: roll d20, succeed if result >= DC. No modifiers apply.
    P(success) = (21 - dc) / 20, clamped to [0.0, 1.0].

    https://2e.aonprd.com/Rules.aspx?ID=2169
    """
    return max(0.0, min(1.0, (21 - dc) / 20))
