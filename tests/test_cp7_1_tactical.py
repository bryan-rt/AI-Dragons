"""Tests for CP7.1 tactical reasoning fixes."""

import pytest

from pf2e.actions import Action, ActionType, evaluate_action
from pf2e.combat_math import die_average
from sim.candidates import generate_candidates
from sim.scenario import load_scenario
from sim.round_state import RoundState, CombatantSnapshot
from dataclasses import replace

EV_TOLERANCE = 0.01


def _load_state(scenario_path, init_order):
    scenario = load_scenario(scenario_path)
    return RoundState.from_scenario(scenario, init_order)


# ---------------------------------------------------------------------------
# Fix 1: Idempotent condition suppression
# ---------------------------------------------------------------------------

class TestDemoralizeConditionSuppression:

    @pytest.fixture
    def state(self):
        return _load_state(
            "scenarios/checkpoint_3_three_bandits.scenario",
            ["Rook", "Aetregan", "Dalai Alpaca", "Erisen",
             "Bandit1", "Bandit2", "BanditCaster"],
        )

    def test_suppressed_when_frightened_2(self, state):
        """No Demoralize candidate when target already frightened_2+."""
        b2 = state.enemies["Bandit2"]
        b2_f2 = replace(b2, conditions=b2.conditions | frozenset({"frightened_2"}))
        state2 = replace(state, enemies={**state.enemies, "Bandit2": b2_f2})
        cands = generate_candidates(state2, "Rook")
        dem_b2 = [c for c in cands if c.type == ActionType.DEMORALIZE
                  and c.target_name == "Bandit2"]
        assert len(dem_b2) == 0

    def test_allowed_when_frightened_1(self, state):
        """Demoralize allowed when target at frightened_1 (crit could improve to 2)."""
        b2 = state.enemies["Bandit2"]
        b2_f1 = replace(b2, conditions=b2.conditions | frozenset({"frightened_1"}))
        state2 = replace(state, enemies={**state.enemies, "Bandit2": b2_f1})
        cands = generate_candidates(state2, "Rook")
        dem_b2 = [c for c in cands if c.type == ActionType.DEMORALIZE
                  and c.target_name == "Bandit2"]
        assert len(dem_b2) > 0

    def test_allowed_when_not_frightened(self, state):
        cands = generate_candidates(state, "Rook")
        dem = [c for c in cands if c.type == ActionType.DEMORALIZE]
        assert len(dem) > 0


class TestDiversionConditionSuppression:

    @pytest.fixture
    def state(self):
        return _load_state(
            "scenarios/checkpoint_3_three_bandits.scenario",
            ["Rook", "Aetregan", "Dalai Alpaca", "Erisen",
             "Bandit1", "Bandit2", "BanditCaster"],
        )

    def test_suppressed_when_off_guard(self, state):
        b1 = state.enemies["Bandit1"]
        b1_og = replace(b1, off_guard=True)
        state2 = replace(state, enemies={**state.enemies, "Bandit1": b1_og})
        cands = generate_candidates(state2, "Dalai Alpaca")
        div_b1 = [c for c in cands if c.type == ActionType.CREATE_A_DIVERSION
                  and c.target_name == "Bandit1"]
        assert len(div_b1) == 0

    def test_suppressed_when_prone(self, state):
        b1 = state.enemies["Bandit1"]
        b1_p = replace(b1, prone=True)
        state2 = replace(state, enemies={**state.enemies, "Bandit1": b1_p})
        cands = generate_candidates(state2, "Dalai Alpaca")
        div_b1 = [c for c in cands if c.type == ActionType.CREATE_A_DIVERSION
                  and c.target_name == "Bandit1"]
        assert len(div_b1) == 0

    def test_allowed_when_not_off_guard(self, state):
        cands = generate_candidates(state, "Dalai Alpaca")
        div = [c for c in cands if c.type == ActionType.CREATE_A_DIVERSION]
        assert len(div) > 0


class TestFeintConditionSuppression:

    @pytest.fixture
    def state(self):
        return _load_state(
            "scenarios/checkpoint_3_three_bandits.scenario",
            ["Aetregan", "Rook", "Dalai Alpaca", "Erisen",
             "Bandit1", "Bandit2", "BanditCaster"],
        )

    def test_suppressed_when_off_guard(self, state):
        # Move Aetregan adjacent to Bandit1 for Feint reach
        aet = replace(state.pcs["Aetregan"], position=(1, 3))
        b1 = replace(state.enemies["Bandit1"], off_guard=True)
        state2 = replace(state,
                         pcs={**state.pcs, "Aetregan": aet},
                         enemies={**state.enemies, "Bandit1": b1})
        cands = generate_candidates(state2, "Aetregan")
        feint_b1 = [c for c in cands if c.type == ActionType.FEINT
                    and c.target_name == "Bandit1"]
        assert len(feint_b1) == 0


# ---------------------------------------------------------------------------
# Fix 2: RK time value and resistance avoidance
# ---------------------------------------------------------------------------

class TestRecallKnowledgeTimeValue:

    @pytest.fixture
    def state(self):
        return _load_state(
            "scenarios/checkpoint_3_three_bandits.scenario",
            ["Dalai Alpaca", "Rook", "Aetregan", "Erisen",
             "Bandit1", "Bandit2", "BanditCaster"],
        )

    def test_rk_ev_higher_at_full_hp(self, state):
        """Full-HP enemy should have higher RK EV than near-dead enemy."""
        # Full HP Bandit2
        rk_full = Action(type=ActionType.RECALL_KNOWLEDGE, actor_name="Dalai Alpaca",
                         action_cost=1, target_name="Bandit2")
        r_full = evaluate_action(rk_full, state)
        ev_full = sum(o.probability * o.score_delta for o in r_full.outcomes)

        # Near-dead Bandit2
        b2_low = replace(state.enemies["Bandit2"], current_hp=3)
        state_low = replace(state, enemies={**state.enemies, "Bandit2": b2_low})
        r_low = evaluate_action(rk_full, state_low)
        ev_low = sum(o.probability * o.score_delta for o in r_low.outcomes)

        assert ev_full > ev_low

    def test_rk_captures_resistance_avoidance(self, state):
        """Enemy with only resistance (no weakness) should score > 0."""
        rk = Action(type=ActionType.RECALL_KNOWLEDGE, actor_name="Dalai Alpaca",
                    action_cost=1, target_name="Bandit2")
        result = evaluate_action(rk, state)
        ev = sum(o.probability * o.score_delta for o in result.outcomes)
        assert ev > 0


# ---------------------------------------------------------------------------
# Fix 3: Demoralize EV accounts for existing frightened
# ---------------------------------------------------------------------------

class TestDemoralizeExistingFrightened:

    @pytest.fixture
    def state(self):
        return _load_state(
            "scenarios/checkpoint_3_three_bandits.scenario",
            ["Rook", "Aetregan", "Dalai Alpaca", "Erisen",
             "Bandit1", "Bandit2", "BanditCaster"],
        )

    def test_lower_ev_when_already_frightened_1(self, state):
        """Demoralize on frightened_1 target has lower EV (success is no-op)."""
        action = Action(type=ActionType.DEMORALIZE, actor_name="Rook",
                        action_cost=1, target_name="Bandit2")

        r_none = evaluate_action(action, state)
        ev_none = sum(o.probability * o.score_delta for o in r_none.outcomes)

        b2_f1 = replace(state.enemies["Bandit2"],
                         conditions=frozenset({"frightened_1"}))
        state_f1 = replace(state, enemies={**state.enemies, "Bandit2": b2_f1})
        r_f1 = evaluate_action(action, state_f1)
        ev_f1 = sum(o.probability * o.score_delta for o in r_f1.outcomes)

        assert ev_f1 < ev_none


# ---------------------------------------------------------------------------
# Fix 4: Focus fire bonus
# ---------------------------------------------------------------------------

class TestFocusFireBonus:

    @pytest.fixture
    def state(self):
        return _load_state(
            "scenarios/checkpoint_3_three_bandits.scenario",
            ["Rook", "Aetregan", "Dalai Alpaca", "Erisen",
             "Bandit1", "Bandit2", "BanditCaster"],
        )

    def test_no_bonus_on_first_attack(self, state):
        """map_count=0 → no focus fire bonus."""
        # Move Rook adjacent to Bandit1 (1,3) → Rook at (1,4)
        rook = replace(state.pcs["Rook"], position=(1, 4), map_count=0)
        state2 = replace(state, pcs={**state.pcs, "Rook": rook})
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")
        result = evaluate_action(action, state2)
        assert result.eligible

    def test_bonus_on_wounded_target(self, state):
        """Follow-up attack on 30% HP target should have higher EV than 100%."""
        rook = replace(state.pcs["Rook"], position=(1, 4), map_count=1)
        state2 = replace(state, pcs={**state.pcs, "Rook": rook})

        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")

        # Full HP
        r_full = evaluate_action(action, state2)
        ev_full = r_full.expected_damage_dealt + sum(
            o.probability * o.score_delta for o in r_full.outcomes)

        # 30% HP
        b1_low = replace(state.enemies["Bandit1"], current_hp=6)
        state_low = replace(state2, enemies={**state.enemies, "Bandit1": b1_low})
        r_low = evaluate_action(action, state_low)
        ev_low = r_low.expected_damage_dealt + sum(
            o.probability * o.score_delta for o in r_low.outcomes)

        assert ev_low > ev_full


# ---------------------------------------------------------------------------
# EV Regression
# ---------------------------------------------------------------------------

class TestEVRegression:
    def test_ev_7_65(self):
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)
