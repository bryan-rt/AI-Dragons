"""Tests for scenario [initiative] section parsing (Pass 3a)."""

import pytest

from sim.scenario import ScenarioParseError, parse_scenario


BASE = """\
[grid]
. . . . .
. c g m .
. . . . .

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2 atk=7 dmg=1d8 dmg_bonus=3 attacks=2
"""


class TestInitiativeSection:
    def test_no_section_defaults_to_seed_42(self) -> None:
        s = parse_scenario(BASE)
        assert s.initiative_seed == 42
        assert s.initiative_explicit == {}

    def test_seed_only(self) -> None:
        text = BASE + "\n[initiative]\nseed = 99\n"
        s = parse_scenario(text)
        assert s.initiative_seed == 99
        assert s.initiative_explicit == {}

    def test_explicit_ordering(self) -> None:
        text = BASE + "\n[initiative]\nAetregan = 18\nBandit1 = 12\nRook = 10\n"
        s = parse_scenario(text)
        assert s.initiative_explicit == {
            "Aetregan": 18,
            "Bandit1": 12,
            "Rook": 10,
        }

    def test_invalid_seed_raises(self) -> None:
        text = BASE + "\n[initiative]\nseed = abc\n"
        with pytest.raises(ScenarioParseError, match="seed"):
            parse_scenario(text)

    def test_invalid_explicit_value_raises(self) -> None:
        text = BASE + "\n[initiative]\nAetregan = notanumber\n"
        with pytest.raises(ScenarioParseError):
            parse_scenario(text)
