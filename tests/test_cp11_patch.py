"""Tests for CP11.3 patch: initiative locking, early exit, MAP completeness."""

import pytest
from dataclasses import replace

from pf2e.actions import Action, ActionType
from pf2e.tactics import evaluate_tactic, STRIKE_HARD
from sim.scenario import load_scenario
from sim.solver import solve_combat
from sim.search import (
    _ATTACK_TRAIT_TYPES, _update_action_economy,
    simulate_round, SearchConfig,
)
from sim.round_state import RoundState

SCENARIO_1 = "scenarios/checkpoint_1_strike_hard.scenario"
SCENARIO_4 = "scenarios/checkpoint_4_terrain_camp.scenario"
EV_TOLERANCE = 0.01


# -------------------------------------------------------------------
# Fix 1: Initiative locking
# -------------------------------------------------------------------

class TestInitiativeLocking:

    def test_solve_combat_deterministic(self):
        """Same scenario produces identical result on two calls."""
        scenario = load_scenario(SCENARIO_1)
        r1 = solve_combat(scenario)
        r2 = solve_combat(scenario)
        assert r1.outcome == r2.outcome
        assert r1.rounds_taken == r2.rounds_taken
        assert r1.total_score == pytest.approx(r2.total_score, abs=0.01)

    def test_solve_combat_is_optimal_always_true(self):
        scenario = load_scenario(SCENARIO_1)
        result = solve_combat(scenario)
        assert result.is_optimal is True

    def test_solve_combat_scenario_seed_overrides_caller_seed(self):
        """scenario.initiative_seed wins over the seed parameter."""
        scenario = load_scenario(SCENARIO_1)
        r1 = solve_combat(scenario, seed=42)
        r2 = solve_combat(scenario, seed=99)
        assert r1.rounds_taken == r2.rounds_taken
        assert r1.outcome == r2.outcome

    def test_solve_combat_no_num_plans_parameter(self):
        """num_plans removed — passing it raises TypeError."""
        scenario = load_scenario(SCENARIO_1)
        with pytest.raises(TypeError):
            solve_combat(scenario, num_plans=3)

    def test_solve_combat_returns_combat_solution(self):
        """Return type has expected fields."""
        scenario = load_scenario(SCENARIO_1)
        result = solve_combat(scenario)
        assert result.outcome in ("victory", "wipe", "timeout")
        assert result.rounds_taken >= 1
        assert result.scenario_name == scenario.name


# -------------------------------------------------------------------
# Fix 2: Early exit in simulate_round
# -------------------------------------------------------------------

class TestEarlyExit:

    def _make_state(self, enemy_hp):
        scenario = load_scenario(SCENARIO_1)
        state = RoundState.from_scenario(
            scenario,
            ["Aetregan", "Rook", "Dalai Alpaca", "Erisen", "Bandit1"],
        )
        return state.with_enemy_update("Bandit1", current_hp=enemy_hp)

    def test_early_exit_when_enemy_killed_mid_round(self):
        """Plans list shorter than initiative order when enemy dies."""
        from pf2e.actions import evaluate_action
        from sim.candidates import generate_candidates

        state = self._make_state(enemy_hp=1)
        config = SearchConfig()
        plans, final = simulate_round(
            state, config, generate_candidates, evaluate_action,
        )
        assert all(e.current_hp <= 0 for e in final.enemies.values())
        assert len(plans) < len(state.initiative_order)

    def test_no_early_exit_when_enemy_survives(self):
        """All turns execute when enemy cannot be killed this round."""
        from pf2e.actions import evaluate_action
        from sim.candidates import generate_candidates

        # 200 HP guarantees no kill this round
        state = self._make_state(enemy_hp=200)
        state = state.with_enemy_update("Bandit1", max_hp=200)
        config = SearchConfig()
        plans, final = simulate_round(
            state, config, generate_candidates, evaluate_action,
        )
        assert len(plans) == len(state.initiative_order)

    def test_final_state_has_dead_enemies_after_early_exit(self):
        """Final state reflects zero HP on enemies after exit."""
        from pf2e.actions import evaluate_action
        from sim.candidates import generate_candidates

        state = self._make_state(enemy_hp=1)
        config = SearchConfig()
        _, final = simulate_round(
            state, config, generate_candidates, evaluate_action,
        )
        for enemy in final.enemies.values():
            assert enemy.current_hp <= 0


# -------------------------------------------------------------------
# Fix 3: MAP completeness
# -------------------------------------------------------------------

class TestMAPCompleteness:

    def test_mortar_launch_in_attack_trait_types(self):
        assert ActionType.MORTAR_LAUNCH in _ATTACK_TRAIT_TYPES

    def test_strike_still_in_attack_trait_types(self):
        assert ActionType.STRIKE in _ATTACK_TRAIT_TYPES

    def test_trip_still_in_attack_trait_types(self):
        assert ActionType.TRIP in _ATTACK_TRAIT_TYPES

    def test_cast_spell_not_in_frozenset(self):
        """CAST_SPELL handled conditionally, not via frozenset."""
        assert ActionType.CAST_SPELL not in _ATTACK_TRAIT_TYPES

    def _erisen_state(self):
        scenario = load_scenario(SCENARIO_1)
        return RoundState.from_scenario(scenario, ["Erisen", "Bandit1"])

    def _dalai_state(self):
        scenario = load_scenario(SCENARIO_1)
        return RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Bandit1"])

    def test_needle_darts_increments_map_count(self):
        """CAST_SPELL with attack-roll pattern increments map_count."""
        state = self._erisen_state()
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Erisen",
            action_cost=2, target_name="Bandit1",
            tactic_name="needle-darts",
        )
        state2 = _update_action_economy(state, "Erisen", action)
        assert state2.pcs["Erisen"].map_count == 1

    def test_force_barrage_does_not_increment_map_count(self):
        """CAST_SPELL with auto-hit pattern does NOT increment."""
        state = self._dalai_state()
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=1, target_name="Bandit1",
            tactic_name="force-barrage",
        )
        state2 = _update_action_economy(
            state, "Dalai Alpaca", action)
        assert state2.pcs["Dalai Alpaca"].map_count == 0

    def test_fear_does_not_increment_map_count(self):
        """CAST_SPELL with save pattern does NOT increment."""
        state = self._dalai_state()
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1",
            tactic_name="fear",
        )
        state2 = _update_action_economy(
            state, "Dalai Alpaca", action)
        assert state2.pcs["Dalai Alpaca"].map_count == 0

    def test_mortar_launch_increments_map_count(self):
        """MORTAR_LAUNCH increments map_count via frozenset."""
        state = self._erisen_state()
        action = Action(
            type=ActionType.MORTAR_LAUNCH, actor_name="Erisen",
            action_cost=1,
        )
        state2 = _update_action_economy(state, "Erisen", action)
        assert state2.pcs["Erisen"].map_count == 1


# -------------------------------------------------------------------
# Regression
# -------------------------------------------------------------------

class TestRegression:

    def test_ev_7_65_42nd_verification(self):
        """EV 7.65 unchanged — 42nd verification."""
        scenario = load_scenario(SCENARIO_1)
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(
            7.65, abs=EV_TOLERANCE)

    def test_terrain_scenario_victory(self):
        """Full combat resolves to victory after solver change."""
        scenario = load_scenario(SCENARIO_4)
        result = solve_combat(scenario)
        assert result.outcome == "victory"
