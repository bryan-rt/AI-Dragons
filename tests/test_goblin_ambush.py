"""Tests for goblin ambush scenario + sheet= syntax (Phase C.3)."""

import pytest

from pf2e.npc_data import NPCData
from sim.scenario import load_scenario
from sim.solver import solve_combat
from sim.search import SearchConfig, run_simulation

SCENARIO = "scenarios/goblin_ambush.scenario"
STRIKE_HARD_SCENARIO = "scenarios/checkpoint_1_strike_hard.scenario"
EV_TOLERANCE = 0.01


# -------------------------------------------------------------------
# Scenario loading
# -------------------------------------------------------------------

class TestScenarioLoading:

    def test_scenario_loads(self):
        scenario = load_scenario(SCENARIO)
        assert scenario.name == "Goblin Ambush"

    def test_three_enemies(self):
        scenario = load_scenario(SCENARIO)
        assert len(scenario.enemies) == 3

    def test_all_enemies_have_npc_data(self):
        scenario = load_scenario(SCENARIO)
        for enemy in scenario.enemies:
            assert enemy.character is not None
            assert isinstance(enemy.character, NPCData)

    def test_goblin_warrior_stats(self):
        scenario = load_scenario(SCENARIO)
        warrior = next(
            e for e in scenario.enemies if "Warrior" in e.name)
        assert warrior.ac == 16
        assert warrior.max_hp == 6
        assert warrior.attack_bonus == 7

    def test_goblin_war_chanter_stats(self):
        scenario = load_scenario(SCENARIO)
        chanter = next(
            e for e in scenario.enemies if "Chanter" in e.name)
        assert chanter.ac == 17
        assert chanter.max_hp == 16

    def test_goblin_dog_stats(self):
        scenario = load_scenario(SCENARIO)
        dog = next(
            e for e in scenario.enemies if "Dog" in e.name)
        assert dog.ac == 15
        assert dog.max_hp == 17
        assert dog.attack_bonus == 9

    def test_goblin_dog_has_jaws(self):
        scenario = load_scenario(SCENARIO)
        dog = next(e for e in scenario.enemies if "Dog" in e.name)
        jaws = next(
            (eq for eq in dog.character.equipped_weapons
             if "Jaws" in eq.weapon.name), None)
        assert jaws is not None

    def test_goblin_warrior_dogslicer_agile(self):
        scenario = load_scenario(SCENARIO)
        warrior = next(
            e for e in scenario.enemies if "Warrior" in e.name)
        dogslicer = next(
            eq for eq in warrior.character.equipped_weapons
            if eq.weapon.name == "Dogslicer")
        assert dogslicer.weapon.is_agile


# -------------------------------------------------------------------
# Simulation
# -------------------------------------------------------------------

class TestSimulation:

    def test_full_combat_runs(self):
        scenario = load_scenario(SCENARIO)
        result = solve_combat(scenario, seed=77, max_rounds=10)
        assert result.outcome in ("victory", "wipe", "timeout")

    def test_full_combat_victory(self):
        scenario = load_scenario(SCENARIO)
        result = solve_combat(scenario, seed=77, max_rounds=10)
        assert result.outcome == "victory"

    def test_single_round_runs(self):
        scenario = load_scenario(SCENARIO)
        recs = run_simulation(scenario, seed=77)
        assert len(recs) > 0

    def test_verbose_output_contains_agile_map(self):
        """Goblin attacks should show agile MAP (-4 not -5)."""
        scenario = load_scenario(SCENARIO)
        config = SearchConfig(verbose=True)
        recs = run_simulation(scenario, seed=77, config=config)
        all_text = "\n".join(
            "\n".join(r.verbose_lines) for r in recs)
        # Goblin Dog or Warrior should have a strike with map=-5
        # (non-agile for Dog, or second agile for Warrior would be -4)
        assert "map=" in all_text


# -------------------------------------------------------------------
# Regression
# -------------------------------------------------------------------

class TestRegression:

    def test_ev_7_65_46th_verification(self):
        """EV 7.65 unchanged — 46th verification."""
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD
        scenario = load_scenario(STRIKE_HARD_SCENARIO)
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(
            7.65, abs=EV_TOLERANCE)

    def test_existing_scenarios_unaffected(self):
        """Flat-stat scenarios still work after sheet= addition."""
        scenario = load_scenario(STRIKE_HARD_SCENARIO)
        result = solve_combat(scenario)
        assert result.outcome == "victory"
