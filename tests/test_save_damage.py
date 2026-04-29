"""Tests for save-damage chassis (CP10.4.4).

Covers: basic_save_ev math, aoe_enemy_ev, aoe_friendly_fire_ev,
evaluate_save_damage_spell, mortar delegation, and regression.
"""

import pytest
from dataclasses import replace

from pf2e.actions import (
    Action,
    ActionType,
    evaluate_action,
    evaluate_mortar_launch,
    _evaluate_save_damage_spell,
)
from pf2e.save_damage import (
    aoe_enemy_ev,
    aoe_friendly_fire_ev,
    basic_save_ev,
    evaluate_save_damage_spell,
)
from pf2e.combat_math import class_dc, enumerate_d20_outcomes, save_bonus
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
    save_mod: int = 5,
    current_hp: int = 20,
) -> EnemySnapshot:
    return EnemySnapshot(
        name=name, position=(5, 7), current_hp=current_hp, max_hp=20,
        ac=15, saves={SaveType.REFLEX: save_mod, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        attack_bonus=7, damage_dice="1d8", damage_bonus=3,
        num_attacks_per_turn=2, perception_bonus=4,
        off_guard=False, prone=False, actions_remaining=3,
    )


# ===========================================================================
# basic_save_ev math (5)
# ===========================================================================

class TestBasicSaveEV:

    def test_known_value_mortar(self):
        """DC 17, save +5, 2d6 (avg 7.0) = 5.95.

        Hand-computed: d20 outcomes for +5 vs DC 17:
        crit_fail=2, fail=9, success=8, crit_success=1
        EV = (2/20)*14 + (9/20)*7 + (8/20)*3.5 + (1/20)*0 = 5.95
        """
        ev = basic_save_ev(dc=17, save_mod=5, base_dmg=7.0)
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)

    def test_crit_success_zero(self):
        """Very high save_mod → most outcomes are crit success → low EV."""
        ev = basic_save_ev(dc=10, save_mod=25, base_dmg=10.0)
        # Almost all faces crit-succeed → near 0
        assert ev < 1.0

    def test_crit_fail_double(self):
        """Very low save_mod → most outcomes are crit failure → high EV."""
        ev = basic_save_ev(dc=30, save_mod=-5, base_dmg=10.0)
        # Almost all faces crit-fail → near 20
        assert ev > 15.0

    def test_zero_base_damage(self):
        ev = basic_save_ev(dc=17, save_mod=5, base_dmg=0.0)
        assert ev == 0.0

    def test_dc_scaling(self):
        """Higher DC → higher EV (same save_mod)."""
        ev_low = basic_save_ev(dc=12, save_mod=5, base_dmg=7.0)
        ev_high = basic_save_ev(dc=20, save_mod=5, base_dmg=7.0)
        assert ev_high > ev_low


# ===========================================================================
# aoe_enemy_ev (4)
# ===========================================================================

class TestAoeEnemyEV:

    def test_single_target(self):
        e = _make_enemy_snap(save_mod=5)
        ev = aoe_enemy_ev(dc=17, save_type=SaveType.REFLEX, base_dmg=7.0,
                          enemies=[e])
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)

    def test_multi_target_sums(self):
        e1 = _make_enemy_snap(name="E1", save_mod=5)
        e2 = _make_enemy_snap(name="E2", save_mod=5)
        ev = aoe_enemy_ev(dc=17, save_type=SaveType.REFLEX, base_dmg=7.0,
                          enemies=[e1, e2])
        assert ev == pytest.approx(5.95 * 2, abs=EV_TOLERANCE)

    def test_skips_dead(self):
        alive = _make_enemy_snap(name="Alive", save_mod=5)
        dead = _make_enemy_snap(name="Dead", save_mod=5, current_hp=0)
        ev = aoe_enemy_ev(dc=17, save_type=SaveType.REFLEX, base_dmg=7.0,
                          enemies=[alive, dead])
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)

    def test_empty_list(self):
        ev = aoe_enemy_ev(dc=17, save_type=SaveType.REFLEX, base_dmg=7.0,
                          enemies=[])
        assert ev == 0.0


# ===========================================================================
# aoe_friendly_fire_ev (3)
# ===========================================================================

class TestAoeFriendlyFireEV:

    def test_one_ally(self):
        state = _quick_state()
        ally = state.pcs["Rook"]
        ev = aoe_friendly_fire_ev(dc=17, save_type=SaveType.REFLEX,
                                  base_dmg=7.0, allies_in_burst=[ally])
        assert ev > 0.0

    def test_no_allies(self):
        ev = aoe_friendly_fire_ev(dc=17, save_type=SaveType.REFLEX,
                                  base_dmg=7.0, allies_in_burst=[])
        assert ev == 0.0

    def test_dead_ally_skipped(self):
        state = _quick_state(pc_overrides={"Rook": {"current_hp": 0}})
        ally = state.pcs["Rook"]
        ev = aoe_friendly_fire_ev(dc=17, save_type=SaveType.REFLEX,
                                  base_dmg=7.0, allies_in_burst=[ally])
        assert ev == 0.0


# ===========================================================================
# evaluate_save_damage_spell (5)
# ===========================================================================

class TestSaveDamageSpell:

    def _make_defn(self) -> SpellDefinition:
        """Minimal save-for-damage spell definition."""
        return SpellDefinition(
            name="Test Spell", slug="test-spell",
            aon_url="", action_cost=2, rank=1,
            pattern=SpellPattern.SAVE_FOR_DAMAGE,
            traits=frozenset(), range_ft=30,
            damage_dice=2, damage_die="d6", damage_bonus=0,
            damage_type=DamageType.FIRE,
            save_type=SaveType.REFLEX, is_basic_save=True,
            scales_with_actions=False, uses_spell_slot=True,
            spell_slot_rank=1,
        )

    def test_ineligible_dead_target(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"current_hp": 0}})
        action = Action(type=ActionType.CAST_SPELL, actor_name="Erisen",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="test-spell")
        result = evaluate_save_damage_spell(action, state,
                                            state.pcs["Erisen"], self._make_defn())
        assert not result.eligible

    def test_ineligible_no_target(self):
        state = _quick_state()
        action = Action(type=ActionType.CAST_SPELL, actor_name="Erisen",
                        action_cost=2, target_name="NonExistent",
                        tactic_name="test-spell")
        result = evaluate_save_damage_spell(action, state,
                                            state.pcs["Erisen"], self._make_defn())
        assert not result.eligible

    def test_ev_correct(self):
        state = _quick_state()
        defn = self._make_defn()
        action = Action(type=ActionType.CAST_SPELL, actor_name="Erisen",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="test-spell")
        actor = state.pcs["Erisen"]
        result = evaluate_save_damage_spell(action, state, actor, defn)
        assert result.eligible
        # Verify EV matches basic_save_ev directly
        dc = class_dc(actor.character)
        save_mod = state.enemies["Bandit1"].saves.get(SaveType.REFLEX, 0)
        base_dmg = 2 * 3.5 + 0  # 2d6 avg
        expected_ev = basic_save_ev(dc, save_mod, base_dmg)
        actual_ev = abs(result.outcomes[0].hp_changes["Bandit1"])
        assert actual_ev == pytest.approx(expected_ev, abs=0.01)

    def test_probability_sum(self):
        state = _quick_state()
        action = Action(type=ActionType.CAST_SPELL, actor_name="Erisen",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="test-spell")
        result = evaluate_save_damage_spell(action, state,
                                            state.pcs["Erisen"], self._make_defn())
        assert len(result.outcomes) == 1
        assert result.outcomes[0].probability == 1.0

    def test_parity_with_old(self):
        """New evaluator matches old _evaluate_save_damage_spell."""
        state = _quick_state()
        defn = self._make_defn()
        action = Action(type=ActionType.CAST_SPELL, actor_name="Erisen",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="test-spell")
        actor = state.pcs["Erisen"]
        old = _evaluate_save_damage_spell(action, state, actor, defn)
        new = evaluate_save_damage_spell(action, state, actor, defn)
        assert old.eligible == new.eligible
        old_ev = abs(old.outcomes[0].hp_changes["Bandit1"])
        new_ev = abs(new.outcomes[0].hp_changes["Bandit1"])
        assert old_ev == pytest.approx(new_ev, abs=0.01)


# ===========================================================================
# Mortar delegation (5)
# ===========================================================================

class TestMortarDelegation:

    def _mortar_state(self, ally_adjacent=False):
        """State with Erisen aimed+loaded, optionally ally adjacent to enemy.

        Default scenario has Rook at (5,6) adjacent to Bandit1 at (5,7),
        so we move Rook away unless testing FF.
        """
        overrides = {
            "Erisen": {
                "conditions": frozenset({"mortar_deployed", "mortar_aimed", "mortar_loaded"}),
            },
        }
        if ally_adjacent:
            # Keep Rook adjacent to Bandit1 (default), move others away
            overrides["Aetregan"] = {"position": (5, 1)}
            overrides["Dalai Alpaca"] = {"position": (6, 1)}
        else:
            # Move all PCs away from enemies so no FF triggers
            overrides["Rook"] = {"position": (5, 2)}
            overrides["Aetregan"] = {"position": (5, 1)}
            overrides["Dalai Alpaca"] = {"position": (6, 1)}
        state = _quick_state(pc_overrides=overrides)
        return state

    def test_mortar_launch_works(self):
        state = self._mortar_state()
        action = Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen",
                        action_cost=1)
        result = evaluate_mortar_launch(action, state)
        assert result.eligible
        assert result.expected_damage_dealt > 0

    def test_mortar_ff_reduces_score(self):
        """With Rook adjacent to enemy, FF penalty appears in description.

        Single enemy + Rook FF makes score negative (Rook Reflex +3 < enemy +5),
        so we add a second enemy so enemy_score > ff_penalty.
        """
        extra = _make_enemy_snap(name="Bandit2", save_mod=5)
        state_no_ff = self._mortar_state(ally_adjacent=False)
        state_no_ff = replace(state_no_ff,
                              enemies={**state_no_ff.enemies, extra.name: extra})
        state_ff = self._mortar_state(ally_adjacent=True)
        state_ff = replace(state_ff,
                           enemies={**state_ff.enemies, extra.name: extra})
        action = Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen",
                        action_cost=1)
        r_no = evaluate_mortar_launch(action, state_no_ff)
        r_ff = evaluate_mortar_launch(action, state_ff)
        assert r_no.eligible
        assert r_ff.eligible
        # FF version has lower score shown in description
        assert "FF" in r_ff.outcomes[0].description

    def test_mortar_ff_exceeds_enemy_ineligible(self):
        """When many allies are in burst, friendly fire exceeds enemy damage."""
        state = _quick_state(pc_overrides={
            "Erisen": {
                "conditions": frozenset({"mortar_deployed", "mortar_aimed", "mortar_loaded"}),
            },
            # Put all PCs adjacent to enemy
            "Aetregan": {"position": (5, 6)},
            "Rook": {"position": (5, 8)},
            "Dalai Alpaca": {"position": (4, 7)},
        })
        action = Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen",
                        action_cost=1)
        result = evaluate_mortar_launch(action, state)
        assert not result.eligible
        assert "Friendly fire" in result.ineligibility_reason

    def test_mortar_parity(self):
        """Mortar launch EV matches basic_save_ev for known values."""
        state = self._mortar_state(ally_adjacent=False)
        action = Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen",
                        action_cost=1)
        result = evaluate_mortar_launch(action, state)
        # Verify enemy EV via basic_save_ev directly
        actor = state.pcs["Erisen"]
        dc = class_dc(actor.character)
        base_dmg = 2 * 3.5  # 2d6
        living = [e for e in state.enemies.values() if e.current_hp > 0]
        expected_ev = sum(
            basic_save_ev(dc, e.saves.get(SaveType.REFLEX, 0), base_dmg)
            for e in living
        )
        assert result.expected_damage_dealt == pytest.approx(expected_ev, abs=0.1)

    def test_mortar_chain_credit_unchanged(self):
        """AIM chain credit still works (uses expected_aoe_damage, not save_damage)."""
        from pf2e.actions import evaluate_mortar_aim
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"mortar_deployed"})},
        })
        action = Action(type=ActionType.MORTAR_AIM, actor_name="Erisen",
                        action_cost=1)
        result = evaluate_mortar_aim(action, state)
        assert result.eligible
        assert result.outcomes[0].score_delta > 0


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_30th_verification(self):
        """30th verification: Strike Hard EV 7.65 after CP10.4.4."""
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)

    def test_mortar_ev_5_95_direct(self):
        """Mortar EV 5.95 per target: DC 17, Reflex +5, 2d6 (avg 7.0)."""
        ev = basic_save_ev(dc=17, save_mod=5, base_dmg=7.0)
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)

    def test_prone_probability_55pct(self):
        """Tactical Takedown 55% prone unchanged after CP10.4.4."""
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
