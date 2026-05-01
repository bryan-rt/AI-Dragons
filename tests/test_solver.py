"""Tests for sim/solver.py — full combat solver (CP6)."""

import pytest

from pf2e.actions import ActionType
from sim.scenario import load_scenario
from sim.solver import (
    CombatSolution,
    RoundLog,
    TurnLog,
    _all_enemies_dead,
    _all_pcs_dead,
    _compute_cumulative_score,
    _difficulty_rating,
    _end_of_turn_cleanup,
    _hp_summary,
    _is_dead,
    _reset_turn_state,
    solve_combat,
)
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


def _quick_state():
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    init_order = ["Aetregan", "Rook", "Dalai Alpaca", "Erisen", "Bandit1"]
    return RoundState.from_scenario(scenario, init_order)


# ---------------------------------------------------------------------------
# Condition duration tests (write first per brief)
# ---------------------------------------------------------------------------

class TestResetTurnState:

    def test_resets_map_count(self) -> None:
        state = _quick_state()
        state = state.with_pc_update("Rook", map_count=2)
        state = _reset_turn_state(state, "Rook")
        assert state.pcs["Rook"].map_count == 0

    def test_resets_actions_remaining(self) -> None:
        state = _quick_state()
        state = state.with_pc_update("Rook", actions_remaining=0)
        state = _reset_turn_state(state, "Rook")
        assert state.pcs["Rook"].actions_remaining == 3

    def test_clears_shield_raised(self) -> None:
        state = _quick_state()
        state = state.with_pc_update("Rook", shield_raised=True)
        state = _reset_turn_state(state, "Rook")
        assert not state.pcs["Rook"].shield_raised

    def test_clears_anthem_for_bard(self) -> None:
        from dataclasses import replace
        state = replace(_quick_state(), anthem_active=True)
        state = _reset_turn_state(state, "Dalai Alpaca")
        assert not state.anthem_active

    def test_clears_taunt_for_guardian(self) -> None:
        state = _quick_state()
        state = state.with_pc_update(
            "Rook", conditions=frozenset({"taunting_Bandit1"}),
        )
        state = state.with_enemy_update(
            "Bandit1", conditions=frozenset({"taunted_by_rook"}),
        )
        state = _reset_turn_state(state, "Rook")
        assert "taunting_Bandit1" not in state.pcs["Rook"].conditions
        assert "taunted_by_rook" not in state.enemies["Bandit1"].conditions

    def test_does_not_clear_encounter_conditions(self) -> None:
        state = _quick_state()
        state = state.with_pc_update(
            "Dalai Alpaca",
            conditions=frozenset({"soothe_used", "recalled_bandit1"}),
        )
        state = _reset_turn_state(state, "Dalai Alpaca")
        assert "soothe_used" in state.pcs["Dalai Alpaca"].conditions
        assert "recalled_bandit1" in state.pcs["Dalai Alpaca"].conditions


class TestEndOfTurnCleanup:

    def test_decrements_frightened(self) -> None:
        state = _quick_state()
        state = state.with_pc_update("Rook", frightened=2)
        state = _end_of_turn_cleanup(state, "Rook")
        # PC frightened lives in int field, not frozenset (CP10.5)
        assert state.pcs["Rook"].frightened == 1

    def test_removes_frightened_at_zero(self) -> None:
        state = _quick_state()
        state = state.with_pc_update("Rook", frightened=1)
        state = _end_of_turn_cleanup(state, "Rook")
        assert state.pcs["Rook"].frightened == 0

    def test_no_change_without_frightened(self) -> None:
        state = _quick_state()
        original_conds = state.pcs["Rook"].conditions
        state = _end_of_turn_cleanup(state, "Rook")
        assert state.pcs["Rook"].conditions == original_conds


# ---------------------------------------------------------------------------
# STAND tests
# ---------------------------------------------------------------------------

class TestStand:

    def test_stand_eligible_when_prone(self) -> None:
        from pf2e.actions import evaluate_stand, Action
        state = _quick_state()
        state = state.with_pc_update("Rook", prone=True)
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        result = evaluate_stand(action, state)
        assert result.eligible

    def test_stand_ineligible_when_not_prone(self) -> None:
        from pf2e.actions import evaluate_stand, Action
        state = _quick_state()
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        result = evaluate_stand(action, state)
        assert not result.eligible

    def test_stand_clears_prone(self) -> None:
        from pf2e.actions import evaluate_stand, Action
        state = _quick_state()
        state = state.with_pc_update("Rook", prone=True)
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        result = evaluate_stand(action, state)
        removed = result.outcomes[0].conditions_removed.get("Rook", ())
        assert "prone" in removed


# ---------------------------------------------------------------------------
# Solver tests
# ---------------------------------------------------------------------------

class TestSolveCombat:

    def test_solve_combat_victory(self) -> None:
        scenario = load_scenario("scenarios/checkpoint_2_two_bandits.scenario")
        solution = solve_combat(scenario, seed=42, max_rounds=10)
        assert solution.outcome == "victory"
        assert solution.rounds_taken <= 10

    def test_solve_combat_has_round_logs(self) -> None:
        scenario = load_scenario("scenarios/checkpoint_2_two_bandits.scenario")
        solution = solve_combat(scenario, seed=42)
        assert len(solution.rounds) > 0
        assert len(solution.rounds[0].turns) > 0

    def test_solve_combat_round_cap(self) -> None:
        """Very short max_rounds forces timeout or fast victory."""
        scenario = load_scenario("scenarios/checkpoint_2_two_bandits.scenario")
        solution = solve_combat(scenario, seed=42, max_rounds=1)
        # With 1 round max, likely can't kill both bandits
        assert solution.rounds_taken <= 1

    def test_solve_combat_returns_optimal(self) -> None:
        scenario = load_scenario("scenarios/checkpoint_2_two_bandits.scenario")
        solution = solve_combat(scenario, seed=42)
        if solution.outcome == "victory":
            assert solution.is_optimal

    def test_solve_combat_skips_dead(self) -> None:
        """Dead enemies should not appear in later round turn logs.

        Note: PCs at 0 HP may still get turns (dying system processes
        recovery checks). This test only verifies dead *enemies* are
        skipped, since enemies die immediately at 0 HP (no dying state).
        """
        scenario = load_scenario("scenarios/checkpoint_2_two_bandits.scenario")
        solution = solve_combat(scenario, seed=42)
        if solution.rounds_taken >= 2:
            last_turn = solution.rounds[0].turns[-1]
            round1_dead_enemies = {
                name for name, hp in last_turn.hp_summary.items()
                if hp <= 0 and name.startswith("Bandit")
            }
            round2_actors = {t.combatant_name for t in solution.rounds[1].turns}
            assert round1_dead_enemies.isdisjoint(round2_actors)


class TestDifficultyRating:

    def test_trivial(self) -> None:
        assert _difficulty_rating("victory", 2) == "trivial"

    def test_easy(self) -> None:
        assert _difficulty_rating("victory", 4) == "easy"

    def test_impossible(self) -> None:
        assert _difficulty_rating("wipe", 3) == "impossible"

    def test_timeout_impossible(self) -> None:
        assert _difficulty_rating("timeout", 10) == "impossible"


class TestCumulativeScore:

    def test_round_bonus(self) -> None:
        state = _quick_state()
        fast = _compute_cumulative_score([10.0], 2, state, 10)
        slow = _compute_cumulative_score([10.0], 8, state, 10)
        assert fast > slow

    def test_survival_bonus(self) -> None:
        state = _quick_state()
        healthy = _compute_cumulative_score([10.0], 5, state, 10)
        # Damage a PC
        damaged_state = state.with_pc_update("Rook", current_hp=1)
        injured = _compute_cumulative_score([10.0], 5, damaged_state, 10)
        assert healthy > injured


class TestFullCombatCli:

    def test_full_combat_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        from sim.cli import main
        main([
            "--scenario", "scenarios/checkpoint_2_two_bandits.scenario",
            "--full-combat", "--seed", "42",
        ])
        out = capsys.readouterr().out
        assert "Round 1" in out
        assert "Outcome" in out
