"""Tests for AbilityScores and modifier computation."""

import pytest

from pf2e.abilities import AbilityScores
from pf2e.types import Ability


@pytest.fixture
def scores() -> AbilityScores:
    return AbilityScores(str_=18, dex=16, con=14, int_=10, wis=11, cha=8)


class TestAbilityMod:
    """Modifier = (score - 10) // 2."""

    @pytest.mark.parametrize("score, expected_mod", [
        (8, -1),
        (10, 0),
        (11, 0),
        (12, 1),
        (14, 2),
        (16, 3),
        (18, 4),
        (19, 4),
        (20, 5),
    ])
    def test_mod_formula(self, score: int, expected_mod: int) -> None:
        abilities = AbilityScores(
            str_=score, dex=10, con=10, int_=10, wis=10, cha=10,
        )
        assert abilities.mod(Ability.STR) == expected_mod

    def test_mod_each_ability(self, scores: AbilityScores) -> None:
        assert scores.mod(Ability.STR) == 4   # (18-10)//2
        assert scores.mod(Ability.DEX) == 3   # (16-10)//2
        assert scores.mod(Ability.CON) == 2   # (14-10)//2
        assert scores.mod(Ability.INT) == 0   # (10-10)//2
        assert scores.mod(Ability.WIS) == 0   # (11-10)//2
        assert scores.mod(Ability.CHA) == -1  # (8-10)//2


class TestAbilityScore:
    """score() returns the raw ability score."""

    def test_score_indexing(self, scores: AbilityScores) -> None:
        assert scores.score(Ability.STR) == 18
        assert scores.score(Ability.DEX) == 16
        assert scores.score(Ability.CON) == 14
        assert scores.score(Ability.INT) == 10
        assert scores.score(Ability.WIS) == 11
        assert scores.score(Ability.CHA) == 8
