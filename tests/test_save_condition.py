"""Tests for save-condition chassis (CP10.4.5).

Covers: _enemy_avg_damage, condition_ev, evaluate_condition_spell,
parity with old _evaluate_condition_spell, and regression.
"""

import pytest

from pf2e.actions import (
    Action,
    ActionType,
    _evaluate_condition_spell,
)
from pf2e.save_condition import (
    _enemy_avg_damage,
    condition_ev,
    evaluate_condition_spell,
)
from pf2e.combat_math import class_dc, enumerate_d20_outcomes
from pf2e.spells import SPELL_REGISTRY, SpellDefinition, SpellPattern
from pf2e.types import DamageType, SaveType
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState
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


def _make_enemy_snap(
    name: str = "TestEnemy",
    damage_dice: str = "1d8",
    damage_bonus: int = 3,
    num_attacks: int = 2,
    current_hp: int = 20,
    will_save: int = 2,
) -> EnemySnapshot:
    return EnemySnapshot(
        name=name, position=(5, 7), current_hp=current_hp, max_hp=20,
        ac=15, saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: will_save},
        attack_bonus=7, damage_dice=damage_dice, damage_bonus=damage_bonus,
        num_attacks_per_turn=num_attacks, perception_bonus=4,
        off_guard=False, prone=False, actions_remaining=3,
    )


def _fear_defn() -> SpellDefinition:
    return SPELL_REGISTRY["fear"]


def _fear_action(target: str = "Bandit1") -> Action:
    return Action(
        type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
        action_cost=2, target_name=target, tactic_name="fear",
    )


# ===========================================================================
# _enemy_avg_damage (3)
# ===========================================================================

class TestEnemyAvgDamage:

    def test_standard_1d8(self):
        """1d8 + 3 → 4.5 + 3 = 7.5"""
        e = _make_enemy_snap(damage_dice="1d8", damage_bonus=3)
        assert _enemy_avg_damage(e) == pytest.approx(7.5)

    def test_multi_dice_2d6(self):
        """2d6 + 2 → 7.0 + 2 = 9.0"""
        e = _make_enemy_snap(damage_dice="2d6", damage_bonus=2)
        assert _enemy_avg_damage(e) == pytest.approx(9.0)

    def test_no_dice(self):
        """Empty damage_dice → damage_bonus only."""
        e = _make_enemy_snap(damage_dice="", damage_bonus=5)
        assert _enemy_avg_damage(e) == pytest.approx(5.0)


# ===========================================================================
# condition_ev (5)
# ===========================================================================

class TestConditionEV:

    def test_frightened_level1(self):
        """frightened 1: 1 * 0.05 * 2 attacks * 7.5 avg * 2 = 1.5"""
        e = _make_enemy_snap(damage_dice="1d8", damage_bonus=3, num_attacks=2)
        ev = condition_ev("frightened", 1, e)
        assert ev == pytest.approx(1.5)

    def test_frightened_level2_is_double_level1(self):
        e = _make_enemy_snap()
        ev1 = condition_ev("frightened", 1, e)
        ev2 = condition_ev("frightened", 2, e)
        assert ev2 == pytest.approx(ev1 * 2)

    def test_fleeing_known(self):
        """fleeing: 2 attacks * 7.5 avg = 15.0"""
        e = _make_enemy_snap(damage_dice="1d8", damage_bonus=3, num_attacks=2)
        ev = condition_ev("fleeing", 1, e)
        assert ev == pytest.approx(15.0)

    def test_empty_condition_zero(self):
        e = _make_enemy_snap()
        assert condition_ev("", 0, e) == 0.0

    def test_unknown_condition_zero(self):
        e = _make_enemy_snap()
        assert condition_ev("stunned", 1, e) == 0.0


# ===========================================================================
# evaluate_condition_spell (8)
# ===========================================================================

class TestEvaluateConditionSpell:

    def test_fear_ineligible_dead_target(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"current_hp": 0}})
        result = evaluate_condition_spell(
            _fear_action(), state, state.pcs["Dalai Alpaca"], _fear_defn())
        assert not result.eligible

    def test_fear_ineligible_missing_target(self):
        state = _quick_state()
        action = _fear_action(target="NonExistent")
        result = evaluate_condition_spell(
            action, state, state.pcs["Dalai Alpaca"], _fear_defn())
        assert not result.eligible

    def test_fear_eligible_four_outcomes(self):
        state = _quick_state()
        result = evaluate_condition_spell(
            _fear_action(), state, state.pcs["Dalai Alpaca"], _fear_defn())
        assert result.eligible
        assert len(result.outcomes) == 4

    def test_fear_probabilities_sum_to_one(self):
        state = _quick_state()
        result = evaluate_condition_spell(
            _fear_action(), state, state.pcs["Dalai Alpaca"], _fear_defn())
        total = sum(o.probability for o in result.outcomes)
        assert total == pytest.approx(1.0)

    def test_fear_crit_success_no_conditions(self):
        state = _quick_state()
        result = evaluate_condition_spell(
            _fear_action(), state, state.pcs["Dalai Alpaca"], _fear_defn())
        # First outcome is crit_success (order follows _DEGREE_PREFIXES)
        crit_s = result.outcomes[0]
        assert "crit_success" in crit_s.description
        assert crit_s.conditions_applied == {}
        assert crit_s.score_delta == 0.0

    def test_fear_crit_failure_two_conditions(self):
        state = _quick_state()
        result = evaluate_condition_spell(
            _fear_action(), state, state.pcs["Dalai Alpaca"], _fear_defn())
        # crit_failure is second in _DEGREE_PREFIXES order
        crit_f = result.outcomes[1]
        assert "crit_failure" in crit_f.description
        conds = crit_f.conditions_applied["Bandit1"]
        assert "frightened_3" in conds
        assert "fleeing_1" in conds

    def test_fear_success_score_positive(self):
        state = _quick_state()
        result = evaluate_condition_spell(
            _fear_action(), state, state.pcs["Dalai Alpaca"], _fear_defn())
        # success outcome (third, after crit_success and crit_failure)
        success_outcome = [o for o in result.outcomes if "success:" in o.description
                           and "crit" not in o.description][0]
        assert success_outcome.score_delta > 0

    def test_fear_crit_failure_score_highest(self):
        state = _quick_state()
        result = evaluate_condition_spell(
            _fear_action(), state, state.pcs["Dalai Alpaca"], _fear_defn())
        scores = [o.score_delta for o in result.outcomes]
        crit_f = result.outcomes[1]  # crit_failure
        assert crit_f.score_delta == max(scores)


# ===========================================================================
# Parity with old evaluator (4)
# ===========================================================================

class TestParity:
    """Verify new chassis matches old _evaluate_condition_spell for Bandit1.

    NOTE: For multi-dice targets (e.g. "2d6"), flee_ev will differ because
    the old code has a bug that ignores dice count. Parity tests use the
    standard scenario (Bandit1 "1d8") where both computations agree.
    """

    def _both_results(self):
        state = _quick_state()
        action = _fear_action()
        actor = state.pcs["Dalai Alpaca"]
        defn = _fear_defn()
        old = _evaluate_condition_spell(action, state, actor, defn)
        new = evaluate_condition_spell(action, state, actor, defn)
        return old, new

    def test_parity_outcome_count(self):
        old, new = self._both_results()
        assert len(old.outcomes) == len(new.outcomes)

    def test_parity_probabilities(self):
        old, new = self._both_results()
        # Old code outputs in order: crit_s, success, failure, crit_failure
        # New code outputs in _DEGREE_PREFIXES order: crit_s, crit_f, success, failure
        # Match by probability value (each degree has unique probability)
        old_probs = sorted(o.probability for o in old.outcomes)
        new_probs = sorted(o.probability for o in new.outcomes)
        for op, np_ in zip(old_probs, new_probs):
            assert op == pytest.approx(np_, abs=EV_TOLERANCE)

    def test_parity_score_deltas(self):
        old, new = self._both_results()
        old_scores = sorted(o.score_delta for o in old.outcomes)
        new_scores = sorted(o.score_delta for o in new.outcomes)
        for os_, ns_ in zip(old_scores, new_scores):
            assert os_ == pytest.approx(ns_, abs=EV_TOLERANCE)

    def test_parity_conditions_applied(self):
        old, new = self._both_results()
        # Compare condition sets per outcome, matched by score_delta
        old_by_score = {round(o.score_delta, 2): o.conditions_applied for o in old.outcomes}
        new_by_score = {round(o.score_delta, 2): o.conditions_applied for o in new.outcomes}
        for score_key in old_by_score:
            assert score_key in new_by_score
            old_conds = old_by_score[score_key]
            new_conds = new_by_score[score_key]
            # Both should have same targets with same condition tuples
            assert set(old_conds.keys()) == set(new_conds.keys())
            for target_name in old_conds:
                assert set(old_conds[target_name]) == set(new_conds[target_name])


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_31st_verification(self):
        """31st verification: Strike Hard EV 7.65 after CP10.4.5."""
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
        """Tactical Takedown 55% prone unchanged after CP10.4.5."""
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
