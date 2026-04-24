"""Tests for Action, ActionOutcome, ActionResult dataclasses (Pass 3a)."""

import pytest

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType


class TestActionConstruction:
    def test_stride_action(self) -> None:
        a = Action(
            type=ActionType.STRIDE,
            actor_name="Rook",
            action_cost=1,
            target_position=(5, 8),
        )
        assert a.type == ActionType.STRIDE
        assert a.actor_name == "Rook"
        assert a.target_position == (5, 8)

    def test_strike_action(self) -> None:
        a = Action(
            type=ActionType.STRIKE,
            actor_name="Aetregan",
            action_cost=1,
            target_name="Bandit1",
            weapon_name="Scorpion Whip",
        )
        assert a.target_name == "Bandit1"
        assert a.weapon_name == "Scorpion Whip"

    def test_tactic_action(self) -> None:
        a = Action(
            type=ActionType.ACTIVATE_TACTIC,
            actor_name="Aetregan",
            action_cost=2,
            tactic_name="Strike Hard!",
        )
        assert a.tactic_name == "Strike Hard!"

    def test_action_is_frozen(self) -> None:
        a = Action(type=ActionType.END_TURN, actor_name="X", action_cost=0)
        with pytest.raises(Exception):
            a.actor_name = "Y"  # type: ignore[misc]


class TestActionOutcome:
    def test_outcome_defaults(self) -> None:
        o = ActionOutcome(probability=1.0)
        assert o.hp_changes == {}
        assert o.conditions_applied == {}

    def test_outcome_damage(self) -> None:
        o = ActionOutcome(
            probability=0.5,
            hp_changes={"Bandit1": -8.5},
            description="Rook hits Bandit1 for 8.5 damage",
        )
        assert o.hp_changes["Bandit1"] == -8.5

    def test_outcome_conditions(self) -> None:
        o = ActionOutcome(
            probability=0.6,
            conditions_applied={"Bandit1": ("off_guard",)},
        )
        assert "off_guard" in o.conditions_applied["Bandit1"]


class TestActionResult:
    def test_eligible_result(self) -> None:
        action = Action(type=ActionType.STRIDE, actor_name="Rook", action_cost=1)
        outcome = ActionOutcome(probability=1.0, description="Stride")
        r = ActionResult(action=action, outcomes=(outcome,))
        assert r.eligible
        assert r.verify_probability_sum()

    def test_ineligible_result(self) -> None:
        action = Action(
            type=ActionType.PLANT_BANNER, actor_name="Aetregan", action_cost=2,
        )
        r = ActionResult(
            action=action,
            outcomes=(),
            eligible=False,
            ineligibility_reason="Aetregan does not have Plant Banner feat",
        )
        assert not r.eligible
        assert "Plant Banner" in r.ineligibility_reason
        assert r.verify_probability_sum()

    def test_probability_sum_violation(self) -> None:
        action = Action(type=ActionType.STRIDE, actor_name="X", action_cost=1)
        r = ActionResult(action=action, outcomes=(
            ActionOutcome(probability=0.3),
            ActionOutcome(probability=0.4),
        ))
        assert not r.verify_probability_sum()

    def test_expected_damage_dealt(self) -> None:
        action = Action(type=ActionType.STRIKE, actor_name="Rook", action_cost=1)
        r = ActionResult(action=action, outcomes=(
            ActionOutcome(probability=0.5, hp_changes={"Bandit1": -10.0}),
            ActionOutcome(probability=0.5, hp_changes={}),
        ))
        assert r.expected_damage_dealt == pytest.approx(5.0)

    def test_expected_damage_zero_for_miss(self) -> None:
        action = Action(type=ActionType.STRIKE, actor_name="Rook", action_cost=1)
        r = ActionResult(action=action, outcomes=(
            ActionOutcome(probability=1.0, hp_changes={}),
        ))
        assert r.expected_damage_dealt == 0.0
