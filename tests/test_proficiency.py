"""Tests for proficiency bonus calculation."""

import pytest

from pf2e.proficiency import proficiency_bonus
from pf2e.types import ProficiencyRank


class TestProficiencyBonus:

    def test_untrained_always_zero(self) -> None:
        for level in (1, 5, 10, 20):
            assert proficiency_bonus(ProficiencyRank.UNTRAINED, level) == 0

    @pytest.mark.parametrize("rank, level, expected", [
        (ProficiencyRank.TRAINED, 1, 3),
        (ProficiencyRank.EXPERT, 1, 5),
        (ProficiencyRank.MASTER, 1, 7),
        (ProficiencyRank.LEGENDARY, 1, 9),
        (ProficiencyRank.TRAINED, 5, 7),
        (ProficiencyRank.MASTER, 10, 16),
        (ProficiencyRank.EXPERT, 20, 24),
        (ProficiencyRank.LEGENDARY, 20, 28),
    ])
    def test_proficiency_values(
        self, rank: ProficiencyRank, level: int, expected: int
    ) -> None:
        assert proficiency_bonus(rank, level) == expected
