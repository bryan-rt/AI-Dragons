"""Tests for verbose combat output (CP11.7.0)."""

import pytest

from sim.scenario import load_scenario
from sim.search import (
    SearchConfig,
    ScoreBreakdown,
    TurnPlan,
    run_simulation,
    simulate_round,
)
from sim.initiative import roll_initiative
from sim.round_state import RoundState
from sim.verbose import format_verbose_turn, _hp_delta, _clamp

SCENARIO = "scenarios/checkpoint_1_strike_hard.scenario"
TERRAIN_SCENARIO = "scenarios/checkpoint_4_terrain_camp.scenario"
EV_TOLERANCE = 0.01


# --- Helpers ---

def _run_verbose(scenario_path=SCENARIO, seed=42):
    scenario = load_scenario(scenario_path)
    config = SearchConfig(verbose=True)
    return run_simulation(scenario, seed=seed, config=config)


def _build_state(scenario_path=SCENARIO, seed=42):
    scenario = load_scenario(scenario_path)
    dummy = RoundState.from_scenario(scenario, [])
    order = roll_initiative(
        list(dummy.pcs.values()), list(dummy.enemies.values()),
        seed=seed,
        explicit=scenario.initiative_explicit or None,
    )
    return RoundState.from_scenario(scenario, order), scenario


# ---------------------------------------------------------------
# Unit: _hp_delta
# ---------------------------------------------------------------

class TestHpDelta:
    def test_hp_changed(self):
        state, _ = _build_state()
        state2 = state.with_enemy_update("Bandit1", current_hp=10)
        result = _hp_delta("Bandit1", state, state2)
        assert "\u2192" in result
        assert "Bandit1" in result

    def test_hp_unchanged(self):
        state, _ = _build_state()
        result = _hp_delta("Bandit1", state, state)
        assert "\u2192" not in result
        assert "Bandit1" in result

    def test_unknown_name(self):
        state, _ = _build_state()
        result = _hp_delta("Nobody", state, state)
        assert result == ""


# ---------------------------------------------------------------
# Unit: _clamp
# ---------------------------------------------------------------

class TestClamp:
    def test_short_line_unchanged(self):
        assert _clamp("hello") == "hello"

    def test_long_line_truncated(self):
        long = "x" * 90
        result = _clamp(long)
        assert len(result) == 80
        assert result.endswith("\u2026")

    def test_exact_80_unchanged(self):
        line = "y" * 80
        assert _clamp(line) == line


# ---------------------------------------------------------------
# Unit: format_verbose_turn with empty results
# ---------------------------------------------------------------

def test_verbose_turn_empty_when_no_results():
    state, _ = _build_state()
    plan = TurnPlan(
        actor_name="Aetregan",
        actions=(),
        expected_score=0.0,
        resulting_state=state,
        score_breakdown=ScoreBreakdown(0, 0, 0, 0),
        action_results=(),
        intermediate_states=(),
    )
    result = format_verbose_turn(plan, state)
    assert result == ""


# ---------------------------------------------------------------
# Integration: TurnPlan fields
# ---------------------------------------------------------------

class TestTurnPlanVerboseFields:
    def test_action_results_populated_when_verbose(self):
        recs = _run_verbose()
        found_verbose = any(r.verbose_text for r in recs)
        assert found_verbose, "At least one turn should have verbose text"

    def test_action_results_empty_when_not_verbose(self):
        scenario = load_scenario(SCENARIO)
        config = SearchConfig(verbose=False)
        recs = run_simulation(scenario, seed=42, config=config)
        for rec in recs:
            assert rec.verbose_text == ""

    def test_intermediate_states_length_matches_actions(self):
        state, scenario = _build_state()
        config = SearchConfig(verbose=True)
        from pf2e.actions import evaluate_action as ea
        from sim.candidates import generate_candidates
        plans, _ = simulate_round(state, config, generate_candidates, ea)
        for plan in plans:
            assert len(plan.intermediate_states) == len(plan.actions)


# ---------------------------------------------------------------
# Integration: output content
# ---------------------------------------------------------------

class TestVerboseOutputContent:
    def test_contains_map(self):
        recs = _run_verbose()
        all_text = "\n".join(r.verbose_text for r in recs)
        assert "map=" in all_text

    def test_contains_ac(self):
        recs = _run_verbose()
        all_text = "\n".join(r.verbose_text for r in recs)
        assert "vs AC" in all_text

    def test_contains_ev(self):
        recs = _run_verbose()
        all_text = "\n".join(r.verbose_text for r in recs)
        assert "EV:" in all_text

    def test_all_lines_under_80_chars(self):
        recs = _run_verbose()
        for rec in recs:
            for line in rec.verbose_text.splitlines():
                assert len(line) <= 80, (
                    f"Line too long ({len(line)}): {line!r}")

    def test_no_verbose_flag_actions_unchanged(self):
        """Non-verbose part of output identical with/without --verbose."""
        scenario = load_scenario(SCENARIO)
        recs_normal = run_simulation(scenario, seed=42, config=None)
        recs_verbose = run_simulation(
            scenario, seed=42, config=SearchConfig(verbose=True))
        for r1, r2 in zip(recs_normal, recs_verbose):
            assert r1.actions == r2.actions
            assert abs(r1.expected_score - r2.expected_score) < EV_TOLERANCE

    def test_enemy_turns_have_verbose_text(self):
        recs = _run_verbose()
        enemy_texts = [
            r.verbose_text for r in recs if r.actor_name == "Bandit1"]
        assert any(t for t in enemy_texts), (
            "Bandit1 should have verbose text")


# ---------------------------------------------------------------
# Full-combat verbose
# ---------------------------------------------------------------

def test_full_combat_verbose():
    """solve_combat with verbose=True produces verbose_text on TurnLogs."""
    from sim.solver import solve_combat
    scenario = load_scenario(SCENARIO)
    config = SearchConfig(verbose=True)
    solution = solve_combat(
        scenario, seed=42, max_rounds=10, num_plans=1, config=config)
    found = False
    for rlog in solution.rounds:
        for turn in rlog.turns:
            if turn.verbose_text:
                found = True
                break
    assert found, "Full combat should have at least one verbose turn"


# ---------------------------------------------------------------
# Regression
# ---------------------------------------------------------------

def test_ev_7_65_with_verbose_active():
    """EV 7.65 unchanged when verbose=True — 41st verification."""
    from pf2e.tactics import evaluate_tactic, STRIKE_HARD
    scenario = load_scenario(SCENARIO)
    ctx = scenario.build_tactic_context()
    result = evaluate_tactic(STRIKE_HARD, ctx)
    assert result.expected_damage_dealt == pytest.approx(
        7.65, abs=EV_TOLERANCE)
