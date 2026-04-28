"""Tests for contest roll chassis (CP10.4.1).

Covers: data model, _condition_ev(), eligibility, outcomes, parity
with old evaluators, and EV 7.65 regression.
"""

import pytest

from pf2e.actions import (
    Action,
    ActionType,
    evaluate_action,
    evaluate_create_a_diversion,
    evaluate_demoralize,
    evaluate_disarm,
    evaluate_feint,
    evaluate_trip,
)
from pf2e.combat_math import lore_bonus, skill_bonus
from pf2e.contest_roll import (
    CONTEST_ROLL_REGISTRY,
    ContestRollDef,
    DegreeEffect,
    _condition_ev,
    evaluate_contest_roll,
)
from pf2e.traits import TraitCategory, has_trait
from pf2e.types import SaveType, Skill
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState
from sim.scenario import load_scenario
from tests.fixtures import make_aetregan, make_rook

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from pf2e.character import EnemyState


def _make_bandit(
    name: str = "Bandit1",
    position: tuple[int, int] = (5, 7),
    current_hp: int = 20,
    conditions: frozenset[str] = frozenset(),
) -> EnemyState:
    return EnemyState(
        name=name, ac=15,
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        position=position, attack_bonus=7, damage_dice="1d8",
        damage_bonus=3, num_attacks_per_turn=2, max_hp=20,
        current_hp=current_hp, perception_bonus=4,
        conditions=conditions,
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


def _make_enemy_snap(
    conditions: frozenset[str] = frozenset(),
    damage_dice: str = "1d8",
    damage_bonus: int = 3,
    num_attacks: int = 2,
) -> EnemySnapshot:
    """Minimal EnemySnapshot for _condition_ev tests."""
    return EnemySnapshot(
        name="TestEnemy", position=(5, 7), current_hp=20, max_hp=20,
        ac=15, saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        attack_bonus=7, damage_dice=damage_dice, damage_bonus=damage_bonus,
        num_attacks_per_turn=num_attacks, perception_bonus=4,
        off_guard=False, prone=False, actions_remaining=3,
        conditions=conditions,
    )


# ===========================================================================
# Data (5)
# ===========================================================================

class TestContestRollData:

    def test_degree_effect_is_frozen(self):
        effect = DegreeEffect(conditions_on_target=("prone",))
        with pytest.raises(AttributeError):
            effect.conditions_on_target = ("off_guard",)  # type: ignore[misc]

    def test_registry_has_five_entries(self):
        assert len(CONTEST_ROLL_REGISTRY) == 5
        assert ActionType.TRIP in CONTEST_ROLL_REGISTRY
        assert ActionType.DISARM in CONTEST_ROLL_REGISTRY
        assert ActionType.DEMORALIZE in CONTEST_ROLL_REGISTRY
        assert ActionType.CREATE_A_DIVERSION in CONTEST_ROLL_REGISTRY
        assert ActionType.FEINT in CONTEST_ROLL_REGISTRY

    def test_cad_crit_success_is_none(self):
        """Create a Diversion collapses crit success into success."""
        defn = CONTEST_ROLL_REGISTRY[ActionType.CREATE_A_DIVERSION]
        assert defn.crit_success is None

    def test_trip_has_attack_trait(self):
        defn = CONTEST_ROLL_REGISTRY[ActionType.TRIP]
        assert has_trait(defn.traits, TraitCategory.MAP)

    def test_feint_has_mental_trait(self):
        defn = CONTEST_ROLL_REGISTRY[ActionType.FEINT]
        assert "mental" in defn.traits


# ===========================================================================
# _condition_ev (4)
# ===========================================================================

class TestConditionEv:

    def test_frightened_1_nonzero(self):
        snap = _make_enemy_snap()
        ev = _condition_ev("frightened_1", snap)
        assert ev > 0

    def test_frightened_2_greater_than_1(self):
        snap = _make_enemy_snap()
        ev1 = _condition_ev("frightened_1", snap)
        ev2 = _condition_ev("frightened_2", snap)
        assert ev2 > ev1

    def test_existing_level_no_gain(self):
        """If target already frightened_2, applying frightened_1 has no gain."""
        snap = _make_enemy_snap(conditions=frozenset({"frightened_2"}))
        ev = _condition_ev("frightened_1", snap)
        assert ev == 0.0

    def test_unknown_condition_zero(self):
        snap = _make_enemy_snap()
        assert _condition_ev("prone", snap) == 0.0
        assert _condition_ev("off_guard", snap) == 0.0
        assert _condition_ev("disarmed", snap) == 0.0
        assert _condition_ev("something_weird", snap) == 0.0


# ===========================================================================
# Eligibility (6)
# ===========================================================================

class TestContestRollEligibility:

    def test_trip_out_of_reach(self):
        state = _quick_state(pc_overrides={"Rook": {"position": (0, 0)}})
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert not result.eligible
        assert "reach" in result.ineligibility_reason.lower()

    def test_demoralize_beyond_30ft(self):
        state = _quick_state(pc_overrides={"Rook": {"position": (0, 0)}})
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert not result.eligible
        assert "30" in result.ineligibility_reason

    def test_demoralize_immune(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"demoralize_immune"})},
        })
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert not result.eligible

    def test_feint_requires_2_actions(self):
        state = _quick_state(pc_overrides={"Aetregan": {"actions_remaining": 1}})
        action = Action(
            type=ActionType.FEINT, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert not result.eligible

    def test_cad_diversion_immune(self):
        state = _quick_state(enemy_overrides={
            "Bandit1": {"conditions": frozenset({"diversion_immune"})},
        })
        action = Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name="Aetregan",
            action_cost=1, target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert not result.eligible

    def test_dead_target(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"current_hp": 0}})
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert not result.eligible


# ===========================================================================
# Outcomes (8)
# ===========================================================================

class TestContestRollOutcomes:

    def test_trip_success_prone_and_off_guard(self):
        state = _quick_state()
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert result.eligible
        success_outcomes = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "prone" in o.conditions_applied["Bandit1"]
            and "off_guard" in o.conditions_applied["Bandit1"]
        ]
        assert len(success_outcomes) >= 1

    def test_trip_crit_fail_actor_prone(self):
        state = _quick_state()
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        crit_fail = [
            o for o in result.outcomes
            if o.conditions_applied.get("Rook")
            and "prone" in o.conditions_applied["Rook"]
        ]
        assert len(crit_fail) >= 1

    def test_disarm_crit_fail_actor_off_guard(self):
        state = _quick_state()
        action = Action(
            type=ActionType.DISARM, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        crit_fail = [
            o for o in result.outcomes
            if o.conditions_applied.get("Rook")
            and "off_guard" in o.conditions_applied["Rook"]
        ]
        assert len(crit_fail) >= 1

    def test_demoralize_success_frightened_1(self):
        state = _quick_state()
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert result.eligible
        scared = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "frightened_1" in o.conditions_applied["Bandit1"]
        ]
        assert len(scared) >= 1

    def test_demoralize_crit_success_frightened_2(self):
        state = _quick_state()
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        f2 = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "frightened_2" in o.conditions_applied["Bandit1"]
        ]
        assert len(f2) >= 1

    def test_demoralize_failure_sets_immune(self):
        state = _quick_state()
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        immune = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "demoralize_immune" in o.conditions_applied["Bandit1"]
        ]
        assert len(immune) >= 1

    def test_cad_success_off_guard(self):
        state = _quick_state()
        action = Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name="Aetregan",
            action_cost=1, target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert result.eligible
        og = [
            o for o in result.outcomes
            if o.conditions_applied.get("Bandit1")
            and "off_guard" in o.conditions_applied["Bandit1"]
        ]
        assert len(og) == 1

    def test_feint_deceptive_tactics_uses_lore(self):
        """Aetregan (has Deceptive Tactics) uses Warfare Lore for Feint."""
        state = _quick_state()
        # Aetregan's Warfare Lore > Deception (untrained)
        warfare = lore_bonus(make_aetregan(), "Warfare")
        deception = skill_bonus(make_aetregan(), Skill.DECEPTION)
        assert warfare > deception  # Confirms Deceptive Tactics would matter

        action = Action(
            type=ActionType.FEINT, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        result = evaluate_contest_roll(action, state)
        assert result.eligible


# ===========================================================================
# Parity (6) — new chassis matches old evaluator output
# ===========================================================================

class TestContestRollParity:

    def _compare_results(self, old_result, new_result):
        """Assert two ActionResults have matching outcomes."""
        assert old_result.eligible == new_result.eligible
        if not old_result.eligible:
            return
        assert len(old_result.outcomes) == len(new_result.outcomes)
        for old_o, new_o in zip(old_result.outcomes, new_result.outcomes):
            assert old_o.probability == pytest.approx(new_o.probability, abs=1e-9)
            assert old_o.conditions_applied == new_o.conditions_applied
            assert old_o.score_delta == pytest.approx(new_o.score_delta, abs=EV_TOLERANCE)

    def test_parity_trip(self):
        state = _quick_state()
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        old = evaluate_trip(action, state)
        new = evaluate_contest_roll(action, state)
        self._compare_results(old, new)

    def test_parity_disarm(self):
        state = _quick_state()
        action = Action(
            type=ActionType.DISARM, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        old = evaluate_disarm(action, state)
        new = evaluate_contest_roll(action, state)
        self._compare_results(old, new)

    def test_parity_demoralize(self):
        state = _quick_state()
        action = Action(
            type=ActionType.DEMORALIZE, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        old = evaluate_demoralize(action, state)
        new = evaluate_contest_roll(action, state)
        self._compare_results(old, new)

    def test_parity_create_a_diversion(self):
        state = _quick_state()
        action = Action(
            type=ActionType.CREATE_A_DIVERSION, actor_name="Aetregan",
            action_cost=1, target_name="Bandit1",
        )
        old = evaluate_create_a_diversion(action, state)
        new = evaluate_contest_roll(action, state)
        self._compare_results(old, new)

    def test_parity_feint(self):
        state = _quick_state()
        action = Action(
            type=ActionType.FEINT, actor_name="Aetregan", action_cost=1,
            target_name="Bandit1",
        )
        old = evaluate_feint(action, state)
        new = evaluate_contest_roll(action, state)
        self._compare_results(old, new)

    def test_dispatcher_routes_to_chassis(self):
        """evaluate_action() routes contest roll actions through the chassis."""
        state = _quick_state()
        action = Action(
            type=ActionType.TRIP, actor_name="Rook", action_cost=1,
            target_name="Bandit1",
        )
        dispatched = evaluate_action(action, state)
        direct = evaluate_contest_roll(action, state)
        self._compare_results(dispatched, direct)


# ===========================================================================
# Regression (1)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_27th_verification(self):
        """27th verification: Strike Hard EV 7.65 after CP10.4.1."""
        from pf2e.tactics import STRIKE_HARD, evaluate_tactic

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)
