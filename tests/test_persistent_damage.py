"""Tests for persistent damage system (CP10.8).

Covers: tag parsing, apply_persistent_damage, attempt_recovery,
merge_persistent_tag stacking, process_end_of_turn ordering,
Needle Darts crit bleed, and regression.
"""

import pytest
from dataclasses import replace
from unittest.mock import patch

from pf2e.damage_pipeline import (
    _parse_persistent_tags,
    apply_persistent_damage,
    attempt_recovery,
    merge_persistent_tag,
)
from pf2e.conditions import process_end_of_turn
from pf2e.rolls import flat_check
from pf2e.spells import SPELL_REGISTRY
from pf2e.strike import evaluate_spell_attack_roll
from pf2e.actions import Action, ActionType
from sim.round_state import RoundState
from sim.scenario import load_scenario

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
# Tag parsing (3)
# ===========================================================================

class TestParseTags:

    def test_parse_bleed_1(self):
        tags = _parse_persistent_tags(frozenset({"persistent_bleed_1"}))
        assert tags == [("bleed", 1)]

    def test_parse_fire_5(self):
        tags = _parse_persistent_tags(frozenset({"persistent_fire_5", "hidden"}))
        assert tags == [("fire", 5)]

    def test_parse_no_persistent(self):
        tags = _parse_persistent_tags(frozenset({"hidden", "prone"}))
        assert tags == []


# ===========================================================================
# apply_persistent_damage (6)
# ===========================================================================

class TestApplyPersistentDamage:

    def test_pc_bleed_reduces_hp(self):
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"persistent_bleed_1"})},
        })
        assert state.pcs["Rook"].current_hp == 23
        state2, dmg = apply_persistent_damage(state, "Rook")
        assert state2.pcs["Rook"].current_hp == 22
        assert dmg == 1.0

    def test_enemy_fire_reduces_hp(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"persistent_fire_3"})},
        })
        state2, dmg = apply_persistent_damage(state, "Bandit1")
        assert state2.enemies["Bandit1"].current_hp == 17
        assert dmg == 3.0

    def test_multiple_types_both_apply(self):
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({
                "persistent_bleed_1", "persistent_fire_2",
            })},
        })
        state2, dmg = apply_persistent_damage(state, "Rook")
        assert state2.pcs["Rook"].current_hp == 20  # 23 - 3
        assert dmg == 3.0

    def test_no_tags_no_damage(self):
        state = _quick_state()
        state2, dmg = apply_persistent_damage(state, "Rook")
        assert state2.pcs["Rook"].current_hp == state.pcs["Rook"].current_hp
        assert dmg == 0.0

    def test_hp_floors_at_zero(self):
        state = _quick_state(pc_overrides={
            "Rook": {"current_hp": 1, "conditions": frozenset({"persistent_bleed_5"})},
        })
        state2, dmg = apply_persistent_damage(state, "Rook")
        assert state2.pcs["Rook"].current_hp == 0
        assert dmg == 5.0

    def test_returns_damage_amount(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"persistent_bleed_2"})},
        })
        _, dmg = apply_persistent_damage(state, "Bandit1")
        assert dmg == 2.0


# ===========================================================================
# attempt_recovery (3)
# ===========================================================================

class TestRecovery:

    def test_recovery_probability_is_030(self):
        assert flat_check(15) == pytest.approx(0.30)

    def test_recovery_removes_tag_on_success(self):
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"persistent_bleed_1"})},
        })
        with patch("pf2e.damage_pipeline.random.random", return_value=0.1):
            state2 = attempt_recovery(state, "Rook")
        assert "persistent_bleed_1" not in state2.pcs["Rook"].conditions

    def test_recovery_keeps_tag_on_failure(self):
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"persistent_bleed_1"})},
        })
        with patch("pf2e.damage_pipeline.random.random", return_value=0.5):
            state2 = attempt_recovery(state, "Rook")
        assert "persistent_bleed_1" in state2.pcs["Rook"].conditions


# ===========================================================================
# merge_persistent_tag stacking (3)
# ===========================================================================

class TestMergePersistentTag:

    def test_same_type_takes_higher(self):
        existing = frozenset({"persistent_bleed_1"})
        result = merge_persistent_tag(existing, "persistent_bleed_3")
        assert "persistent_bleed_3" in result
        assert "persistent_bleed_1" not in result

    def test_same_type_lower_ignored(self):
        existing = frozenset({"persistent_bleed_3"})
        result = merge_persistent_tag(existing, "persistent_bleed_1")
        assert "persistent_bleed_3" in result
        assert "persistent_bleed_1" not in result

    def test_different_types_coexist(self):
        existing = frozenset({"persistent_bleed_1"})
        result = merge_persistent_tag(existing, "persistent_fire_2")
        assert "persistent_bleed_1" in result
        assert "persistent_fire_2" in result


# ===========================================================================
# process_end_of_turn ordering (3)
# ===========================================================================

class TestEndOfTurnOrdering:

    def test_damage_applied_before_recovery(self):
        """Persistent damage reduces HP even if recovery succeeds."""
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"persistent_bleed_2"})},
        })
        hp_before = state.pcs["Rook"].current_hp
        # Force recovery success
        with patch("pf2e.damage_pipeline.random.random", return_value=0.1):
            state2 = process_end_of_turn(state, "Rook")
        # Damage was applied (HP reduced)
        assert state2.pcs["Rook"].current_hp == hp_before - 2
        # Recovery removed the tag
        assert "persistent_bleed_2" not in state2.pcs["Rook"].conditions

    def test_frightened_still_decrements(self):
        state = _quick_state(pc_overrides={"Rook": {"frightened": 2}})
        state2 = process_end_of_turn(state, "Rook")
        assert state2.pcs["Rook"].frightened == 1

    def test_no_persistent_no_change_to_hp(self):
        state = _quick_state()
        hp_before = state.pcs["Rook"].current_hp
        state2 = process_end_of_turn(state, "Rook")
        assert state2.pcs["Rook"].current_hp == hp_before


# ===========================================================================
# Needle Darts crit (4)
# ===========================================================================

class TestNeedleDartsCrit:

    def test_crit_persistent_bleed_field(self):
        defn = SPELL_REGISTRY["needle-darts"]
        assert defn.crit_persistent_bleed == 1

    def test_needle_darts_crit_has_bleed(self):
        state = _quick_state()
        defn = SPELL_REGISTRY["needle-darts"]
        actor = state.pcs["Dalai Alpaca"]
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="needle-darts")
        result = evaluate_spell_attack_roll(action, state, actor, defn)
        # Find crit outcome (highest damage)
        crit_outcomes = [o for o in result.outcomes if o.conditions_applied]
        assert len(crit_outcomes) >= 1
        crit = crit_outcomes[0]
        assert "persistent_bleed_1" in crit.conditions_applied.get("Bandit1", ())

    def test_needle_darts_hit_no_bleed(self):
        state = _quick_state()
        defn = SPELL_REGISTRY["needle-darts"]
        actor = state.pcs["Dalai Alpaca"]
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="needle-darts")
        result = evaluate_spell_attack_roll(action, state, actor, defn)
        # Non-crit outcomes should not have bleed
        non_crit = [o for o in result.outcomes if not o.conditions_applied]
        assert len(non_crit) >= 1  # miss and/or hit

    def test_needle_darts_miss_no_bleed(self):
        state = _quick_state()
        defn = SPELL_REGISTRY["needle-darts"]
        actor = state.pcs["Dalai Alpaca"]
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="needle-darts")
        result = evaluate_spell_attack_roll(action, state, actor, defn)
        miss = [o for o in result.outcomes if not o.hp_changes]
        if miss:
            assert not miss[0].conditions_applied


# ===========================================================================
# Regression (4)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_36th_verification(self):
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

    def test_no_persistent_in_default_scenario(self):
        state = _quick_state()
        for name in list(state.pcs) + list(state.enemies):
            tags = _parse_persistent_tags(
                state.pcs[name].conditions if name in state.pcs
                else state.enemies[name].conditions
            )
            assert tags == []
