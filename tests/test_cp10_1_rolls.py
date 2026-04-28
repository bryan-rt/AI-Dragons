"""Tests for pf2e/rolls.py — CP10.1 Roll Foundation.

19 tests: 10 flat_check, 5 FortuneState.combine, 3 RollType, 1 regression.
"""

import pytest

from pf2e.rolls import RollType, FortuneState, flat_check

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# flat_check — 10 tests
# ---------------------------------------------------------------------------

class TestFlatCheck:
    def test_flat_check_dc5_concealment(self):
        """DC 5 concealed: 16 out of 20 results succeed."""
        assert flat_check(5) == pytest.approx(16 / 20)

    def test_flat_check_dc11_hidden(self):
        """DC 11 hidden: 10 out of 20 results succeed."""
        assert flat_check(11) == pytest.approx(10 / 20)

    def test_flat_check_dc15_persistent_damage(self):
        """DC 15 persistent damage recovery: 6 out of 20."""
        assert flat_check(15) == pytest.approx(6 / 20)

    def test_flat_check_dc20_near_impossible(self):
        """DC 20: only nat-20 succeeds = 1/20."""
        assert flat_check(20) == pytest.approx(1 / 20)

    def test_flat_check_dc21_impossible(self):
        """DC 21: impossible, nothing on a d20 reaches it."""
        assert flat_check(21) == 0.0

    def test_flat_check_dc1_always_succeeds(self):
        """DC 1: every result on d20 succeeds."""
        assert flat_check(1) == 1.0

    def test_flat_check_dc0_clamped_to_one(self):
        """DC 0 would give 21/20 = 1.05, clamped to 1.0."""
        assert flat_check(0) == 1.0

    def test_flat_check_dc_negative_clamped(self):
        """Negative DC clamped to 1.0."""
        assert flat_check(-5) == 1.0

    def test_flat_check_dc_high_clamped(self):
        """DC 25 (beyond d20 range) clamped to 0.0."""
        assert flat_check(25) == 0.0

    def test_flat_check_returns_float(self):
        """flat_check always returns a float, not int."""
        assert isinstance(flat_check(10), float)


# ---------------------------------------------------------------------------
# FortuneState.combine — 5 tests
# ---------------------------------------------------------------------------

class TestFortuneStateCombine:
    def test_fortune_state_neither(self):
        assert FortuneState.combine(False, False) is FortuneState.NORMAL

    def test_fortune_state_fortune_only(self):
        assert FortuneState.combine(True, False) is FortuneState.FORTUNE

    def test_fortune_state_misfortune_only(self):
        assert FortuneState.combine(False, True) is FortuneState.MISFORTUNE

    def test_fortune_state_both_cancel(self):
        assert FortuneState.combine(True, True) is FortuneState.CANCELLED

    def test_fortune_state_cancelled_not_normal(self):
        """CANCELLED is semantically distinct from NORMAL."""
        assert FortuneState.CANCELLED is not FortuneState.NORMAL


# ---------------------------------------------------------------------------
# RollType — 3 tests
# ---------------------------------------------------------------------------

class TestRollType:
    def test_roll_type_standard_exists(self):
        assert RollType.STANDARD is not None

    def test_roll_type_flat_exists(self):
        assert RollType.FLAT is not None

    def test_roll_types_are_distinct(self):
        assert RollType.STANDARD is not RollType.FLAT


# ---------------------------------------------------------------------------
# Killer Regression — EV 7.65
# ---------------------------------------------------------------------------

class TestEVRegression:
    def test_ev_7_65_regression(self):
        """24th verification: Strike Hard EV 7.65 after CP10.1."""
        from sim.scenario import load_scenario
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)
