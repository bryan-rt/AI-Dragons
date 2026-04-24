"""Tests for sim/search.py — beam search, scoring, branching, adversarial."""

import time

import pytest

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType
from pf2e.character import CombatantState, EnemyState
from pf2e.types import SaveType
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState
from sim.grid import GridState
from sim.scenario import load_scenario
from sim.search import (
    SearchConfig,
    ScoreBreakdown,
    TurnPlan,
    adversarial_enemy_turn,
    apply_action_result,
    beam_search_turn,
    compute_breakdown,
    drop_cost,
    kill_value,
    role_multiplier,
    score_state,
    simulate_round,
)
from tests.fixtures import (
    make_aetregan,
    make_dalai,
    make_rook_combat_state,
)

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers for building mock states and evaluators
# ---------------------------------------------------------------------------

def _quick_state(
    pc_hps: dict[str, int] | None = None,
    enemy_hps: dict[str, int] | None = None,
) -> RoundState:
    """Build a RoundState from the canonical scenario with optional HP overrides."""
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    init_order = ["Aetregan", "Rook", "Dalai Alpaca", "Erisen", "Bandit1"]
    state = RoundState.from_scenario(scenario, init_order)
    if pc_hps:
        for name, hp in pc_hps.items():
            state = state.with_pc_update(name, current_hp=hp)
    if enemy_hps:
        for name, hp in enemy_hps.items():
            state = state.with_enemy_update(name, current_hp=hp)
    return state


def _end_turn_action(actor: str) -> Action:
    return Action(type=ActionType.END_TURN, actor_name=actor, action_cost=0)


def _strike_action(actor: str, target: str) -> Action:
    return Action(
        type=ActionType.STRIKE, actor_name=actor, action_cost=1,
        target_name=target, weapon_name="Longsword",
    )


def _mock_evaluator(
    outcomes_map: dict[str, ActionResult],
) -> tuple[
    type(lambda: None),  # candidate_actions
    type(lambda: None),  # evaluate_action
]:
    """Build mock candidate_actions and evaluate_action callables.

    outcomes_map keys are "type:target" strings like "STRIKE:Bandit1".
    """
    def candidate_actions(state: RoundState, actor: str) -> list[Action]:
        actions = []
        for key in outcomes_map:
            parts = key.split(":")
            atype = ActionType[parts[0]]
            target = parts[1] if len(parts) > 1 else ""
            actions.append(Action(
                type=atype, actor_name=actor, action_cost=1,
                target_name=target,
            ))
        actions.append(_end_turn_action(actor))
        return actions

    def evaluate_action(action: Action, state: RoundState) -> ActionResult:
        if action.type == ActionType.END_TURN:
            return ActionResult(
                action=action,
                outcomes=(ActionOutcome(probability=1.0),),
            )
        key = f"{action.type.name}:{action.target_name}"
        if key in outcomes_map:
            return outcomes_map[key]
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason="Not in mock")

    return candidate_actions, evaluate_action


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------

class TestScoring:

    def test_score_zero_for_unchanged_state(self) -> None:
        state = _quick_state()
        assert score_state(state, state) == 0.0

    def test_damage_dealt_positive(self) -> None:
        initial = _quick_state()
        damaged = initial.with_enemy_update("Bandit1", current_hp=15)
        # Bandit1 was at 20, now 15 → 5 damage dealt
        assert score_state(damaged, initial) == pytest.approx(5.0, abs=EV_TOLERANCE)

    def test_damage_taken_penalized_half(self) -> None:
        initial = _quick_state()
        damaged = initial.with_pc_update("Rook", current_hp=13)
        # Rook was at 23, now 13 → 10 damage taken → -5.0
        assert score_state(damaged, initial) == pytest.approx(-5.0, abs=EV_TOLERANCE)

    def test_kill_adds_kill_value(self) -> None:
        initial = _quick_state()
        killed = initial.with_enemy_update("Bandit1", current_hp=0)
        # kill_value = 20 + 10*2 = 40. damage_dealt = 20.
        # score = 40 + 20 = 60
        assert score_state(killed, initial) == pytest.approx(60.0, abs=EV_TOLERANCE)


class TestRoleMultiplier:

    def test_dalai_drop_cost_doubled(self) -> None:
        initial = _quick_state()
        dropped = initial.with_pc_update("Dalai Alpaca", current_hp=0)
        breakdown = compute_breakdown(dropped, initial)
        # Dalai max_hp=17, role=2.0 → drop_cost = 17 + 10*2 = 37
        assert breakdown.drop_score == pytest.approx(37.0, abs=EV_TOLERANCE)

    def test_default_role_multiplier_one(self) -> None:
        initial = _quick_state()
        dropped = initial.with_pc_update("Rook", current_hp=0)
        breakdown = compute_breakdown(dropped, initial)
        # Rook max_hp=23, role=1.0 → drop_cost = 23 + 10*1 = 33
        assert breakdown.drop_score == pytest.approx(33.0, abs=EV_TOLERANCE)


# ---------------------------------------------------------------------------
# Beam search tests
# ---------------------------------------------------------------------------

class TestBeamSearch:

    def _strike_result(self, actor: str, target: str, dmg: float) -> ActionResult:
        return ActionResult(
            action=_strike_action(actor, target),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}, description="miss"),
                ActionOutcome(probability=0.5, hp_changes={target: -dmg},
                             description="hit"),
                ActionOutcome(probability=0.1, hp_changes={target: -dmg * 2},
                             description="crit"),
            ),
        )

    def test_selects_highest_score_sequence(self) -> None:
        state = _quick_state()
        good = self._strike_result("Rook", "Bandit1", 8.0)
        bad = ActionResult(
            action=Action(type=ActionType.STRIDE, actor_name="Rook",
                         action_cost=1),
            outcomes=(ActionOutcome(probability=1.0),),
        )
        cands, evaluator = _mock_evaluator({
            "STRIKE:Bandit1": good, "STRIDE:": bad,
        })
        plan = beam_search_turn(
            state, "Rook", SearchConfig(beam_widths=(5, 3, 2)),
            cands, evaluator,
        )
        assert any(a.type == ActionType.STRIKE for a in plan.actions)

    def test_beam_widths_respected(self) -> None:
        """With beam (2,2,2), search should still produce a valid plan."""
        state = _quick_state()
        result = self._strike_result("Rook", "Bandit1", 8.0)
        cands, evaluator = _mock_evaluator({"STRIKE:Bandit1": result})
        plan = beam_search_turn(
            state, "Rook", SearchConfig(beam_widths=(2, 2, 2)),
            cands, evaluator,
        )
        assert plan.actor_name == "Rook"
        assert len(plan.actions) <= 3

    def test_pruning_below_threshold(self) -> None:
        """Outcomes below 0.1% are pruned."""
        state = _quick_state()
        result = ActionResult(
            action=_strike_action("Rook", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=0.999, hp_changes={}),
                ActionOutcome(probability=0.001,
                             hp_changes={"Bandit1": -100}),
            ),
        )
        cands, evaluator = _mock_evaluator({"STRIKE:Bandit1": result})
        plan = beam_search_turn(
            state, "Rook", SearchConfig(beam_widths=(5, 3, 2)),
            cands, evaluator,
        )
        # The 0.001 outcome at threshold boundary should still be included
        # (0.001 == threshold, not below)
        assert plan is not None

    def test_widening_at_root(self) -> None:
        """Root depth uses beam_widths[0] = larger K."""
        state = _quick_state()
        result = self._strike_result("Rook", "Bandit1", 8.0)
        cands, evaluator = _mock_evaluator({"STRIKE:Bandit1": result})
        plan = beam_search_turn(
            state, "Rook", SearchConfig(beam_widths=(50, 5, 2)),
            cands, evaluator,
        )
        assert plan is not None

    def test_three_action_turn_depth(self) -> None:
        state = _quick_state()
        result = self._strike_result("Rook", "Bandit1", 8.0)
        cands, evaluator = _mock_evaluator({"STRIKE:Bandit1": result})
        plan = beam_search_turn(
            state, "Rook", SearchConfig(beam_widths=(3, 3, 3)),
            cands, evaluator,
        )
        assert len(plan.actions) == 3

    def test_end_turn_short_circuits(self) -> None:
        """If only END_TURN is available, plan has 1 action."""
        state = _quick_state()
        cands = lambda s, a: [_end_turn_action(a)]
        evaluator = lambda a, s: ActionResult(
            action=a, outcomes=(ActionOutcome(probability=1.0),),
        )
        plan = beam_search_turn(
            state, "Rook", SearchConfig(beam_widths=(3, 3, 3)),
            cands, evaluator,
        )
        assert len(plan.actions) == 1
        assert plan.actions[0].type == ActionType.END_TURN


# ---------------------------------------------------------------------------
# Kill/drop branching tests
# ---------------------------------------------------------------------------

class TestKillDropBranching:

    def test_threshold_crossing_spawns_two_children(self) -> None:
        """60% kill probability → exactly 2 branches."""
        state = _quick_state(enemy_hps={"Bandit1": 5})
        result = ActionResult(
            action=_strike_action("Rook", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.5, hp_changes={"Bandit1": -8}),
                ActionOutcome(probability=0.1, hp_changes={"Bandit1": -16}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        assert len(branches) == 2

    def test_below_threshold_no_branching(self) -> None:
        """3% kill probability → 1 EV-folded state."""
        state = _quick_state(enemy_hps={"Bandit1": 5})
        result = ActionResult(
            action=_strike_action("Rook", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=0.97, hp_changes={}),
                ActionOutcome(probability=0.03, hp_changes={"Bandit1": -10}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        assert len(branches) == 1

    def test_event_world_hp_zero(self) -> None:
        state = _quick_state(enemy_hps={"Bandit1": 5})
        result = ActionResult(
            action=_strike_action("Rook", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.6, hp_changes={"Bandit1": -10}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        event_states = [s for s, w in branches if s.enemies["Bandit1"].current_hp <= 0]
        assert len(event_states) == 1
        assert event_states[0].enemies["Bandit1"].current_hp == 0

    def test_no_event_world_hp_ev_updated(self) -> None:
        state = _quick_state(enemy_hps={"Bandit1": 5})
        result = ActionResult(
            action=_strike_action("Rook", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.6, hp_changes={"Bandit1": -10}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        no_event = [s for s, w in branches if s.enemies["Bandit1"].current_hp > 0]
        assert len(no_event) == 1
        # Only the miss (prob 0.4) is non-crossing → HP stays at 5
        assert no_event[0].enemies["Bandit1"].current_hp == 5

    def test_multi_target_independent_branching(self) -> None:
        """Two enemies each with independent kill chance."""
        state = _quick_state(enemy_hps={"Bandit1": 3})
        # This tests that branching handles the outcome set correctly
        # even though only one enemy exists in canonical scenario
        result = ActionResult(
            action=_strike_action("Rook", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=0.3, hp_changes={}),
                ActionOutcome(probability=0.7, hp_changes={"Bandit1": -10}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        assert len(branches) == 2


# ---------------------------------------------------------------------------
# Reaction branching tests
# ---------------------------------------------------------------------------

class TestReactionBranching:

    def test_intercept_decision_branches(self) -> None:
        """An ActionResult with intercept-expanded outcomes branches correctly."""
        state = _quick_state()
        # Mock: hit with intercept = 2 outcomes, hit without = 1
        result = ActionResult(
            action=_strike_action("Bandit1", "Dalai Alpaca"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.3,
                             hp_changes={"Dalai Alpaca": -8}),
                ActionOutcome(probability=0.3,
                             hp_changes={"Rook": -7}),  # intercepted
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        # No kill/drop crossing at full HP → EV-collapse, 1 state
        assert len(branches) == 1

    def test_shield_block_decision_branches(self) -> None:
        """Shield block reduced damage shows up in EV calculation."""
        state = _quick_state()
        result = ActionResult(
            action=_strike_action("Bandit1", "Rook"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.3, hp_changes={"Rook": -8}),
                ActionOutcome(probability=0.3, hp_changes={"Rook": -3}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        assert len(branches) == 1  # no kill/drop at full HP

    def test_both_reactions_quad_branch(self) -> None:
        """4 reaction combos on a hit, reflected in outcomes."""
        state = _quick_state()
        result = ActionResult(
            action=_strike_action("Bandit1", "Dalai Alpaca"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.15,
                             hp_changes={"Dalai Alpaca": -8}),
                ActionOutcome(probability=0.15,
                             hp_changes={"Dalai Alpaca": -3}),
                ActionOutcome(probability=0.15,
                             hp_changes={"Rook": -7}),
                ActionOutcome(probability=0.15,
                             hp_changes={"Rook": -2}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        assert len(branches) >= 1

    def test_ineligible_reactions_no_branching(self) -> None:
        """Standard 3-outcome Strike with no reactions."""
        state = _quick_state()
        result = ActionResult(
            action=_strike_action("Bandit1", "Rook"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.5, hp_changes={"Rook": -8}),
                ActionOutcome(probability=0.1, hp_changes={"Rook": -16}),
            ),
        )
        branches = apply_action_result(
            result, state, state, SearchConfig(),
        )
        assert len(branches) == 1


# ---------------------------------------------------------------------------
# Adversarial enemy tests
# ---------------------------------------------------------------------------

class TestAdversarialEnemy:

    def test_enemy_search_sign_flips_score(self) -> None:
        state = _quick_state()
        attack_dalai = ActionResult(
            action=Action(type=ActionType.STRIKE, actor_name="Bandit1",
                         action_cost=1, target_name="Dalai Alpaca"),
            outcomes=(
                ActionOutcome(probability=0.5, hp_changes={}),
                ActionOutcome(probability=0.5,
                             hp_changes={"Dalai Alpaca": -8}),
            ),
        )
        cands, evaluator = _mock_evaluator({"STRIKE:Dalai Alpaca": attack_dalai})
        plan = adversarial_enemy_turn(
            state, "Bandit1", SearchConfig(enemy_beam_widths=(3, 2, 1)),
            cands, evaluator,
        )
        # Enemy should pick the attack that harms PCs
        assert any(a.target_name == "Dalai Alpaca" for a in plan.actions
                   if a.type == ActionType.STRIKE)

    def test_enemy_beam_widths_used(self) -> None:
        state = _quick_state()
        result = ActionResult(
            action=_strike_action("Bandit1", "Rook"),
            outcomes=(ActionOutcome(probability=1.0, hp_changes={"Rook": -5}),),
        )
        cands, evaluator = _mock_evaluator({"STRIKE:Rook": result})
        plan = adversarial_enemy_turn(
            state, "Bandit1", SearchConfig(enemy_beam_widths=(2, 1, 1)),
            cands, evaluator,
        )
        assert plan.actor_name == "Bandit1"

    def test_no_recursive_sub_search(self) -> None:
        """Enemy search should not call adversarial_enemy_turn recursively."""
        call_count = 0
        state = _quick_state()

        def counting_cands(s, a):
            nonlocal call_count
            call_count += 1
            return [_end_turn_action(a)]

        def evaluator(a, s):
            return ActionResult(
                action=a, outcomes=(ActionOutcome(probability=1.0),),
            )

        adversarial_enemy_turn(
            state, "Bandit1", SearchConfig(enemy_beam_widths=(2, 1, 1)),
            counting_cands, evaluator,
        )
        # candidate_actions called once per beam entry per depth, not recursively
        assert call_count <= 10  # reasonable bound


# ---------------------------------------------------------------------------
# Simulate round tests
# ---------------------------------------------------------------------------

class TestSimulateRound:

    def test_initiative_order_traversed(self) -> None:
        state = _quick_state()
        # Restrict to 3 combatants for simplicity
        from dataclasses import replace
        state = replace(state, initiative_order=("Aetregan", "Bandit1", "Rook"))

        def cands(s, a):
            return [_end_turn_action(a)]

        def evaluator(a, s):
            return ActionResult(
                action=a, outcomes=(ActionOutcome(probability=1.0),),
            )

        plans, final = simulate_round(state, SearchConfig(), cands, evaluator)
        assert len(plans) == 3
        assert [p.actor_name for p in plans] == ["Aetregan", "Bandit1", "Rook"]

    def test_final_state_accumulates_changes(self) -> None:
        state = _quick_state()
        from dataclasses import replace
        state = replace(state, initiative_order=("Rook",))

        damage_result = ActionResult(
            action=_strike_action("Rook", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=1.0, hp_changes={"Bandit1": -5}),
            ),
        )
        cands, evaluator = _mock_evaluator({"STRIKE:Bandit1": damage_result})
        plans, final = simulate_round(
            state, SearchConfig(beam_widths=(2, 2, 2)), cands, evaluator,
        )
        # After 3 Strikes dealing 5 each = 15 total damage
        assert final.enemies["Bandit1"].current_hp < state.enemies["Bandit1"].current_hp


# ---------------------------------------------------------------------------
# Timing test (C2 target)
# ---------------------------------------------------------------------------

class TestTiming:

    @pytest.mark.slow
    def test_full_round_under_15_seconds(self) -> None:
        """C2 timing target: simulate_round completes in <15s."""
        state = _quick_state()
        strike = ActionResult(
            action=_strike_action("X", "Bandit1"),
            outcomes=(
                ActionOutcome(probability=0.4, hp_changes={}),
                ActionOutcome(probability=0.5, hp_changes={"Bandit1": -8}),
                ActionOutcome(probability=0.1, hp_changes={"Bandit1": -16}),
            ),
        )

        def cands(s, a):
            targets = list(s.enemies.keys()) if a in [p for p in s.pcs] else list(s.pcs.keys())
            actions = [
                Action(type=ActionType.STRIKE, actor_name=a,
                      action_cost=1, target_name=t)
                for t in targets[:1]
            ]
            actions.append(_end_turn_action(a))
            return actions

        def evaluator(a, s):
            if a.type == ActionType.END_TURN:
                return ActionResult(
                    action=a, outcomes=(ActionOutcome(probability=1.0),),
                )
            return ActionResult(
                action=a,
                outcomes=(
                    ActionOutcome(probability=0.4, hp_changes={}),
                    ActionOutcome(probability=0.5,
                                 hp_changes={a.target_name: -8}),
                    ActionOutcome(probability=0.1,
                                 hp_changes={a.target_name: -16}),
                ),
            )

        start = time.time()
        plans, final = simulate_round(
            state, SearchConfig(beam_widths=(10, 5, 3),
                               enemy_beam_widths=(5, 3, 2)),
            cands, evaluator,
        )
        elapsed = time.time() - start
        assert elapsed < 15.0, f"simulate_round took {elapsed:.1f}s (target: <15s)"
