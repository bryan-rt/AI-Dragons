"""Proficiency bonus calculation.

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2136)
"""

from pf2e.types import ProficiencyRank


def proficiency_bonus(rank: ProficiencyRank, level: int) -> int:
    """Compute proficiency bonus from rank and character level.

    Untrained: always 0.
    Trained or better: rank bonus (2/4/6/8) + level.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2136)
    """
    if rank == ProficiencyRank.UNTRAINED:
        return 0
    return rank.value + level
