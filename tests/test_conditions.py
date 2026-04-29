"""Tests for condition state machine (CP10.5).

Covers: ConditionDef registry, process_end_of_turn, conditions_removed
bug fix, simulate_round end-of-turn, integration, and regression.
"""

import pytest
from dataclasses import replace

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType
from pf2e.conditions import CONDITION_REGISTRY, ConditionDef, process_end_of_turn
from sim.round_state import RoundState
from sim.scenario import load_scenario
from sim.search import apply_outcome_to_state

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
# Registry (5)
# ===========================================================================

class TestRegistry:

    def test_frightened_end_of_turn_decrement(self):
        defn = CONDITION_REGISTRY["frightened"]
        assert defn.end_of_turn_decrement is True
        assert defn.tracked_as_int is True
        assert defn.snapshot_field == "frightened"

    def test_prone_tracked_as_bool(self):
        defn = CONDITION_REGISTRY["prone"]
        assert defn.tracked_as_bool is True
        assert defn.snapshot_field == "prone"

    def test_off_guard_tracked_as_bool(self):
        defn = CONDITION_REGISTRY["off_guard"]
        assert defn.tracked_as_bool is True
        assert defn.snapshot_field == "off_guard"

    def test_hidden_frozenset_only(self):
        defn = CONDITION_REGISTRY["hidden"]
        assert defn.tracked_as_bool is False
        assert defn.tracked_as_int is False

    def test_demoralize_immune_frozenset_only(self):
        defn = CONDITION_REGISTRY["demoralize_immune"]
        assert defn.tracked_as_bool is False
        assert defn.tracked_as_int is False


# ===========================================================================
# process_end_of_turn — PC (4)
# ===========================================================================

class TestProcessEndOfTurnPC:

    def test_pc_frightened_2_to_1(self):
        state = _quick_state(pc_overrides={"Rook": {"frightened": 2}})
        result = process_end_of_turn(state, "Rook")
        assert result.pcs["Rook"].frightened == 1

    def test_pc_frightened_1_clears(self):
        state = _quick_state(pc_overrides={"Rook": {"frightened": 1}})
        result = process_end_of_turn(state, "Rook")
        assert result.pcs["Rook"].frightened == 0

    def test_pc_not_frightened_no_change(self):
        state = _quick_state()
        assert state.pcs["Rook"].frightened == 0
        result = process_end_of_turn(state, "Rook")
        assert result.pcs["Rook"].frightened == 0

    def test_pc_frozenset_unchanged(self):
        """PC frightened is int field only — frozenset should not be modified."""
        conds = frozenset({"hidden", "cover"})
        state = _quick_state(pc_overrides={
            "Rook": {"frightened": 2, "conditions": conds},
        })
        result = process_end_of_turn(state, "Rook")
        assert result.pcs["Rook"].conditions == conds


# ===========================================================================
# process_end_of_turn — Enemy (4)
# ===========================================================================

class TestProcessEndOfTurnEnemy:

    def test_enemy_frightened_2_decrements(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"frightened_2"})},
        })
        result = process_end_of_turn(state, "Bandit1")
        assert "frightened_1" in result.enemies["Bandit1"].conditions
        assert "frightened_2" not in result.enemies["Bandit1"].conditions

    def test_enemy_frightened_1_cleared(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"frightened_1"})},
        })
        result = process_end_of_turn(state, "Bandit1")
        conds = result.enemies["Bandit1"].conditions
        assert not any(c.startswith("frightened_") for c in conds)

    def test_enemy_not_frightened_no_change(self):
        state = _quick_state()
        conds_before = state.enemies["Bandit1"].conditions
        result = process_end_of_turn(state, "Bandit1")
        assert result.enemies["Bandit1"].conditions == conds_before

    def test_parity_with_old_cleanup(self):
        """New process_end_of_turn matches old solver._end_of_turn_cleanup for enemies."""
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"frightened_2", "demoralize_immune"})},
        })
        result = process_end_of_turn(state, "Bandit1")
        conds = result.enemies["Bandit1"].conditions
        assert "frightened_1" in conds
        assert "demoralize_immune" in conds


# ===========================================================================
# conditions_removed bug fix (7)
# ===========================================================================

class TestConditionsRemovedFix:

    def _apply_removal(self, state, target_name, conds_to_remove):
        """Apply an outcome that removes conditions from target."""
        action = Action(type=ActionType.STAND, actor_name=target_name,
                        action_cost=1)
        outcome = ActionOutcome(
            probability=1.0,
            conditions_removed={target_name: tuple(conds_to_remove)},
        )
        return apply_outcome_to_state(outcome, state)

    def test_remove_prone_clears_bool(self):
        state = _quick_state(pc_overrides={
            "Rook": {"prone": True, "conditions": frozenset({"prone"})},
        })
        result = self._apply_removal(state, "Rook", ["prone"])
        assert result.pcs["Rook"].prone is False
        assert "prone" not in result.pcs["Rook"].conditions

    def test_remove_off_guard_clears_bool(self):
        state = _quick_state(pc_overrides={
            "Rook": {"off_guard": True, "conditions": frozenset({"off_guard"})},
        })
        result = self._apply_removal(state, "Rook", ["off_guard"])
        assert result.pcs["Rook"].off_guard is False

    def test_remove_shield_raised_clears_bool(self):
        state = _quick_state(pc_overrides={
            "Rook": {"shield_raised": True, "conditions": frozenset({"shield_raised"})},
        })
        result = self._apply_removal(state, "Rook", ["shield_raised"])
        assert result.pcs["Rook"].shield_raised is False

    def test_remove_frightened_clears_int(self):
        state = _quick_state(pc_overrides={"Rook": {"frightened": 2}})
        result = self._apply_removal(state, "Rook", ["frightened_2"])
        assert result.pcs["Rook"].frightened == 0

    def test_remove_frozenset_only_condition(self):
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"mortar_loaded", "mortar_aimed"})},
        })
        result = self._apply_removal(state, "Erisen", ["mortar_loaded"])
        assert "mortar_loaded" not in result.pcs["Erisen"].conditions
        assert "mortar_aimed" in result.pcs["Erisen"].conditions

    def test_remove_enemy_prone_clears_bool(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"prone": True, "conditions": frozenset({"prone"})},
        })
        result = self._apply_removal(state, "Bandit1", ["prone"])
        assert result.enemies["Bandit1"].prone is False
        assert "prone" not in result.enemies["Bandit1"].conditions

    def test_remove_mixed_conditions(self):
        """Remove prone (bool) and mortar_loaded (frozenset) simultaneously."""
        state = _quick_state(pc_overrides={
            "Erisen": {
                "prone": True,
                "conditions": frozenset({"prone", "mortar_loaded"}),
            },
        })
        result = self._apply_removal(state, "Erisen", ["prone", "mortar_loaded"])
        assert result.pcs["Erisen"].prone is False
        assert "prone" not in result.pcs["Erisen"].conditions
        assert "mortar_loaded" not in result.pcs["Erisen"].conditions


# ===========================================================================
# simulate_round end-of-turn (2)
# ===========================================================================

class TestSimulateRoundEndOfTurn:

    def test_simulate_round_frightened_decrements(self):
        """After simulate_round, PC frightened should be decremented."""
        from sim.search import simulate_round, SearchConfig
        state = _quick_state(pc_overrides={"Rook": {"frightened": 2}})
        state = replace(state, initiative_order=("Rook",))

        def cands(s, name):
            return [Action(type=ActionType.END_TURN, actor_name=name,
                           action_cost=0)]

        def evaluator(a, s):
            return ActionResult(
                action=a, outcomes=(ActionOutcome(probability=1.0),))

        plans, final = simulate_round(state, SearchConfig(), cands, evaluator)
        assert final.pcs["Rook"].frightened == 1

    def test_simulate_round_no_frightened_no_side_effect(self):
        from sim.search import simulate_round, SearchConfig
        state = _quick_state()
        state = replace(state, initiative_order=("Rook",))

        def cands(s, name):
            return [Action(type=ActionType.END_TURN, actor_name=name,
                           action_cost=0)]

        def evaluator(a, s):
            return ActionResult(
                action=a, outcomes=(ActionOutcome(probability=1.0),))

        plans, final = simulate_round(state, SearchConfig(), cands, evaluator)
        assert final.pcs["Rook"].frightened == 0


# ===========================================================================
# Integration (3)
# ===========================================================================

class TestIntegration:

    def test_stand_clears_prone_bool(self):
        """Applying Stand outcome clears prone: bool via conditions_removed fix."""
        state = _quick_state(pc_overrides={
            "Rook": {"prone": True, "conditions": frozenset({"prone"})},
        })
        action = Action(type=ActionType.STAND, actor_name="Rook",
                        action_cost=1)
        outcome = ActionOutcome(
            probability=1.0,
            conditions_removed={"Rook": ("prone",)},
        )
        result = apply_outcome_to_state(outcome, state)
        assert result.pcs["Rook"].prone is False

    def test_stand_then_crawl_ineligible(self):
        """After Stand clears prone, Crawl should be ineligible."""
        from pf2e.movement import evaluate_crawl
        state = _quick_state(pc_overrides={
            "Rook": {"prone": True, "conditions": frozenset({"prone"})},
        })
        # Apply Stand outcome
        outcome = ActionOutcome(
            probability=1.0,
            conditions_removed={"Rook": ("prone",)},
        )
        state = apply_outcome_to_state(outcome, state)
        # Now try Crawl
        crawl = Action(type=ActionType.CRAWL, actor_name="Rook",
                       action_cost=1, target_position=(5, 7))
        result = evaluate_crawl(crawl, state)
        assert not result.eligible

    def test_demoralize_chain(self):
        """Demoralize applies frightened → end-of-turn decrements it."""
        # Apply frightened_2 to enemy
        state = _quick_state()
        outcome = ActionOutcome(
            probability=1.0,
            conditions_applied={"Bandit1": ("frightened_2",)},
        )
        state = apply_outcome_to_state(outcome, state)
        assert "frightened_2" in state.enemies["Bandit1"].conditions
        # End of Bandit1's turn
        state = process_end_of_turn(state, "Bandit1")
        assert "frightened_1" in state.enemies["Bandit1"].conditions
        assert "frightened_2" not in state.enemies["Bandit1"].conditions


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_33rd_verification(self):
        """33rd verification: Strike Hard EV 7.65 after CP10.5."""
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
        """Tactical Takedown 55% prone unchanged after CP10.5."""
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
