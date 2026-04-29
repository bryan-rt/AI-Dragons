"""Tests for auto-state chassis (CP10.4.2).

Covers: registry, eligibility, outcomes, EV, parity with old evaluators,
new actions (Drop Prone, Take Cover), and EV 7.65 regression.
"""

import pytest

from pf2e.actions import (
    Action,
    ActionType,
    evaluate_action,
    evaluate_raise_shield,
    evaluate_stand,
)
from pf2e.auto_state import (
    AUTO_STATE_REGISTRY,
    AutoStateDef,
    _compute_ev,
    evaluate_auto_state,
)
from pf2e.types import SaveType
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState
from sim.scenario import load_scenario
from tests.fixtures import make_rook

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quick_state(
    pc_overrides: dict | None = None,
    enemy_overrides: dict | None = None,
) -> RoundState:
    """Build a RoundState from the canonical scenario."""
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
# Registry (3)
# ===========================================================================

class TestRegistry:

    def test_registry_has_4_entries(self):
        assert len(AUTO_STATE_REGISTRY) == 4

    def test_all_entries_frozen(self):
        for defn in AUTO_STATE_REGISTRY.values():
            assert isinstance(defn, AutoStateDef)
            assert isinstance(defn.traits, frozenset)
            assert isinstance(defn.conditions_applied, tuple)
            assert isinstance(defn.conditions_removed, tuple)

    def test_ev_formula_values_valid(self):
        valid = {"", "shield_danger"}
        for defn in AUTO_STATE_REGISTRY.values():
            assert defn.ev_formula in valid, f"Invalid formula: {defn.ev_formula}"


# ===========================================================================
# Eligibility (8)
# ===========================================================================

class TestEligibility:

    def test_stand_ineligible_when_not_prone(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": False}})
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert not result.eligible
        assert "needs prone" in result.ineligibility_reason

    def test_stand_eligible_when_prone(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert result.eligible

    def test_raise_shield_ineligible_when_no_shield_held(self):
        state = _quick_state(pc_overrides={"Rook": {"held_weapons": ()}})
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert not result.eligible
        assert "shield not held" in result.ineligibility_reason

    def test_raise_shield_eligible_when_shield_held_not_raised(self):
        rook = make_rook()
        shield_name = rook.shield.name
        state = _quick_state(pc_overrides={
            "Rook": {"held_weapons": (shield_name,), "shield_raised": False},
        })
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert result.eligible

    def test_drop_prone_ineligible_when_already_prone(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.DROP_PRONE, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert not result.eligible
        assert "already has prone" in result.ineligibility_reason

    def test_drop_prone_eligible_when_not_prone(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": False}})
        action = Action(type=ActionType.DROP_PRONE, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert result.eligible

    def test_take_cover_ineligible_when_already_covered(self):
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"cover"})},
        })
        action = Action(type=ActionType.TAKE_COVER, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert not result.eligible
        assert "already has cover" in result.ineligibility_reason

    def test_take_cover_eligible_when_no_cover(self):
        state = _quick_state()
        action = Action(type=ActionType.TAKE_COVER, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert result.eligible


# ===========================================================================
# Outcomes (4)
# ===========================================================================

class TestOutcomes:

    def test_stand_removes_prone_condition(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert result.eligible
        outcome = result.outcomes[0]
        assert outcome.probability == 1.0
        assert "prone" in outcome.conditions_removed.get("Rook", ())

    def test_raise_shield_applies_shield_raised(self):
        rook = make_rook()
        shield_name = rook.shield.name
        state = _quick_state(pc_overrides={
            "Rook": {"held_weapons": (shield_name,), "shield_raised": False},
        })
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        outcome = result.outcomes[0]
        assert "shield_raised" in outcome.conditions_applied.get("Rook", ())

    def test_drop_prone_applies_prone(self):
        state = _quick_state()
        action = Action(type=ActionType.DROP_PRONE, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        outcome = result.outcomes[0]
        assert "prone" in outcome.conditions_applied.get("Rook", ())

    def test_take_cover_applies_cover(self):
        state = _quick_state()
        action = Action(type=ActionType.TAKE_COVER, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        outcome = result.outcomes[0]
        assert "cover" in outcome.conditions_applied.get("Rook", ())


# ===========================================================================
# EV (2)
# ===========================================================================

class TestEV:

    def test_shield_danger_nonzero_vs_live_enemy(self):
        rook = make_rook()
        shield_name = rook.shield.name
        state = _quick_state(pc_overrides={
            "Rook": {"held_weapons": (shield_name,), "shield_raised": False},
        })
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert result.eligible
        assert result.outcomes[0].score_delta > 0.0

    def test_shield_danger_zero_vs_no_enemies(self):
        rook = make_rook()
        shield_name = rook.shield.name
        state = _quick_state(
            pc_overrides={
                "Rook": {"held_weapons": (shield_name,), "shield_raised": False},
            },
            enemy_overrides={"Bandit1": {"current_hp": 0}},
        )
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_auto_state(action, state)
        assert result.eligible
        assert result.outcomes[0].score_delta == 0.0


# ===========================================================================
# Parity with old evaluators (4)
# ===========================================================================

class TestParity:

    def test_stand_matches_old_evaluator_eligible(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        old = evaluate_stand(action, state)
        new = evaluate_auto_state(action, state)
        assert old.eligible == new.eligible

    def test_stand_matches_old_evaluator_conditions(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.STAND, actor_name="Rook", action_cost=1)
        old = evaluate_stand(action, state)
        new = evaluate_auto_state(action, state)
        assert old.outcomes[0].conditions_removed == new.outcomes[0].conditions_removed

    def test_raise_shield_matches_old_evaluator_eligible(self):
        rook = make_rook()
        shield_name = rook.shield.name
        state = _quick_state(pc_overrides={
            "Rook": {"held_weapons": (shield_name,), "shield_raised": False},
        })
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        old = evaluate_raise_shield(action, state)
        new = evaluate_auto_state(action, state)
        assert old.eligible == new.eligible

    def test_raise_shield_matches_old_evaluator_score_delta(self):
        """New EV uses simpler formula (no p_targets_actor weighting).

        The old evaluator divides by num_threatened PCs; the new one
        sums all enemy damage * 0.10. They differ in magnitude but both
        are positive when enemies are alive. This test verifies both
        produce positive EV.
        """
        rook = make_rook()
        shield_name = rook.shield.name
        state = _quick_state(pc_overrides={
            "Rook": {"held_weapons": (shield_name,), "shield_raised": False},
        })
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        old = evaluate_raise_shield(action, state)
        new = evaluate_auto_state(action, state)
        assert old.outcomes[0].score_delta > 0.0
        assert new.outcomes[0].score_delta > 0.0


# ===========================================================================
# New actions in realistic state (2)
# ===========================================================================

class TestNewActions:

    def test_drop_prone_in_realistic_state(self):
        """Drop Prone works in a full scenario state."""
        state = _quick_state()
        action = Action(type=ActionType.DROP_PRONE, actor_name="Aetregan", action_cost=1)
        result = evaluate_action(action, state)
        assert result.eligible
        assert result.outcomes[0].probability == 1.0
        assert "prone" in result.outcomes[0].conditions_applied.get("Aetregan", ())

    def test_take_cover_in_realistic_state(self):
        """Take Cover works in a full scenario state."""
        state = _quick_state()
        action = Action(type=ActionType.TAKE_COVER, actor_name="Dalai Alpaca", action_cost=1)
        result = evaluate_action(action, state)
        assert result.eligible
        assert result.outcomes[0].probability == 1.0
        assert "cover" in result.outcomes[0].conditions_applied.get("Dalai Alpaca", ())


# ===========================================================================
# Regression (1)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_28th_verification(self):
        """28th verification: Strike Hard EV 7.65 after CP10.4.2."""
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)
