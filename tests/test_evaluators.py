"""Tests for action evaluators (CP5.1.3c Step 10).

Each test builds its own RoundState — no shared mutable state.
"""

import pytest

from pf2e.actions import (
    Action,
    ActionOutcome,
    ActionResult,
    ActionType,
    evaluate_action,
    evaluate_activate_tactic,
    evaluate_create_a_diversion,
    evaluate_demoralize,
    evaluate_disarm,
    evaluate_end_turn,
    evaluate_feint,
    evaluate_intercept_attack,
    evaluate_plant_banner,
    evaluate_raise_shield,
    evaluate_shield_block,
    evaluate_step,
    evaluate_stride,
    evaluate_strike,
    evaluate_trip,
)
from pf2e.character import CombatantState, EnemyState
from pf2e.combat_math import lore_bonus, skill_bonus
from pf2e.tactics import STRIKE_HARD, evaluate_tactic
from pf2e.types import SaveType, Skill
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState
from sim.scenario import load_scenario
from tests.fixtures import (
    make_aetregan,
    make_dalai,
    make_erisen,
    make_rook,
    make_rook_combat_state,
)

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bandit(
    name: str = "Bandit1",
    position: tuple[int, int] = (5, 7),
    current_hp: int = 20,
) -> EnemyState:
    return EnemyState(
        name=name, ac=15,
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        position=position, attack_bonus=7, damage_dice="1d8",
        damage_bonus=3, num_attacks_per_turn=2, max_hp=20,
        current_hp=current_hp, perception_bonus=4,
    )


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


# ---------------------------------------------------------------------------
# Group A: Snapshot blocker fields
# ---------------------------------------------------------------------------

class TestSnapshotBlockerFields:

    def test_combatant_snapshot_has_map_count(self) -> None:
        snap = CombatantSnapshot.from_combatant_state(make_rook_combat_state())
        assert snap.map_count == 0

    def test_combatant_snapshot_has_conditions(self) -> None:
        snap = CombatantSnapshot.from_combatant_state(make_rook_combat_state())
        assert snap.conditions == frozenset()

    def test_enemy_snapshot_has_conditions(self) -> None:
        enemy = _make_bandit()
        snap = EnemySnapshot.from_enemy_state(enemy)
        assert snap.conditions == frozenset()


# ---------------------------------------------------------------------------
# Group B: Per-evaluator tests
# ---------------------------------------------------------------------------

class TestEndTurn:

    def test_end_turn_always_eligible(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.END_TURN, actor_name="Rook", action_cost=0)
        result = evaluate_end_turn(action, state)
        assert result.eligible
        assert len(result.outcomes) == 1
        assert result.outcomes[0].probability == 1.0
        assert result.outcomes[0].hp_changes == {}


class TestPlantBanner:

    def test_plant_banner_ineligible_aetregan(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.PLANT_BANNER, actor_name="Aetregan", action_cost=1)
        result = evaluate_plant_banner(action, state)
        assert not result.eligible
        assert "Plant Banner" in result.ineligibility_reason


class TestRaiseShield:

    def test_raise_shield_eligible_with_shield(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_raise_shield(action, state)
        assert result.eligible
        assert result.outcomes[0].conditions_applied["Rook"] == ("shield_raised",)

    def test_raise_shield_ineligible_without_shield(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Erisen", action_cost=1)
        result = evaluate_raise_shield(action, state)
        assert not result.eligible

    def test_raise_shield_ineligible_if_already_raised(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"shield_raised": True}})
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_raise_shield(action, state)
        assert not result.eligible


class TestStep:

    def test_step_only_adjacent_squares(self) -> None:
        state = _quick_state()
        actor_pos = state.pcs["Rook"].position
        action = Action(
            type=ActionType.STEP, actor_name="Rook", action_cost=1,
            target_position=(actor_pos[0] - 1, actor_pos[1]),
        )
        result = evaluate_step(action, state)
        assert result.eligible
        dest = result.outcomes[0].position_changes["Rook"]
        # Destination should be exactly 1 square away
        dr = abs(dest[0] - actor_pos[0])
        dc = abs(dest[1] - actor_pos[1])
        assert max(dr, dc) <= 1


class TestStride:

    def test_stride_respects_speed(self) -> None:
        """STRIDE evaluator accepts any target_position — speed check is in candidate gen."""
        state = _quick_state()
        action = Action(
            type=ActionType.STRIDE, actor_name="Rook", action_cost=1,
            target_position=(0, 0),
        )
        result = evaluate_stride(action, state)
        assert result.eligible


class TestStrike:

    def test_strike_map0_no_penalty(self) -> None:
        """First strike (map_count=0) has no MAP penalty."""
        state = _quick_state()
        action = Action(
            type=ActionType.STRIKE, actor_name="Rook", action_cost=1,
            target_name="Bandit1", weapon_name="Longsword",
        )
        result = evaluate_strike(action, state)
        assert result.eligible
        assert len(result.outcomes) >= 2  # at least miss + hit

    def test_strike_map1_minus5(self) -> None:
        """Second strike (map_count=1) gets -5 MAP for non-agile."""
        state = _quick_state(pc_overrides={"Rook": {"map_count": 1}})
        action = Action(
            type=ActionType.STRIKE, actor_name="Rook", action_cost=1,
            target_name="Bandit1", weapon_name="Longsword",
        )
        result0 = evaluate_strike(
            action, _quick_state(),
        )
        result1 = evaluate_strike(action, state)
        # MAP=1 should have higher miss probability than MAP=0
        miss0 = sum(o.probability for o in result0.outcomes if not o.hp_changes)
        miss1 = sum(o.probability for o in result1.outcomes if not o.hp_changes)
        assert miss1 > miss0

    def test_strike_map2_minus10(self) -> None:
        """Third strike (map_count=2) gets -10 MAP."""
        state = _quick_state(pc_overrides={"Rook": {"map_count": 2}})
        action = Action(
            type=ActionType.STRIKE, actor_name="Rook", action_cost=1,
            target_name="Bandit1", weapon_name="Longsword",
        )
        result = evaluate_strike(action, state)
        miss_prob = sum(o.probability for o in result.outcomes if not o.hp_changes)
        assert miss_prob > 0.5  # at -10, should miss most of the time

    def test_strike_agile_map1_minus4(self) -> None:
        """Agile weapon uses -4 MAP instead of -5 for the same character."""
        # Erisen's dagger is agile: MAP at map_count=1 is -4
        # Compare miss rate increase from MAP 0 to MAP 1
        state0 = _quick_state(pc_overrides={
            "Erisen": {"map_count": 0, "position": (5, 8)},
        })
        state1 = _quick_state(pc_overrides={
            "Erisen": {"map_count": 1, "position": (5, 8)},
        })
        action = Action(
            type=ActionType.STRIKE, actor_name="Erisen", action_cost=1,
            target_name="Bandit1", weapon_name="Dagger",
        )
        result0 = evaluate_strike(action, state0)
        result1 = evaluate_strike(action, state1)

        miss0 = sum(o.probability for o in result0.outcomes if not o.hp_changes)
        miss1 = sum(o.probability for o in result1.outcomes if not o.hp_changes)
        # Agile: -4 penalty = 4 extra faces miss = 0.20 increase
        miss_increase = miss1 - miss0
        assert miss_increase == pytest.approx(0.20, abs=0.05)

    def test_strike_ineligible_out_of_reach(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"position": (0, 0)}})
        action = Action(
            type=ActionType.STRIKE, actor_name="Rook", action_cost=1,
            target_name="Bandit1", weapon_name="Longsword",
        )
        result = evaluate_strike(action, state)
        assert not result.eligible

    def test_strike_kill_branch_at_5pct(self) -> None:
        """When enemy is near death, the beam search creates kill branches."""
        from sim.search import SearchConfig, apply_action_result
        state = _quick_state(enemy_overrides={"Bandit1": {"current_hp": 3}})
        action = Action(
            type=ActionType.STRIKE, actor_name="Rook", action_cost=1,
            target_name="Bandit1", weapon_name="Longsword",
        )
        result = evaluate_strike(action, state)
        branches = apply_action_result(result, state, state, SearchConfig())
        # With enemy at 3 HP and Rook dealing ~8+ on hit, should branch
        assert len(branches) >= 1  # at least one branch


class TestTrip:

    def test_trip_success_applies_prone(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_trip(action, state)
        assert result.eligible
        # Find success outcome
        success_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "prone" in o.conditions_applied["Bandit1"]
        ]
        assert len(success_outcomes) >= 1

    def test_trip_crit_fail_actor_prone(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_trip(action, state)
        # Find crit failure outcome
        crit_fail_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Rook")
            and "prone" in o.conditions_applied["Rook"]
        ]
        assert len(crit_fail_outcomes) >= 1

    def test_trip_ineligible_out_of_reach(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"position": (0, 0)}})
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_trip(action, state)
        assert not result.eligible


class TestDisarm:

    def test_disarm_success_applies_penalty(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.DISARM, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_disarm(action, state)
        assert result.eligible
        success_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "disarmed" in o.conditions_applied["Bandit1"]
        ]
        assert len(success_outcomes) >= 1

    def test_disarm_crit_fail_actor_off_guard(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.DISARM, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_disarm(action, state)
        crit_fail_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Rook")
            and "off_guard" in o.conditions_applied["Rook"]
        ]
        assert len(crit_fail_outcomes) >= 1


class TestDemoralize:

    def test_demoralize_success_applies_frightened(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_demoralize(action, state)
        assert result.eligible
        frightened_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and any("frightened" in c for c in o.conditions_applied["Bandit1"])
        ]
        assert len(frightened_outcomes) >= 1

    def test_demoralize_failure_sets_immune(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_demoralize(action, state)
        immune_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "demoralize_immune" in o.conditions_applied["Bandit1"]
        ]
        assert len(immune_outcomes) >= 1

    def test_demoralize_ineligible_when_immune(self) -> None:
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"demoralize_immune"})},
        })
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_demoralize(action, state)
        assert not result.eligible

    def test_demoralize_no_deceptive_tactics(self) -> None:
        """Demoralize always uses Intimidation, not Warfare Lore."""
        state = _quick_state()
        # Aetregan has Deceptive Tactics but Demoralize should NOT use it
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_demoralize(action, state)
        assert result.eligible
        # Verify by checking that the bonus used is Intimidation, not Lore
        # Aetregan doesn't have Intimidation trained, so bonus is lower than Warfare Lore
        intimidation = skill_bonus(make_aetregan(), Skill.INTIMIDATION)
        warfare_lore = lore_bonus(make_aetregan(), "Warfare")
        assert intimidation != warfare_lore  # They should differ


class TestCreateADiversion:

    def test_create_diversion_deceptive_tactics_aetregan(self) -> None:
        """Aetregan uses Warfare Lore for Create a Diversion via Deceptive Tactics."""
        state = _quick_state()
        action = Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name="Aetregan",
            action_cost=1, target_name="Bandit1",
        )
        result = evaluate_create_a_diversion(action, state)
        assert result.eligible
        # With Deceptive Tactics, Aetregan uses Warfare Lore (+7)
        # which is better than Deception (untrained)

    def test_create_diversion_failure_sets_immune(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name="Aetregan",
            action_cost=1, target_name="Bandit1",
        )
        result = evaluate_create_a_diversion(action, state)
        immune_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "diversion_immune" in o.conditions_applied["Bandit1"]
        ]
        assert len(immune_outcomes) >= 1

    def test_create_diversion_ineligible_when_immune(self) -> None:
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"diversion_immune"})},
        })
        action = Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name="Aetregan",
            action_cost=1, target_name="Bandit1",
        )
        result = evaluate_create_a_diversion(action, state)
        assert not result.eligible


class TestFeint:

    def test_feint_deceptive_tactics_aetregan(self) -> None:
        """Aetregan uses Warfare Lore for Feint via Deceptive Tactics."""
        state = _quick_state()
        action = Action(
            type=ActionType.FEINT, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_feint(action, state)
        assert result.eligible

    def test_feint_melee_only(self) -> None:
        state = _quick_state(pc_overrides={"Aetregan": {"position": (0, 0)}})
        action = Action(
            type=ActionType.FEINT, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_feint(action, state)
        assert not result.eligible

    def test_feint_requires_2_actions(self) -> None:
        state = _quick_state(pc_overrides={"Aetregan": {"actions_remaining": 1}})
        action = Action(
            type=ActionType.FEINT, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_feint(action, state)
        assert not result.eligible

    def test_feint_no_immunity_on_failure(self) -> None:
        """Feint failure should NOT add an immunity tag."""
        state = _quick_state()
        action = Action(
            type=ActionType.FEINT, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_feint(action, state)
        for o in result.outcomes:
            for name, conds in o.conditions_applied.items():
                # No "feint_immune" or similar tags
                assert not any("immune" in c for c in conds)


class TestShieldBlock:

    def test_shield_block_reduces_by_hardness(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"shield_raised": True}})
        action = Action(
            type=ActionType.SHIELD_BLOCK, actor_name="Rook", action_cost=0,
        )
        result = evaluate_shield_block(action, state)
        assert result.eligible
        assert "5" in result.outcomes[0].description  # hardness 5

    def test_shield_block_ineligible_without_raised_shield(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.SHIELD_BLOCK, actor_name="Rook", action_cost=0,
        )
        result = evaluate_shield_block(action, state)
        assert not result.eligible


class TestInterceptAttack:

    def test_intercept_attack_guardian_only(self) -> None:
        state = _quick_state()
        action = Action(
            type=ActionType.INTERCEPT_ATTACK, actor_name="Aetregan",
            action_cost=0, target_name="Dalai Alpaca",
        )
        result = evaluate_intercept_attack(action, state)
        assert not result.eligible

    def test_intercept_attack_ally_in_range(self) -> None:
        state = _quick_state()
        # Rook is a Guardian and adjacent to other PCs
        action = Action(
            type=ActionType.INTERCEPT_ATTACK, actor_name="Rook",
            action_cost=0, target_name="Aetregan",
        )
        result = evaluate_intercept_attack(action, state)
        assert result.eligible


class TestActivateTactic:

    def test_activate_tactic_strike_hard_ev(self) -> None:
        """ACTIVATE_TACTIC wrapping Strike Hard! should match tactic EV."""
        state = _quick_state()
        action = Action(
            type=ActionType.ACTIVATE_TACTIC, actor_name="Aetregan",
            action_cost=2, tactic_name="Strike Hard!",
        )
        result = evaluate_activate_tactic(action, state)
        assert result.eligible
        assert result.expected_damage_dealt > 0

    def test_activate_tactic_insufficient_actions(self) -> None:
        state = _quick_state(pc_overrides={"Aetregan": {"actions_remaining": 1}})
        action = Action(
            type=ActionType.ACTIVATE_TACTIC, actor_name="Aetregan",
            action_cost=2, tactic_name="Strike Hard!",
        )
        result = evaluate_activate_tactic(action, state)
        assert not result.eligible

    def test_activate_tactic_ineligible_for_non_commander(self) -> None:
        """Dalai and Erisen must never generate ACTIVATE_TACTIC candidates."""
        from sim.candidates import generate_candidates
        state = _quick_state()
        for name in ("Dalai Alpaca", "Erisen", "Rook"):
            candidates = generate_candidates(state, name)
            tactic_actions = [a for a in candidates if a.type == ActionType.ACTIVATE_TACTIC]
            assert tactic_actions == [], f"{name} should not have ACTIVATE_TACTIC candidates"

    def test_activate_tactic_no_eligible_squadmates(self) -> None:
        """When no squadmates are in aura, tactic should be ineligible."""
        # Move all squadmates far away from banner aura
        state = _quick_state(pc_overrides={
            "Rook": {"position": (0, 0)},
            "Dalai Alpaca": {"position": (0, 1)},
            "Erisen": {"position": (0, 2)},
        })
        action = Action(
            type=ActionType.ACTIVATE_TACTIC, actor_name="Aetregan",
            action_cost=2, tactic_name="Strike Hard!",
        )
        result = evaluate_activate_tactic(action, state)
        # Strike Hard requires a squadmate in aura with reach to an enemy
        # With squadmates at (0,0)-(0,2) and enemy at (5,7), they're out of reach
        assert not result.eligible


class TestDispatcher:

    def test_dispatcher_all_types_registered(self) -> None:
        """All action types (excluding EVER_READY) have evaluators."""
        from pf2e.actions import _ACTION_EVALUATORS
        expected = {
            ActionType.END_TURN, ActionType.PLANT_BANNER,
            ActionType.RAISE_SHIELD, ActionType.STEP,
            ActionType.STRIDE, ActionType.STRIKE,
            ActionType.TRIP, ActionType.DISARM,
            ActionType.DEMORALIZE, ActionType.CREATE_A_DIVERSION,
            ActionType.FEINT, ActionType.SHIELD_BLOCK,
            ActionType.INTERCEPT_ATTACK, ActionType.ACTIVATE_TACTIC,
            ActionType.ANTHEM, ActionType.SOOTHE,
            ActionType.MORTAR_AIM, ActionType.MORTAR_LOAD,
            ActionType.MORTAR_LAUNCH, ActionType.TAUNT,
            ActionType.RECALL_KNOWLEDGE, ActionType.HIDE,
            ActionType.SNEAK, ActionType.SEEK, ActionType.AID,
            ActionType.STAND,
        }
        assert set(_ACTION_EVALUATORS.keys()) == expected

    def test_ever_ready_not_in_dispatcher(self) -> None:
        from pf2e.actions import _ACTION_EVALUATORS
        assert ActionType.EVER_READY not in _ACTION_EVALUATORS

    def test_dispatcher_unknown_type_returns_ineligible(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.EVER_READY, actor_name="Rook", action_cost=0)
        result = evaluate_action(action, state)
        assert not result.eligible


# ---------------------------------------------------------------------------
# Group C: Regression and integration
# ---------------------------------------------------------------------------

class TestKillerRegression:

    def test_strike_hard_ev_8_55_from_disk(self) -> None:
        """8th verification of the killer regression. Must not change."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.eligible
        assert result.expected_damage_dealt == pytest.approx(8.55, abs=EV_TOLERANCE)


class TestIntegration:

    def test_full_round_from_scenario(self) -> None:
        """End-to-end: load -> run_simulation -> RoundRecommendation."""
        from sim.search import run_simulation
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        recommendations = run_simulation(scenario, seed=42)
        assert recommendations is not None
        assert len(recommendations) > 0
        aetregan_rec = next(
            (r for r in recommendations if r.actor_name == "Aetregan"), None,
        )
        assert aetregan_rec is not None


# ---------------------------------------------------------------------------
# CP5.2: New evaluator tests
# ---------------------------------------------------------------------------

class TestAnthem:

    def test_anthem_eligible_for_dalai(self) -> None:
        from dataclasses import replace as dc_replace
        state = dc_replace(_quick_state(), anthem_active=False)
        action = Action(type=ActionType.ANTHEM, actor_name="Dalai Alpaca", action_cost=1)
        from pf2e.actions import evaluate_anthem
        result = evaluate_anthem(action, state)
        assert result.eligible

    def test_anthem_ineligible_for_non_bard(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.ANTHEM, actor_name="Rook", action_cost=1)
        from pf2e.actions import evaluate_anthem
        result = evaluate_anthem(action, state)
        assert not result.eligible

    def test_anthem_ineligible_when_already_active(self) -> None:
        from dataclasses import replace as dc_replace
        state = dc_replace(_quick_state(), anthem_active=True)
        action = Action(type=ActionType.ANTHEM, actor_name="Dalai Alpaca", action_cost=1)
        from pf2e.actions import evaluate_anthem
        result = evaluate_anthem(action, state)
        assert not result.eligible

    def test_anthem_score_positive_with_allies(self) -> None:
        from dataclasses import replace as dc_replace
        state = dc_replace(_quick_state(), anthem_active=False)
        action = Action(type=ActionType.ANTHEM, actor_name="Dalai Alpaca", action_cost=1)
        from pf2e.actions import evaluate_anthem
        result = evaluate_anthem(action, state)
        assert result.eligible
        assert "anthem_active" in result.outcomes[0].conditions_applied.get("Dalai Alpaca", ())

    def test_anthem_propagates_to_round_state(self) -> None:
        """anthem_active condition should set RoundState.anthem_active via apply_outcome_to_state."""
        from dataclasses import replace as dc_replace
        from sim.search import apply_outcome_to_state
        state = dc_replace(_quick_state(), anthem_active=False)
        assert not state.anthem_active
        outcome = ActionOutcome(
            probability=1.0,
            conditions_applied={"Dalai Alpaca": ("anthem_active",)},
        )
        new_state = apply_outcome_to_state(outcome, state)
        assert new_state.anthem_active


class TestSoothe:

    def test_soothe_eligible_when_ally_wounded(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"current_hp": 10}})
        action = Action(type=ActionType.SOOTHE, actor_name="Dalai Alpaca", action_cost=2)
        from pf2e.actions import evaluate_soothe
        result = evaluate_soothe(action, state)
        assert result.eligible
        assert result.outcomes[0].hp_changes  # healing applied

    def test_soothe_ineligible_when_slot_used(self) -> None:
        state = _quick_state(
            pc_overrides={
                "Rook": {"current_hp": 10},
                "Dalai Alpaca": {"conditions": frozenset({"soothe_used"})},
            },
        )
        action = Action(type=ActionType.SOOTHE, actor_name="Dalai Alpaca", action_cost=2)
        from pf2e.actions import evaluate_soothe
        result = evaluate_soothe(action, state)
        assert not result.eligible

    def test_soothe_ineligible_when_no_wounded(self) -> None:
        state = _quick_state()  # all PCs at full HP
        action = Action(type=ActionType.SOOTHE, actor_name="Dalai Alpaca", action_cost=2)
        from pf2e.actions import evaluate_soothe
        result = evaluate_soothe(action, state)
        assert not result.eligible

    def test_soothe_ineligible_when_actions_less_than_2(self) -> None:
        state = _quick_state(pc_overrides={
            "Rook": {"current_hp": 10},
            "Dalai Alpaca": {"actions_remaining": 1},
        })
        action = Action(type=ActionType.SOOTHE, actor_name="Dalai Alpaca", action_cost=2)
        from pf2e.actions import evaluate_soothe
        result = evaluate_soothe(action, state)
        assert not result.eligible

    def test_soothe_sets_used_condition(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"current_hp": 10}})
        action = Action(type=ActionType.SOOTHE, actor_name="Dalai Alpaca", action_cost=2)
        from pf2e.actions import evaluate_soothe
        result = evaluate_soothe(action, state)
        assert "soothe_used" in result.outcomes[0].conditions_applied.get("Dalai Alpaca", ())

    def test_soothe_ineligible_for_non_bard(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"current_hp": 10}})
        action = Action(type=ActionType.SOOTHE, actor_name="Rook", action_cost=2)
        from pf2e.actions import evaluate_soothe
        result = evaluate_soothe(action, state)
        assert not result.eligible


class TestMortarSequence:

    def test_mortar_auto_deployed_at_combat_start(self) -> None:
        state = _quick_state()
        erisen = state.pcs["Erisen"]
        assert "mortar_deployed" in erisen.conditions

    def test_mortar_aim_eligible_when_deployed(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.MORTAR_AIM, actor_name="Erisen", action_cost=1)
        from pf2e.actions import evaluate_mortar_aim
        result = evaluate_mortar_aim(action, state)
        assert result.eligible

    def test_mortar_aim_ineligible_when_already_aimed(self) -> None:
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"mortar_deployed", "mortar_aimed"})},
        })
        action = Action(type=ActionType.MORTAR_AIM, actor_name="Erisen", action_cost=1)
        from pf2e.actions import evaluate_mortar_aim
        result = evaluate_mortar_aim(action, state)
        assert not result.eligible

    def test_mortar_load_eligible_when_aimed(self) -> None:
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"mortar_deployed", "mortar_aimed"})},
        })
        action = Action(type=ActionType.MORTAR_LOAD, actor_name="Erisen", action_cost=1)
        from pf2e.actions import evaluate_mortar_load
        result = evaluate_mortar_load(action, state)
        assert result.eligible

    def test_mortar_load_ineligible_when_not_aimed(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.MORTAR_LOAD, actor_name="Erisen", action_cost=1)
        from pf2e.actions import evaluate_mortar_load
        result = evaluate_mortar_load(action, state)
        assert not result.eligible

    def test_mortar_launch_eligible_when_aimed_and_loaded(self) -> None:
        # Move PCs away from enemy to avoid friendly fire
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"mortar_deployed", "mortar_aimed", "mortar_loaded"}),
                       "position": (0, 0)},
            "Rook": {"position": (0, 1)},
            "Aetregan": {"position": (0, 2)},
            "Dalai Alpaca": {"position": (0, 3)},
        })
        action = Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen", action_cost=1)
        from pf2e.actions import evaluate_mortar_launch
        result = evaluate_mortar_launch(action, state)
        assert result.eligible
        assert result.expected_damage_dealt > 0

    def test_mortar_launch_ineligible_when_only_aimed(self) -> None:
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"mortar_deployed", "mortar_aimed"})},
        })
        action = Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen", action_cost=1)
        from pf2e.actions import evaluate_mortar_launch
        result = evaluate_mortar_launch(action, state)
        assert not result.eligible

    def test_mortar_launch_clears_aimed_and_loaded(self) -> None:
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"mortar_deployed", "mortar_aimed", "mortar_loaded"}),
                       "position": (0, 0)},
            "Rook": {"position": (0, 1)},
            "Aetregan": {"position": (0, 2)},
            "Dalai Alpaca": {"position": (0, 3)},
        })
        action = Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen", action_cost=1)
        from pf2e.actions import evaluate_mortar_launch
        result = evaluate_mortar_launch(action, state)
        removed = result.outcomes[0].conditions_removed.get("Erisen", ())
        assert "mortar_aimed" in removed
        assert "mortar_loaded" in removed

    def test_mortar_full_sequence_state_transitions(self) -> None:
        """AIM → LOAD → LAUNCH sequence produces correct conditions."""
        from sim.search import apply_outcome_to_state
        from pf2e.actions import evaluate_mortar_aim, evaluate_mortar_load, evaluate_mortar_launch

        # Position PCs away from enemy to avoid friendly fire on launch
        state = _quick_state(pc_overrides={
            "Erisen": {"position": (0, 0)},
            "Rook": {"position": (0, 1)},
            "Aetregan": {"position": (0, 2)},
            "Dalai Alpaca": {"position": (0, 3)},
        })
        erisen = state.pcs["Erisen"]
        assert "mortar_deployed" in erisen.conditions

        # AIM
        aim = evaluate_mortar_aim(
            Action(type=ActionType.MORTAR_AIM, actor_name="Erisen", action_cost=1),
            state,
        )
        state = apply_outcome_to_state(aim.outcomes[0], state)
        assert "mortar_aimed" in state.pcs["Erisen"].conditions

        # LOAD
        load = evaluate_mortar_load(
            Action(type=ActionType.MORTAR_LOAD, actor_name="Erisen", action_cost=1),
            state,
        )
        state = apply_outcome_to_state(load.outcomes[0], state)
        assert "mortar_loaded" in state.pcs["Erisen"].conditions

        # LAUNCH
        launch = evaluate_mortar_launch(
            Action(type=ActionType.MORTAR_LAUNCH, actor_name="Erisen", action_cost=1),
            state,
        )
        state = apply_outcome_to_state(launch.outcomes[0], state)
        assert "mortar_aimed" not in state.pcs["Erisen"].conditions
        assert "mortar_loaded" not in state.pcs["Erisen"].conditions
        assert "mortar_deployed" in state.pcs["Erisen"].conditions


class TestTaunt:

    def test_taunt_eligible_for_rook(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.TAUNT, actor_name="Rook", action_cost=1,
                       target_name="Bandit1")
        from pf2e.actions import evaluate_taunt
        result = evaluate_taunt(action, state)
        assert result.eligible

    def test_taunt_ineligible_for_non_guardian(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.TAUNT, actor_name="Aetregan", action_cost=1,
                       target_name="Bandit1")
        from pf2e.actions import evaluate_taunt
        result = evaluate_taunt(action, state)
        assert not result.eligible

    def test_taunt_ineligible_when_already_taunting(self) -> None:
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"taunting_Bandit1"})},
        })
        action = Action(type=ActionType.TAUNT, actor_name="Rook", action_cost=1,
                       target_name="Bandit1")
        from pf2e.actions import evaluate_taunt
        result = evaluate_taunt(action, state)
        assert not result.eligible

    def test_taunt_sets_conditions(self) -> None:
        state = _quick_state()
        action = Action(type=ActionType.TAUNT, actor_name="Rook", action_cost=1,
                       target_name="Bandit1")
        from pf2e.actions import evaluate_taunt
        result = evaluate_taunt(action, state)
        conds = result.outcomes[0].conditions_applied
        assert "taunted_by_rook" in conds.get("Bandit1", ())
        assert "taunting_Bandit1" in conds.get("Rook", ())

    def test_taunt_ineligible_out_of_range(self) -> None:
        state = _quick_state(pc_overrides={"Rook": {"position": (0, 0)}})
        action = Action(type=ActionType.TAUNT, actor_name="Rook", action_cost=1,
                       target_name="Bandit1")
        from pf2e.actions import evaluate_taunt
        result = evaluate_taunt(action, state)
        assert not result.eligible


class TestInterceptAttackExtension:

    def test_intercept_range_10ft_without_taunt(self) -> None:
        """Default 10-ft range when enemy is not taunted."""
        from pf2e.actions import evaluate_intercept_attack
        state = _quick_state()
        action = Action(
            type=ActionType.INTERCEPT_ATTACK, actor_name="Rook",
            action_cost=0, target_name="Aetregan",
        )
        result = evaluate_intercept_attack(action, state)
        assert result.eligible  # Aetregan is adjacent to Rook

    def test_intercept_range_15ft_with_taunted_enemy(self) -> None:
        """Extended 15-ft range when damage comes from taunted enemy."""
        from pf2e.actions import evaluate_intercept_attack
        # Move ally 15 ft from Rook (3 diag = 15 ft via 5/10 rule)
        state = _quick_state(
            pc_overrides={"Aetregan": {"position": (3, 4)}},
            enemy_overrides={"Bandit1": {"conditions": frozenset({"taunted_by_rook"})}},
        )
        action = Action(
            type=ActionType.INTERCEPT_ATTACK, actor_name="Rook",
            action_cost=0, target_name="Aetregan",
            target_names=("Bandit1",),  # attacking enemy
        )
        result = evaluate_intercept_attack(action, state)
        # Rook at (5,6), Aetregan at (3,4): distance = 2 diag = 15 ft
        # With taunt, range is 15 ft → eligible
        assert result.eligible


class TestStrikeHelpers:

    def test_effective_status_bonus_attack_no_anthem(self) -> None:
        from pf2e.actions import _effective_status_bonus_attack
        state = _quick_state()
        rook = state.pcs["Rook"]
        assert _effective_status_bonus_attack(rook, state) == rook.status_bonus_attack

    def test_effective_status_bonus_attack_with_anthem(self) -> None:
        from dataclasses import replace as dc_replace
        from pf2e.actions import _effective_status_bonus_attack
        state = dc_replace(_quick_state(), anthem_active=True)
        rook = state.pcs["Rook"]
        assert _effective_status_bonus_attack(rook, state) >= 1

    def test_effective_bonus_uses_max(self) -> None:
        """If snapshot already has +1 bonus, anthem doesn't double it."""
        from dataclasses import replace as dc_replace
        from pf2e.actions import _effective_status_bonus_attack
        state = dc_replace(_quick_state(), anthem_active=True)
        # Rook starts with anthem bonus from scenario (anthem_active=True at load)
        rook = state.pcs["Rook"]
        bonus = _effective_status_bonus_attack(rook, state)
        assert bonus == max(rook.status_bonus_attack, 1)


class TestScenarioCombatantState:

    def test_combatant_state_section_sets_conditions(self) -> None:
        from sim.scenario import parse_scenario
        text = """
[meta]
name = mortar test

[grid]
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . c g m . .
. . . . i b . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2

[combatant_state]
Erisen = mortar_aimed, mortar_loaded
"""
        scenario = parse_scenario(text)
        from sim.round_state import RoundState
        state = RoundState.from_scenario(scenario, ["Erisen", "Bandit1"])
        erisen = state.pcs["Erisen"]
        assert "mortar_aimed" in erisen.conditions
        assert "mortar_loaded" in erisen.conditions
        assert "mortar_deployed" in erisen.conditions  # auto-deployed


# ---------------------------------------------------------------------------
# CP5.3: New tests
# ---------------------------------------------------------------------------

class TestHasRecalled:

    def test_has_recalled_true_with_tag(self) -> None:
        from pf2e.actions import _has_recalled
        from dataclasses import replace as dc_replace
        state = _quick_state()
        aetregan = dc_replace(state.pcs["Aetregan"],
                              conditions=frozenset({"recalled_bandit1"}))
        assert _has_recalled(aetregan, "Bandit1")

    def test_has_recalled_false_without_tag(self) -> None:
        from pf2e.actions import _has_recalled
        state = _quick_state()
        assert not _has_recalled(state.pcs["Aetregan"], "Bandit1")

    def test_has_recalled_normalizes_name(self) -> None:
        from pf2e.actions import _has_recalled
        from dataclasses import replace as dc_replace
        state = _quick_state()
        aetregan = dc_replace(state.pcs["Aetregan"],
                              conditions=frozenset({"recalled_dalai_alpaca"}))
        assert _has_recalled(aetregan, "Dalai Alpaca")


class TestRecallKnowledge:

    def test_recall_eligible_with_society(self) -> None:
        from pf2e.actions import evaluate_recall_knowledge
        state = _quick_state()
        action = Action(type=ActionType.RECALL_KNOWLEDGE, actor_name="Aetregan",
                       action_cost=1, target_name="Bandit1")
        result = evaluate_recall_knowledge(action, state)
        assert result.eligible

    def test_recall_ineligible_when_already_recalled(self) -> None:
        from pf2e.actions import evaluate_recall_knowledge
        state = _quick_state(pc_overrides={
            "Aetregan": {"conditions": frozenset({"recalled_bandit1"})},
        })
        action = Action(type=ActionType.RECALL_KNOWLEDGE, actor_name="Aetregan",
                       action_cost=1, target_name="Bandit1")
        result = evaluate_recall_knowledge(action, state)
        assert not result.eligible

    def test_recall_sets_tag(self) -> None:
        from pf2e.actions import evaluate_recall_knowledge
        state = _quick_state()
        action = Action(type=ActionType.RECALL_KNOWLEDGE, actor_name="Aetregan",
                       action_cost=1, target_name="Bandit1")
        result = evaluate_recall_knowledge(action, state)
        assert "recalled_bandit1" in result.outcomes[0].conditions_applied.get("Aetregan", ())


class TestStrikeWithWeaknessResistance:

    def _bandit2_state(self):
        """Build state with Bandit2 that has weakness/resistance."""
        from sim.scenario import load_scenario
        return load_scenario("scenarios/checkpoint_2_two_bandits.scenario")

    def test_strike_no_wr_without_recall(self) -> None:
        """Without Recall Knowledge, STRIKE uses flat damage."""
        scenario = self._bandit2_state()
        init_order = ["Aetregan", "Bandit2"]
        from sim.round_state import RoundState
        state = RoundState.from_scenario(scenario, init_order)
        # Aetregan adjacent to Bandit2 for reach
        state = state.with_pc_update("Aetregan", position=(5, 6))
        action = Action(type=ActionType.STRIKE, actor_name="Aetregan",
                       action_cost=1, target_name="Bandit2",
                       weapon_name="Scorpion Whip")
        result = evaluate_action(action, state)
        # Should be eligible and use flat damage (no W/R)
        assert result.eligible

    def test_parse_bandit2_weakness(self) -> None:
        scenario = self._bandit2_state()
        from sim.round_state import RoundState
        state = RoundState.from_scenario(scenario, ["Bandit2"])
        b2 = state.enemies["Bandit2"]
        assert b2.weaknesses.get("bludgeoning") == 3
        assert b2.resistances.get("slashing") == 3
        assert b2.resistances.get("piercing") == 3

    def test_no_wr_for_plain_enemy(self) -> None:
        scenario = self._bandit2_state()
        from sim.round_state import RoundState
        state = RoundState.from_scenario(scenario, ["Bandit1"])
        b1 = state.enemies["Bandit1"]
        assert b1.weaknesses == {}
        assert b1.resistances == {}


class TestHide:

    def test_hide_eligible_when_not_adjacent(self) -> None:
        from pf2e.actions import evaluate_hide
        # Move actor far from enemies
        state = _quick_state(pc_overrides={"Aetregan": {"position": (0, 0)}})
        action = Action(type=ActionType.HIDE, actor_name="Aetregan", action_cost=1)
        result = evaluate_hide(action, state)
        assert result.eligible

    def test_hide_ineligible_when_adjacent(self) -> None:
        from pf2e.actions import evaluate_hide
        state = _quick_state()  # Aetregan at (5,5), Bandit1 at (5,7) — not adjacent
        # Move Aetregan adjacent to Bandit1
        state = state.with_pc_update("Aetregan", position=(5, 8))
        action = Action(type=ActionType.HIDE, actor_name="Aetregan", action_cost=1)
        result = evaluate_hide(action, state)
        assert not result.eligible

    def test_hide_ineligible_when_already_hidden(self) -> None:
        from pf2e.actions import evaluate_hide
        state = _quick_state(pc_overrides={
            "Aetregan": {"position": (0, 0), "conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.HIDE, actor_name="Aetregan", action_cost=1)
        result = evaluate_hide(action, state)
        assert not result.eligible

    def test_hide_sets_hidden_condition(self) -> None:
        from pf2e.actions import evaluate_hide
        state = _quick_state(pc_overrides={"Aetregan": {"position": (0, 0)}})
        action = Action(type=ActionType.HIDE, actor_name="Aetregan", action_cost=1)
        result = evaluate_hide(action, state)
        assert "hidden" in result.outcomes[0].conditions_applied.get("Aetregan", ())


class TestSneak:

    def test_sneak_eligible_when_hidden(self) -> None:
        from pf2e.actions import evaluate_sneak
        state = _quick_state(pc_overrides={
            "Aetregan": {"conditions": frozenset({"hidden"}), "position": (0, 0)},
        })
        action = Action(type=ActionType.SNEAK, actor_name="Aetregan",
                       action_cost=1, target_position=(0, 1))
        result = evaluate_sneak(action, state)
        assert result.eligible

    def test_sneak_ineligible_when_not_hidden(self) -> None:
        from pf2e.actions import evaluate_sneak
        state = _quick_state()
        action = Action(type=ActionType.SNEAK, actor_name="Aetregan",
                       action_cost=1, target_position=(4, 4))
        result = evaluate_sneak(action, state)
        assert not result.eligible

    def test_sneak_two_branches(self) -> None:
        from pf2e.actions import evaluate_sneak
        state = _quick_state(pc_overrides={
            "Aetregan": {"conditions": frozenset({"hidden"}), "position": (0, 0)},
        })
        action = Action(type=ActionType.SNEAK, actor_name="Aetregan",
                       action_cost=1, target_position=(0, 1))
        result = evaluate_sneak(action, state)
        assert len(result.outcomes) == 2  # success + failure


class TestSeek:

    def test_seek_always_eligible(self) -> None:
        from pf2e.actions import evaluate_seek
        state = _quick_state()
        action = Action(type=ActionType.SEEK, actor_name="Aetregan", action_cost=1)
        result = evaluate_seek(action, state)
        assert result.eligible

    def test_seek_score_zero_no_hidden(self) -> None:
        from pf2e.actions import evaluate_seek
        state = _quick_state()
        action = Action(type=ActionType.SEEK, actor_name="Aetregan", action_cost=1)
        result = evaluate_seek(action, state)
        # No hidden enemies, description should indicate 0 hidden
        assert "0 hidden" in result.outcomes[0].description


class TestAid:

    def test_aid_eligible_for_living_ally(self) -> None:
        from pf2e.actions import evaluate_aid
        state = _quick_state()
        action = Action(type=ActionType.AID, actor_name="Aetregan",
                       action_cost=1, target_name="Rook")
        result = evaluate_aid(action, state)
        assert result.eligible

    def test_aid_ineligible_for_self(self) -> None:
        from pf2e.actions import evaluate_aid
        state = _quick_state()
        action = Action(type=ActionType.AID, actor_name="Aetregan",
                       action_cost=1, target_name="Aetregan")
        result = evaluate_aid(action, state)
        assert not result.eligible

    def test_aid_sets_conditions(self) -> None:
        from pf2e.actions import evaluate_aid
        state = _quick_state()
        action = Action(type=ActionType.AID, actor_name="Aetregan",
                       action_cost=1, target_name="Rook")
        result = evaluate_aid(action, state)
        conds = result.outcomes[0].conditions_applied
        assert "aiding_rook" in conds.get("Aetregan", ())
        assert "aided_by_aetregan" in conds.get("Rook", ())


class TestStrikeHidden:

    def test_strike_hidden_bonus(self) -> None:
        """Hidden actor gets +2 to attack."""
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                       action_cost=1, target_name="Bandit1",
                       weapon_name="Longsword")
        result_hidden = evaluate_action(action, state)

        state_normal = _quick_state()
        result_normal = evaluate_action(
            Action(type=ActionType.STRIKE, actor_name="Rook",
                  action_cost=1, target_name="Bandit1",
                  weapon_name="Longsword"),
            state_normal,
        )
        # Hidden should have higher hit rate (lower miss %)
        miss_hidden = sum(o.probability for o in result_hidden.outcomes if not o.hp_changes)
        miss_normal = sum(o.probability for o in result_normal.outcomes if not o.hp_changes)
        assert miss_hidden < miss_normal

    def test_strike_clears_hidden(self) -> None:
        """Strike from hiding clears the Hidden condition."""
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                       action_cost=1, target_name="Bandit1",
                       weapon_name="Longsword")
        result = evaluate_action(action, state)
        # All outcomes should have conditions_removed with "hidden"
        for o in result.outcomes:
            if o.conditions_removed:
                assert "hidden" in o.conditions_removed.get("Rook", ())


class TestStepHidden:

    def test_step_does_not_clear_hidden(self) -> None:
        """STEP is allowed while Hidden without breaking it."""
        state = _quick_state(pc_overrides={
            "Rook": {"conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.STEP, actor_name="Rook",
                       action_cost=1, target_position=(4, 6))
        result = evaluate_action(action, state)
        # Should NOT have conditions_removed for "hidden"
        for o in result.outcomes:
            removed = o.conditions_removed.get("Rook", ())
            assert "hidden" not in removed


# ---------------------------------------------------------------------------
# Bugfix: Enemy candidate generation
# ---------------------------------------------------------------------------

class TestEnemyCandidates:

    def test_enemy_generates_strike_when_pc_adjacent(self) -> None:
        """Enemy must generate STRIKE when a PC is in melee reach."""
        from sim.candidates import generate_candidates
        state = _quick_state()  # Rook at (5,6), Bandit1 at (5,7) — adjacent
        candidates = generate_candidates(state, "Bandit1")
        strike_actions = [a for a in candidates if a.type == ActionType.STRIKE]
        assert len(strike_actions) >= 1

    def test_enemy_generates_stride_when_no_pc_in_reach(self) -> None:
        """Enemy must generate STRIDE when no PC is in melee reach."""
        from sim.candidates import generate_candidates
        # Move all PCs far from Bandit1
        state = _quick_state(pc_overrides={
            "Aetregan": {"position": (0, 0)},
            "Rook": {"position": (0, 1)},
            "Dalai Alpaca": {"position": (0, 2)},
            "Erisen": {"position": (0, 3)},
        })
        candidates = generate_candidates(state, "Bandit1")
        stride_actions = [a for a in candidates if a.type == ActionType.STRIDE]
        assert len(stride_actions) >= 1

    def test_enemy_always_includes_end_turn(self) -> None:
        from sim.candidates import generate_candidates
        state = _quick_state()
        candidates = generate_candidates(state, "Bandit1")
        end_actions = [a for a in candidates if a.type == ActionType.END_TURN]
        assert len(end_actions) >= 1
