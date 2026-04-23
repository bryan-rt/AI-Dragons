"""Tests for sim/scenario.py — scenario loading and TacticContext building."""

import pytest

from pf2e.tactics import STRIKE_HARD, evaluate_tactic
from sim.scenario import (
    Scenario,
    ScenarioParseError,
    load_scenario,
    parse_scenario,
)

EV_TOLERANCE = 0.01
SCENARIOS_DIR = "scenarios"


# ---------------------------------------------------------------------------
# Test A: Killer validation — load from disk, evaluate, EV 8.55
# ---------------------------------------------------------------------------

class TestKillerValidation:
    """The canonical end-to-end test: file -> grid -> tactics -> EV 8.55."""

    def test_strike_hard_from_disk(self) -> None:
        scenario = load_scenario(
            f"{SCENARIOS_DIR}/checkpoint_1_strike_hard.scenario"
        )
        assert scenario.name == "Strike Hard Validation"
        assert scenario.level == 1
        assert scenario.banner_planted is True
        assert scenario.banner_position == (5, 5)
        assert scenario.anthem_active is True
        assert len(scenario.squadmates) == 3
        assert len(scenario.enemies) == 1
        assert scenario.enemies[0].name == "Bandit1"

        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)

        assert result.eligible
        assert result.best_target_ally == "Rook"
        assert result.best_target_enemy == "Bandit1"
        assert result.expected_damage_dealt == pytest.approx(
            8.55, abs=EV_TOLERANCE,
        )


# ---------------------------------------------------------------------------
# Test B: Parse error handling
# ---------------------------------------------------------------------------

class TestParseErrors:

    def test_missing_grid_section(self) -> None:
        text = """\
[meta]
name = broken

[enemies]
m1 name=X ac=10 ref=0 fort=0 will=0
"""
        with pytest.raises(ScenarioParseError, match="grid"):
            parse_scenario(text)

    def test_missing_commander_in_grid(self) -> None:
        text = """\
[grid]
. . . . .
. g . m .
. . . . .

[enemies]
m1 name=X ac=10 ref=0 fort=0 will=0
"""
        with pytest.raises(ScenarioParseError, match="commander"):
            parse_scenario(text)

    def test_enemy_in_grid_no_stats(self) -> None:
        text = """\
[grid]
. . . . .
. c g m .
. . . . .
"""
        with pytest.raises(ScenarioParseError, match="m1"):
            parse_scenario(text)

    def test_enemy_stats_no_grid_token(self) -> None:
        text = """\
[grid]
. . . . .
. c g . .
. . . . .

[enemies]
m1 name=Ghost ac=14 ref=2 fort=2 will=2
"""
        with pytest.raises(ScenarioParseError, match="m1"):
            parse_scenario(text)

    def test_invalid_integer_in_enemy_stats(self) -> None:
        text = """\
[grid]
. . . . .
. c g m .
. . . . .

[enemies]
m1 name=X ac=abc ref=5 fort=3 will=2
"""
        with pytest.raises(ScenarioParseError):
            parse_scenario(text)


# ---------------------------------------------------------------------------
# Test C: Minimal scenario (no banner, no anthem)
# ---------------------------------------------------------------------------

class TestMinimalScenario:

    def test_no_banner_no_anthem(self) -> None:
        text = """\
[grid]
. . . . . .
. c g . m .
. . . . . .

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
"""
        scenario = parse_scenario(text)
        assert scenario.banner_position is None
        assert scenario.banner_planted is False
        assert scenario.anthem_active is False

        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert not result.eligible
        assert "aura" in result.ineligibility_reason.lower()


# ---------------------------------------------------------------------------
# Test D: Grid banner fallback (no [banner] section)
# ---------------------------------------------------------------------------

class TestGridBannerFallback:

    def test_grid_B_token_populates_banner(self) -> None:
        text = """\
[grid]
. . . . . .
. c g B . .
. . . . . .
"""
        scenario = parse_scenario(text)
        assert scenario.banner_position == (1, 3)
        assert scenario.banner_planted is True


# ---------------------------------------------------------------------------
# Test E: parse_scenario with inline text
# ---------------------------------------------------------------------------

class TestInlineParse:

    def test_inline_full_scenario(self) -> None:
        """parse_scenario works without touching the filesystem."""
        text = """\
[meta]
name = Inline Test

[grid]
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . c g m . .
. . . . i b . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .

[banner]
planted = true
position = 5, 5

[anthem]
active = true

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
"""
        scenario = parse_scenario(text)
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.eligible
        assert result.expected_damage_dealt == pytest.approx(
            8.55, abs=EV_TOLERANCE,
        )

    def test_optional_squadmates_absent(self) -> None:
        """Scenario with only commander — no squadmates."""
        text = """\
[grid]
. . . . .
. c . m .
. . . . .

[banner]
planted = true
position = 1, 1

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
"""
        scenario = parse_scenario(text)
        assert scenario.commander.character.name == "Aetregan"
        assert len(scenario.squadmates) == 0
        assert len(scenario.enemies) == 1
