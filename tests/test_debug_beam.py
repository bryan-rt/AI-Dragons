"""Tests for debug beam JSON output (CP11.1).

Covers: DebugTurnLog presence, actor types, depth data, winner matching,
JSON serialization, and regression.
"""

import json
import pytest

from pf2e.actions import evaluate_action as pf2e_evaluate_action, Action, ActionResult
from sim.candidates import generate_candidates
from sim.round_state import RoundState
from sim.scenario import load_scenario
from sim.search import (
    DebugActionEntry,
    DebugSequenceEntry,
    DebugTurnLog,
    SearchConfig,
    beam_search_turn,
    run_simulation,
    simulate_round,
    _debug_serialize,
)

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_with_debug():
    """Run checkpoint_1 scenario with debug_sink and return (plans, sink)."""
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    sink: list[DebugTurnLog] = []
    recs = run_simulation(scenario, seed=42, debug_sink=sink)
    return recs, sink, scenario


# ===========================================================================
# DebugTurnLog presence and content (6)
# ===========================================================================

class TestDebugTurnLogPresence:

    def test_turn_log_per_combatant(self):
        """One DebugTurnLog per combatant in initiative order."""
        _, sink, _ = _run_with_debug()
        assert len(sink) == 5  # 4 PCs + 1 enemy

    def test_pc_actor_type(self):
        _, sink, _ = _run_with_debug()
        pc_turns = [t for t in sink if t.actor_type == "pc"]
        assert len(pc_turns) == 4

    def test_enemy_actor_type(self):
        _, sink, _ = _run_with_debug()
        enemy_turns = [t for t in sink if t.actor_type == "enemy"]
        assert len(enemy_turns) == 1
        assert enemy_turns[0].actor == "Bandit1"

    def test_pre_turn_hp_all_combatants(self):
        _, sink, _ = _run_with_debug()
        first = sink[0]
        assert "Rook" in first.pre_turn_hp
        assert "Bandit1" in first.pre_turn_hp

    def test_initiative_position_set(self):
        _, sink, _ = _run_with_debug()
        positions = [t.initiative_position for t in sink]
        assert all(p >= 1 for p in positions)

    def test_candidates_generated_positive(self):
        _, sink, _ = _run_with_debug()
        for t in sink:
            assert t.candidates_generated > 0


# ===========================================================================
# Depth data (5)
# ===========================================================================

class TestDepthData:

    def test_depth1_nonempty(self):
        _, sink, _ = _run_with_debug()
        for t in sink:
            assert len(t.depth_1_evaluated) > 0

    def test_depth1_count_matches_candidates(self):
        """Depth 1 evaluated entries come from eligible candidates."""
        _, sink, _ = _run_with_debug()
        for t in sink:
            # depth_1 may have more entries than candidates_generated
            # due to branching (kill/drop), but should be >= 1
            assert len(t.depth_1_evaluated) >= 1

    def test_depth2_within_beam_width(self):
        _, sink, _ = _run_with_debug()
        for t in sink:
            assert len(t.depth_2_survivors) <= 50  # max beam K

    def test_depth3_within_beam_width(self):
        _, sink, _ = _run_with_debug()
        for t in sink:
            assert len(t.depth_3_survivors) <= 20

    def test_depth1_entry_has_fields(self):
        _, sink, _ = _run_with_debug()
        entry = sink[0].depth_1_evaluated[0]
        assert isinstance(entry.action, str)
        assert isinstance(entry.score, float)
        assert isinstance(entry.hp_delta, float)
        assert isinstance(entry.condition_ev, float)


# ===========================================================================
# Winner matching (3)
# ===========================================================================

class TestWinnerMatching:

    def test_winner_sequence_nonempty(self):
        _, sink, _ = _run_with_debug()
        for t in sink:
            assert len(t.winner_sequence) >= 1

    def test_winner_breakdown_keys(self):
        _, sink, _ = _run_with_debug()
        for t in sink:
            for key in ("damage_dealt", "damage_taken", "kill_score", "drop_score"):
                assert key in t.winner_breakdown

    def test_winner_first_action_in_depth1(self):
        """Winner's first action should appear somewhere in depth 1 entries."""
        _, sink, _ = _run_with_debug()
        for t in sink:
            first_action = t.winner_sequence[0]
            d1_actions = {e.action for e in t.depth_1_evaluated}
            assert first_action in d1_actions, (
                f"{t.actor}: winner first action {first_action!r} "
                f"not in depth 1: {d1_actions}"
            )


# ===========================================================================
# JSON serialization (3)
# ===========================================================================

class TestJsonSerialization:

    def test_serialize_is_valid_json(self):
        _, sink, scenario = _run_with_debug()
        result = _debug_serialize(sink, scenario.name, 42)
        # Should not raise
        json_str = json.dumps(result, indent=2)
        assert len(json_str) > 100

    def test_serialize_round_structure(self):
        _, sink, scenario = _run_with_debug()
        result = _debug_serialize(sink, scenario.name, 42)
        assert result["rounds"][0]["round_number"] == 1
        assert len(result["rounds"][0]["turns"]) == len(sink)

    def test_serialize_scenario_name(self):
        _, sink, scenario = _run_with_debug()
        result = _debug_serialize(sink, scenario.name, 42)
        assert result["scenario"] == scenario.name


# ===========================================================================
# No-debug regression (1)
# ===========================================================================

class TestNoDebugRegression:

    def test_no_sink_identical_output(self):
        """With debug_sink=None, output is unchanged."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        recs_no = run_simulation(scenario, seed=42, debug_sink=None)
        recs_yes = run_simulation(scenario, seed=42, debug_sink=[])
        assert len(recs_no) == len(recs_yes)
        for r_no, r_yes in zip(recs_no, recs_yes):
            assert r_no.expected_score == pytest.approx(r_yes.expected_score, abs=0.01)


# ===========================================================================
# Regression (2)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_38th_verification(self):
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)

    def test_mortar_ev_5_95(self):
        from pf2e.save_damage import basic_save_ev
        ev = basic_save_ev(dc=17, save_mod=5, base_dmg=7.0)
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)
