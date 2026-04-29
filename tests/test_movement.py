"""Tests for movement chassis (CP10.4.6).

Covers: evaluate_stride, evaluate_step, evaluate_crawl, evaluate_sneak,
parity with old evaluators, candidate generation, and regression.
"""

import pytest

from pf2e.actions import (
    Action,
    ActionType,
    evaluate_stride as old_stride,
    evaluate_step as old_step,
    evaluate_sneak as old_sneak,
)
from pf2e.movement import (
    evaluate_stride,
    evaluate_step,
    evaluate_crawl,
    evaluate_sneak,
)
from sim.candidates import generate_candidates
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
# evaluate_stride (2)
# ===========================================================================

class TestStride:

    def test_stride_produces_position_change(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIDE, actor_name="Rook",
                        action_cost=1, target_position=(3, 3))
        result = evaluate_stride(action, state)
        assert result.eligible
        assert result.outcomes[0].position_changes["Rook"] == (3, 3)

    def test_stride_ineligible_no_position(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIDE, actor_name="Rook",
                        action_cost=1)
        result = evaluate_stride(action, state)
        assert not result.eligible


# ===========================================================================
# evaluate_step (2)
# ===========================================================================

class TestStep:

    def test_step_produces_position_change(self):
        state = _quick_state()
        action = Action(type=ActionType.STEP, actor_name="Rook",
                        action_cost=1, target_position=(5, 7))
        result = evaluate_step(action, state)
        assert result.eligible
        assert result.outcomes[0].position_changes["Rook"] == (5, 7)

    def test_step_ineligible_no_position(self):
        state = _quick_state()
        action = Action(type=ActionType.STEP, actor_name="Rook",
                        action_cost=1)
        result = evaluate_step(action, state)
        assert not result.eligible


# ===========================================================================
# evaluate_crawl (4)
# ===========================================================================

class TestCrawl:

    def test_crawl_eligible_when_prone(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.CRAWL, actor_name="Rook",
                        action_cost=1, target_position=(5, 7))
        result = evaluate_crawl(action, state)
        assert result.eligible
        assert result.outcomes[0].position_changes["Rook"] == (5, 7)

    def test_crawl_ineligible_not_prone(self):
        state = _quick_state()
        action = Action(type=ActionType.CRAWL, actor_name="Rook",
                        action_cost=1, target_position=(5, 7))
        result = evaluate_crawl(action, state)
        assert not result.eligible
        assert "prone" in result.ineligibility_reason.lower()

    def test_crawl_ineligible_no_position(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.CRAWL, actor_name="Rook",
                        action_cost=1)
        result = evaluate_crawl(action, state)
        assert not result.eligible

    def test_crawl_prone_condition_not_removed(self):
        """Crawling does NOT remove prone — must Stand separately."""
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        action = Action(type=ActionType.CRAWL, actor_name="Rook",
                        action_cost=1, target_position=(5, 7))
        result = evaluate_crawl(action, state)
        assert result.eligible
        outcome = result.outcomes[0]
        assert not outcome.conditions_removed


# ===========================================================================
# evaluate_sneak (4)
# ===========================================================================

class TestSneak:

    def test_sneak_two_outcomes_when_hidden(self):
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.SNEAK, actor_name="Erisen",
                        action_cost=1, target_position=(6, 5))
        result = evaluate_sneak(action, state)
        assert result.eligible
        assert len(result.outcomes) == 2

    def test_sneak_ineligible_not_hidden(self):
        state = _quick_state()
        action = Action(type=ActionType.SNEAK, actor_name="Erisen",
                        action_cost=1, target_position=(6, 5))
        result = evaluate_sneak(action, state)
        assert not result.eligible

    def test_sneak_ineligible_no_position(self):
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.SNEAK, actor_name="Erisen",
                        action_cost=1)
        result = evaluate_sneak(action, state)
        assert not result.eligible

    def test_sneak_probabilities_sum_to_one(self):
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.SNEAK, actor_name="Erisen",
                        action_cost=1, target_position=(6, 5))
        result = evaluate_sneak(action, state)
        total = sum(o.probability for o in result.outcomes)
        assert total == pytest.approx(1.0)


# ===========================================================================
# Parity (3)
# ===========================================================================

class TestParity:

    def test_parity_stride(self):
        state = _quick_state()
        action = Action(type=ActionType.STRIDE, actor_name="Rook",
                        action_cost=1, target_position=(3, 3))
        old = old_stride(action, state)
        new = evaluate_stride(action, state)
        assert old.eligible == new.eligible
        assert old.outcomes[0].position_changes == new.outcomes[0].position_changes

    def test_parity_step(self):
        state = _quick_state()
        action = Action(type=ActionType.STEP, actor_name="Rook",
                        action_cost=1, target_position=(5, 7))
        old = old_step(action, state)
        new = evaluate_step(action, state)
        assert old.eligible == new.eligible
        assert old.outcomes[0].position_changes == new.outcomes[0].position_changes

    def test_parity_sneak(self):
        state = _quick_state(pc_overrides={
            "Erisen": {"conditions": frozenset({"hidden"})},
        })
        action = Action(type=ActionType.SNEAK, actor_name="Erisen",
                        action_cost=1, target_position=(6, 5))
        old = old_sneak(action, state)
        new = evaluate_sneak(action, state)
        assert old.eligible == new.eligible
        assert len(old.outcomes) == len(new.outcomes)
        for o, n in zip(old.outcomes, new.outcomes):
            assert o.probability == pytest.approx(n.probability)
            assert o.position_changes == n.position_changes


# ===========================================================================
# Candidates (2)
# ===========================================================================

class TestCrawlCandidates:

    def test_crawl_candidates_generated_when_prone(self):
        state = _quick_state(pc_overrides={"Rook": {"prone": True}})
        candidates = generate_candidates(state, "Rook")
        crawl_actions = [a for a in candidates if a.type == ActionType.CRAWL]
        assert len(crawl_actions) > 0
        # All should be adjacent (distance 1 in grid)
        rook_pos = state.pcs["Rook"].position
        for a in crawl_actions:
            dr = abs(a.target_position[0] - rook_pos[0])
            dc = abs(a.target_position[1] - rook_pos[1])
            assert dr <= 1 and dc <= 1

    def test_crawl_candidates_absent_when_not_prone(self):
        state = _quick_state()
        candidates = generate_candidates(state, "Rook")
        crawl_actions = [a for a in candidates if a.type == ActionType.CRAWL]
        assert len(crawl_actions) == 0


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_32nd_verification(self):
        """32nd verification: Strike Hard EV 7.65 after CP10.4.6."""
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
        """Tactical Takedown 55% prone unchanged after CP10.4.6."""
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
