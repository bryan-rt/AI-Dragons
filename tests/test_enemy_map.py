"""Tests for enemy MAP tracking (CP11.3).

Covers: MAP penalty application, map_count field, _update_action_economy
for enemies, _reset_turn_state, integration, and regression.
"""

import pytest
from dataclasses import replace

from pf2e.actions import Action, ActionType
from pf2e.combat_math import map_penalty
from pf2e.strike import evaluate_enemy_strike
from sim.round_state import EnemySnapshot, RoundState
from sim.scenario import load_scenario
from sim.search import _update_action_economy
from sim.solver import _reset_turn_state

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quick_state(
    pc_overrides: dict | None = None,
    enemy_overrides: dict | None = None,
) -> RoundState:
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    init_order = ["Aetregan", "Rook", "Dalai Alpaca", "Erisen", "Bandit1"]
    state = RoundState.from_scenario(scenario, init_order)
    if pc_overrides:
        for name, changes in pc_overrides.items():
            state = state.with_pc_update(name, **changes)
    if enemy_overrides:
        for name, changes in enemy_overrides.items():
            state = state.with_enemy_update(name, **changes)
    return state


# ===========================================================================
# MAP penalty application (4)
# ===========================================================================

class TestEnemyMAPPenalty:

    def test_first_strike_no_penalty(self):
        """map_count=0: no MAP applied, uses raw attack_bonus."""
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        ev_first = result.expected_damage_dealt
        assert ev_first > 0

    def test_second_strike_minus_5(self):
        """map_count=1: -5 MAP applied."""
        state = _quick_state(enemy_overrides={"Bandit1": {"map_count": 1}})
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        ev_second = result.expected_damage_dealt

        # Compare with first strike
        state0 = _quick_state()
        r0 = evaluate_enemy_strike(action, state0)
        assert ev_second < r0.expected_damage_dealt

    def test_third_strike_minus_10(self):
        """map_count=2: -10 MAP applied."""
        state = _quick_state(enemy_overrides={"Bandit1": {"map_count": 2}})
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        ev_third = result.expected_damage_dealt

        state1 = _quick_state(enemy_overrides={"Bandit1": {"map_count": 1}})
        r1 = evaluate_enemy_strike(action, state1)
        assert ev_third < r1.expected_damage_dealt

    def test_map_penalty_values(self):
        """Verify map_penalty function for standard (non-agile) weapons."""
        assert map_penalty(1, agile=False) == 0
        assert map_penalty(2, agile=False) == -5
        assert map_penalty(3, agile=False) == -10


# ===========================================================================
# map_count field (3)
# ===========================================================================

class TestMapCountField:

    def test_default_map_count_0(self):
        state = _quick_state()
        assert state.enemies["Bandit1"].map_count == 0

    def test_map_count_increments_on_strike(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        state2 = _update_action_economy(state, "Bandit1", action)
        assert state2.enemies["Bandit1"].map_count == 1

    def test_map_count_no_increment_on_stride(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIDE, actor_name="Bandit1",
                        action_cost=1, target_position=(5, 6))
        state2 = _update_action_economy(state, "Bandit1", action)
        assert state2.enemies["Bandit1"].map_count == 0


# ===========================================================================
# _reset_turn_state (2)
# ===========================================================================

class TestResetTurnState:

    def test_map_count_resets_to_0(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"map_count": 2}})
        state2 = _reset_turn_state(state, "Bandit1")
        assert state2.enemies["Bandit1"].map_count == 0

    def test_actions_remaining_resets_to_3(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"actions_remaining": 0}})
        state2 = _reset_turn_state(state, "Bandit1")
        assert state2.enemies["Bandit1"].actions_remaining == 3


# ===========================================================================
# Integration (3)
# ===========================================================================

class TestIntegration:

    def test_sequential_strikes_apply_map(self):
        """Simulate 3 sequential enemy strikes with MAP accumulating."""
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")

        evs = []
        for i in range(3):
            r = evaluate_enemy_strike(action, state)
            evs.append(r.expected_damage_dealt)
            state = _update_action_economy(state, "Bandit1", action)

        # Each subsequent strike should be weaker
        assert evs[0] > evs[1] > evs[2]

    def test_stride_then_strike_no_map(self):
        """STRIDE doesn't increment MAP; following STRIKE is at MAP 0."""
        state = _quick_state()
        stride = Action(type=ActionType.STRIDE, actor_name="Bandit1",
                        action_cost=1, target_position=(5, 6))
        state = _update_action_economy(state, "Bandit1", stride)
        assert state.enemies["Bandit1"].map_count == 0

        strike = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        r = evaluate_enemy_strike(strike, state)
        # First strike after stride: no MAP
        r_fresh = evaluate_enemy_strike(strike, _quick_state())
        assert r.expected_damage_dealt == pytest.approx(
            r_fresh.expected_damage_dealt, abs=0.01)

    def test_enemy_ev_lower_than_before(self):
        """Enemy 3-strike EV with MAP < 3× first strike EV (was equal before)."""
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        r_first = evaluate_enemy_strike(action, state)
        first_ev = r_first.expected_damage_dealt

        total = 0.0
        s = state
        for _ in range(3):
            r = evaluate_enemy_strike(action, s)
            total += r.expected_damage_dealt
            s = _update_action_economy(s, "Bandit1", action)

        # Before MAP fix, total would be 3 × first_ev
        # After fix, it's less because 2nd and 3rd strikes are weaker
        assert total < 3 * first_ev


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_40th_verification(self):
        """EV 7.65 unchanged — tactic evaluator doesn't use enemy strikes."""
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)

    def test_mortar_ev_5_95(self):
        from pf2e.save_damage import basic_save_ev
        ev = basic_save_ev(dc=17, save_mod=5, base_dmg=7.0)
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)

    def test_prone_probability_55pct(self):
        from pf2e.tactics import evaluate_tactic, TACTICAL_TAKEDOWN
        from tests.test_tactics import MockSpatialQueries
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        ctx.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": False},
            distances={("Rook", "Bandit1"): 10, ("Dalai Alpaca", "Bandit1"): 10},
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, ctx)
        assert result.eligible
        assert result.condition_probabilities["Bandit1"]["prone"] == pytest.approx(
            0.55, abs=0.01)
