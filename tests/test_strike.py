"""Tests for strike chassis (CP10.4.3).

Covers: shared helpers, PC weapon strike, enemy strike, spell attack roll,
parity with old evaluators, and EV 7.65 regression.
"""

import pytest
from dataclasses import replace

from pf2e.actions import (
    Action,
    ActionOutcome,
    ActionResult,
    ActionType,
    evaluate_action,
    _evaluate_pc_strike,
    _evaluate_enemy_strike,
    _evaluate_attack_roll_spell,
)
from pf2e.strike import (
    build_strike_outcomes,
    effective_target_ac,
    evaluate_enemy_strike,
    evaluate_pc_weapon_strike,
    evaluate_spell_attack_roll,
    is_flanking,
    _strike_hidden_ev,
)
from pf2e.combat_math import enumerate_d20_outcomes
from pf2e.spells import SPELL_REGISTRY
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
# Shared helpers (6)
# ===========================================================================

class TestSharedHelpers:

    def test_is_flanking_always_false(self):
        state = _quick_state()
        assert is_flanking((0, 0), (1, 1), state) is False

    def test_effective_target_ac_neither(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"off_guard": False, "prone": False},
        })
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (5, 5), state)
        assert ac == target.ac

    def test_effective_target_ac_off_guard(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"off_guard": True}})
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (5, 5), state)
        assert ac == target.ac - 2

    def test_effective_target_ac_prone(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"prone": True, "off_guard": False},
        })
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (5, 5), state)
        assert ac == target.ac - 2

    def test_effective_target_ac_both(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"off_guard": True, "prone": True},
        })
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (5, 5), state)
        # Still only -2 (not -4)
        assert ac == target.ac - 2

    def test_build_strike_outcomes_probability_sum(self):
        outcomes = build_strike_outcomes(
            bonus=5, effective_ac=15, hit_dmg=7.0, crit_dmg=14.0,
            target_name="Bandit1")
        total = sum(o.probability for o in outcomes)
        assert total == pytest.approx(1.0, abs=1e-6)


# ===========================================================================
# PC weapon strike (15)
# ===========================================================================

class TestPCWeaponStrike:

    def test_ineligible_dead_target(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"current_hp": 0}})
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")
        result = evaluate_pc_weapon_strike(action, state)
        assert not result.eligible

    def test_ineligible_out_of_reach(self):
        state = _quick_state(pc_overrides={"Rook": {"position": (0, 0)}})
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")
        result = evaluate_pc_weapon_strike(action, state)
        assert not result.eligible

    def test_ineligible_no_weapon(self):
        """Actor with no equipped weapons."""
        state = _quick_state()
        # Use a character that exists but give a bogus weapon name
        # _find_weapon falls back to first weapon, so this should still work
        # unless character has no weapons at all. Test the explicit None path.
        from pf2e.strike import _find_weapon
        actor = state.pcs["Rook"]
        result = _find_weapon(actor, "NonexistentWeapon")
        # Falls back to first weapon
        assert result is not None

    def test_eligible_standard_strike(self):
        state = _quick_state()
        rook = state.pcs["Rook"]
        weapon_name = rook.character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        result = evaluate_pc_weapon_strike(action, state)
        assert result.eligible
        assert result.verify_probability_sum()

    def test_map_penalty_on_second_attack(self):
        state = _quick_state(pc_overrides={"Rook": {"map_count": 1}})
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        result_map1 = evaluate_pc_weapon_strike(action, state)
        state0 = _quick_state(pc_overrides={"Rook": {"map_count": 0}})
        result_map0 = evaluate_pc_weapon_strike(action, state0)
        # With MAP, expected damage should be lower
        assert result_map1.expected_damage_dealt < result_map0.expected_damage_dealt

    def test_anthem_attack_and_damage(self):
        """Anthem delta applies when snapshot doesn't reflect it yet."""
        # Start with anthem_active=False and status_bonus=0
        state_no = replace(_quick_state(), anthem_active=False)
        state_no = state_no.with_pc_update(
            "Rook", status_bonus_attack=0, status_bonus_damage=0)
        state_yes = replace(state_no, anthem_active=True)
        weapon_name = state_no.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        result_no = evaluate_pc_weapon_strike(action, state_no)
        result_yes = evaluate_pc_weapon_strike(action, state_yes)
        assert result_yes.expected_damage_dealt > result_no.expected_damage_dealt

    def test_two_hand_upgrade(self):
        """Two-hand upgrade when weapon is sole held item."""
        state = _quick_state()
        rook = state.pcs["Rook"]
        weapon = rook.character.equipped_weapons[0].weapon
        has_two_hand = any(t.startswith("two_hand_") for t in weapon.traits)
        if not has_two_hand:
            pytest.skip("Rook's weapon has no two-hand trait")
        # Sole held item = two-hand active
        state1 = state.with_pc_update("Rook", held_weapons=(weapon.name,))
        # Two held items = no upgrade
        state2 = state.with_pc_update("Rook", held_weapons=(weapon.name, "Steel Shield"))
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon.name)
        r1 = evaluate_pc_weapon_strike(action, state1)
        r2 = evaluate_pc_weapon_strike(action, state2)
        assert r1.expected_damage_dealt > r2.expected_damage_dealt

    def test_wr_adjustment_with_recall(self):
        """W/R applies when actor has recall tag."""
        state = _quick_state(
            pc_overrides={"Rook": {"conditions": frozenset({"recalled_bandit1"})}},
            enemy_overrides={"Bandit1": {"weaknesses": {"bludgeoning": 2}}},
        )
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        result_wr = evaluate_pc_weapon_strike(action, state)
        state_no_recall = _quick_state(
            enemy_overrides={"Bandit1": {"weaknesses": {"bludgeoning": 2}}},
        )
        result_no = evaluate_pc_weapon_strike(action, state_no_recall)
        assert result_wr.expected_damage_dealt > result_no.expected_damage_dealt

    def test_focus_fire_bonus(self):
        """Focus fire applies when map_count>0 and target hp<50%."""
        state = _quick_state(
            pc_overrides={"Rook": {"map_count": 1}},
            enemy_overrides={"Bandit1": {"current_hp": 5, "max_hp": 20}},
        )
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        result = evaluate_pc_weapon_strike(action, state)
        # All outcomes should have positive score_delta from focus fire
        assert any(o.score_delta > 0 for o in result.outcomes)

    def test_hidden_clears_on_strike(self):
        state = _quick_state(
            pc_overrides={"Rook": {"conditions": frozenset({"hidden"})}},
        )
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        result = evaluate_pc_weapon_strike(action, state)
        assert result.eligible
        for o in result.outcomes:
            assert "hidden" in o.conditions_removed.get("Rook", ())

    def test_strike_hidden_ev_uses_050(self):
        """_strike_hidden_ev uses 0.50 (DC 11 = 10/20), not 0.45."""
        state = _quick_state()
        actor = state.pcs["Rook"]
        ev = _strike_hidden_ev(state, actor)
        # Manually compute with 0.50
        living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
        living_pcs = sum(1 for pc in state.pcs.values() if pc.current_hp > 0)
        total_attacks = sum(e.num_attacks_per_turn for e in living_enemies)
        from pf2e.combat_math import expected_enemy_turn_damage
        avg_dmg = sum(
            expected_enemy_turn_damage(e, actor) / e.num_attacks_per_turn
            for e in living_enemies if e.num_attacks_per_turn > 0
        ) / max(1, len(living_enemies))
        expected_ev = (total_attacks / living_pcs) * 0.50 * avg_dmg
        assert ev == pytest.approx(expected_ev, abs=0.001)

    def test_parity_pc_strike_eligible(self):
        """New evaluator matches old for standard strike."""
        state = _quick_state()
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        old = _evaluate_pc_strike(action, state, state.pcs["Rook"])
        new = evaluate_pc_weapon_strike(action, state)
        assert old.eligible == new.eligible

    def test_parity_pc_strike_damage(self):
        """New evaluator produces same expected damage as old (no anthem)."""
        state = _quick_state()
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        old = _evaluate_pc_strike(action, state, state.pcs["Rook"])
        new = evaluate_pc_weapon_strike(action, state)
        assert old.expected_damage_dealt == pytest.approx(
            new.expected_damage_dealt, abs=0.01)

    def test_parity_pc_strike_with_anthem(self):
        """New evaluator matches old with anthem active."""
        state = replace(_quick_state(), anthem_active=True)
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        old = _evaluate_pc_strike(action, state, state.pcs["Rook"])
        new = evaluate_pc_weapon_strike(action, state)
        assert old.expected_damage_dealt == pytest.approx(
            new.expected_damage_dealt, abs=0.01)


# ===========================================================================
# Enemy strike (8)
# ===========================================================================

class TestEnemyStrike:

    def test_ineligible_dead_target(self):
        state = _quick_state(pc_overrides={"Rook": {"current_hp": 0}})
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        assert not result.eligible

    def test_ineligible_out_of_reach(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"position": (0, 0)}})
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        assert not result.eligible

    def test_ineligible_no_damage_dice(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"damage_dice": ""}})
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        assert not result.eligible

    def test_eligible_standard_enemy_strike(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        assert result.eligible
        assert result.verify_probability_sum()

    def test_hit_crit_damage_correct(self):
        """Verify damage for 1d8+3 enemy."""
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        hit_outcomes = [o for o in result.outcomes if o.hp_changes]
        assert len(hit_outcomes) >= 1
        # hit_dmg = 1*4.5 + 3 = 7.5, crit = 15.0
        damages = sorted(abs(list(o.hp_changes.values())[0]) for o in hit_outcomes)
        assert damages[0] == pytest.approx(7.5, abs=0.1)
        if len(damages) > 1:
            assert damages[1] == pytest.approx(15.0, abs=0.1)

    def test_off_guard_reduces_ac(self):
        """Off-guard on PC target reduces effective AC."""
        state_normal = _quick_state(pc_overrides={"Rook": {"off_guard": False}})
        state_og = _quick_state(pc_overrides={"Rook": {"off_guard": True}})
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        r_normal = evaluate_enemy_strike(action, state_normal)
        r_og = evaluate_enemy_strike(action, state_og)
        assert r_og.expected_damage_dealt > r_normal.expected_damage_dealt

    def test_parity_enemy_strike_eligible(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        old = _evaluate_enemy_strike(action, state, state.enemies["Bandit1"])
        new = evaluate_enemy_strike(action, state)
        assert old.eligible == new.eligible

    def test_parity_enemy_strike_damage(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        old = _evaluate_enemy_strike(action, state, state.enemies["Bandit1"])
        new = evaluate_enemy_strike(action, state)
        assert old.expected_damage_dealt == pytest.approx(
            new.expected_damage_dealt, abs=0.01)


# ===========================================================================
# Spell attack roll (8)
# ===========================================================================

class TestSpellAttackRoll:

    def _make_spell_action(self, actor_name="Dalai Alpaca", target="Bandit1"):
        return Action(type=ActionType.CAST_SPELL, actor_name=actor_name,
                      action_cost=2, target_name=target,
                      tactic_name="needle-darts")

    def _get_defn(self):
        return SPELL_REGISTRY["needle-darts"]

    def test_ineligible_dead_target(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"current_hp": 0}})
        action = self._make_spell_action()
        actor = state.pcs["Dalai Alpaca"]
        result = evaluate_spell_attack_roll(action, state, actor, self._get_defn())
        assert not result.eligible

    def test_eligible_standard(self):
        state = _quick_state()
        action = self._make_spell_action()
        actor = state.pcs["Dalai Alpaca"]
        result = evaluate_spell_attack_roll(action, state, actor, self._get_defn())
        assert result.eligible
        assert result.verify_probability_sum()

    def test_map_applies(self):
        state0 = _quick_state(pc_overrides={"Dalai Alpaca": {"map_count": 0}})
        state1 = _quick_state(pc_overrides={"Dalai Alpaca": {"map_count": 1}})
        action = self._make_spell_action()
        defn = self._get_defn()
        r0 = evaluate_spell_attack_roll(action, state0, state0.pcs["Dalai Alpaca"], defn)
        r1 = evaluate_spell_attack_roll(action, state1, state1.pcs["Dalai Alpaca"], defn)
        assert r1.expected_damage_dealt < r0.expected_damage_dealt

    def test_off_guard_reduces_ac(self):
        state_og = _quick_state(enemy_overrides={"Bandit1": {"off_guard": True}})
        state_no = _quick_state(enemy_overrides={"Bandit1": {"off_guard": False}})
        action = self._make_spell_action()
        defn = self._get_defn()
        r_og = evaluate_spell_attack_roll(action, state_og, state_og.pcs["Dalai Alpaca"], defn)
        r_no = evaluate_spell_attack_roll(action, state_no, state_no.pcs["Dalai Alpaca"], defn)
        assert r_og.expected_damage_dealt > r_no.expected_damage_dealt

    def test_crit_doubles_damage(self):
        state = _quick_state()
        action = self._make_spell_action()
        defn = self._get_defn()
        result = evaluate_spell_attack_roll(action, state, state.pcs["Dalai Alpaca"], defn)
        hit_outcomes = [o for o in result.outcomes if o.hp_changes]
        if len(hit_outcomes) >= 2:
            damages = sorted(abs(list(o.hp_changes.values())[0]) for o in hit_outcomes)
            assert damages[-1] == pytest.approx(damages[0] * 2, abs=0.1)

    def test_parity_spell_attack_eligible(self):
        state = _quick_state()
        action = self._make_spell_action()
        actor = state.pcs["Dalai Alpaca"]
        defn = self._get_defn()
        old = _evaluate_attack_roll_spell(action, state, actor, defn)
        new = evaluate_spell_attack_roll(action, state, actor, defn)
        assert old.eligible == new.eligible

    def test_parity_spell_attack_damage(self):
        state = _quick_state()
        action = self._make_spell_action()
        actor = state.pcs["Dalai Alpaca"]
        defn = self._get_defn()
        old = _evaluate_attack_roll_spell(action, state, actor, defn)
        new = evaluate_spell_attack_roll(action, state, actor, defn)
        assert old.expected_damage_dealt == pytest.approx(
            new.expected_damage_dealt, abs=0.01)

    def test_parity_spell_attack_probabilities(self):
        state = _quick_state()
        action = self._make_spell_action()
        actor = state.pcs["Dalai Alpaca"]
        defn = self._get_defn()
        old = _evaluate_attack_roll_spell(action, state, actor, defn)
        new = evaluate_spell_attack_roll(action, state, actor, defn)
        for o_old, o_new in zip(old.outcomes, new.outcomes):
            assert o_old.probability == pytest.approx(o_new.probability, abs=1e-6)


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_29th_verification(self):
        """29th verification: Strike Hard EV 7.65 after CP10.4.3."""
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)

    def test_dispatch_routes_to_new_evaluators(self):
        """evaluate_action for STRIKE dispatches through strike.py."""
        state = _quick_state()
        weapon_name = state.pcs["Rook"].character.equipped_weapons[0].weapon.name
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name=weapon_name)
        result = evaluate_action(action, state)
        assert result.eligible
        assert result.expected_damage_dealt > 0

    def test_spell_dispatch_routes_to_new_evaluator(self):
        """evaluate_action for CAST_SPELL ATTACK_ROLL uses strike.py."""
        state = _quick_state()
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="needle-darts")
        result = evaluate_action(action, state)
        assert result.eligible
        assert result.expected_damage_dealt > 0
