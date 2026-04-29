"""Tests for detection and visibility system (CP10.7).

Covers: LightLevel, VisionType, DetectionState, compute_light_level,
perceived_light_level, compute_detection_state, evaluate_hide eligibility,
_hidden_defensive_value fix, RoundState lighting, scenario parsing, regression.
"""

import pytest
from dataclasses import replace

from pf2e.detection import (
    LightLevel,
    LightSource,
    VisionType,
    DetectionState,
    compute_light_level,
    perceived_light_level,
    compute_detection_state,
)
from pf2e.actions import Action, ActionType, evaluate_hide, _hidden_defensive_value
from sim.grid import GridState
from sim.round_state import RoundState
from sim.scenario import load_scenario, parse_scenario

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


_CAMPFIRE = LightSource(position=(5, 8), bright_radius_ft=20, dim_radius_ft=40,
                        name="campfire")


# ===========================================================================
# Enum values (3)
# ===========================================================================

class TestEnums:

    def test_light_level_values(self):
        assert LightLevel.BRIGHT.value == "bright"
        assert LightLevel.DIM.value == "dim"
        assert LightLevel.DARK.value == "dark"

    def test_vision_type_values(self):
        assert VisionType.NORMAL.value == "normal"
        assert VisionType.LOW_LIGHT.value == "low_light"
        assert VisionType.DARKVISION.value == "darkvision"

    def test_detection_state_values(self):
        assert DetectionState.OBSERVED.value == "observed"
        assert DetectionState.CONCEALED.value == "concealed"
        assert DetectionState.HIDDEN.value == "hidden"


# ===========================================================================
# compute_light_level (4)
# ===========================================================================

class TestComputeLightLevel:

    def test_bright_ambient_no_sources(self):
        level = compute_light_level((0, 0), (), LightLevel.BRIGHT)
        assert level == LightLevel.BRIGHT

    def test_dark_ambient_no_sources(self):
        level = compute_light_level((0, 0), (), LightLevel.DARK)
        assert level == LightLevel.DARK

    def test_campfire_bright_radius(self):
        """Position within 20ft of campfire → BRIGHT even in dark ambient."""
        level = compute_light_level((5, 7), (_CAMPFIRE,), LightLevel.DARK)
        assert level == LightLevel.BRIGHT

    def test_campfire_dim_radius(self):
        """Position 25ft from campfire (in dim band) in dark ambient → DIM."""
        # (5,8) to (0,8) = 5 rows = 25ft → within dim 40ft, outside bright 20ft
        level = compute_light_level((0, 8), (_CAMPFIRE,), LightLevel.DARK)
        assert level == LightLevel.DIM


# ===========================================================================
# perceived_light_level (6)
# ===========================================================================

class TestPerceivedLightLevel:

    def test_normal_bright(self):
        assert perceived_light_level(LightLevel.BRIGHT, VisionType.NORMAL) == LightLevel.BRIGHT

    def test_normal_dim_stays_dim(self):
        assert perceived_light_level(LightLevel.DIM, VisionType.NORMAL) == LightLevel.DIM

    def test_normal_dark_stays_dark(self):
        assert perceived_light_level(LightLevel.DARK, VisionType.NORMAL) == LightLevel.DARK

    def test_low_light_dim_becomes_bright(self):
        assert perceived_light_level(LightLevel.DIM, VisionType.LOW_LIGHT) == LightLevel.BRIGHT

    def test_darkvision_dim_becomes_bright(self):
        assert perceived_light_level(LightLevel.DIM, VisionType.DARKVISION) == LightLevel.BRIGHT

    def test_darkvision_dark_becomes_dim(self):
        assert perceived_light_level(LightLevel.DARK, VisionType.DARKVISION) == LightLevel.DIM


# ===========================================================================
# compute_detection_state (6)
# ===========================================================================

class TestDetectionState:

    def test_bright_observed(self):
        ds = compute_detection_state((0, 0), (1, 1), VisionType.NORMAL,
                                     (), LightLevel.BRIGHT)
        assert ds == DetectionState.OBSERVED

    def test_dim_concealed(self):
        ds = compute_detection_state((0, 0), (1, 1), VisionType.NORMAL,
                                     (), LightLevel.DIM)
        assert ds == DetectionState.CONCEALED

    def test_dark_undetected(self):
        ds = compute_detection_state((0, 0), (1, 1), VisionType.NORMAL,
                                     (), LightLevel.DARK)
        assert ds == DetectionState.UNDETECTED

    def test_hidden_overrides_lighting(self):
        ds = compute_detection_state((0, 0), (1, 1), VisionType.NORMAL,
                                     (), LightLevel.BRIGHT, defender_hidden=True)
        assert ds == DetectionState.HIDDEN

    def test_low_light_in_dim_observed(self):
        """Low-light attacker sees dim as bright → OBSERVED."""
        ds = compute_detection_state((0, 0), (1, 1), VisionType.LOW_LIGHT,
                                     (), LightLevel.DIM)
        assert ds == DetectionState.OBSERVED

    def test_darkvision_in_dark_concealed(self):
        """Darkvision attacker sees dark as dim → CONCEALED."""
        ds = compute_detection_state((0, 0), (1, 1), VisionType.DARKVISION,
                                     (), LightLevel.DARK)
        assert ds == DetectionState.CONCEALED


# ===========================================================================
# evaluate_hide new eligibility (6)
# ===========================================================================

class TestHideEligibility:

    def test_hide_eligible_dim_ambient(self):
        """Dim ambient → concealment → Hide eligible."""
        state = _quick_state(pc_overrides={"Erisen": {"position": (0, 0)}})
        state = replace(state, ambient_light=LightLevel.DIM)
        action = Action(type=ActionType.HIDE, actor_name="Erisen", action_cost=1)
        result = evaluate_hide(action, state)
        assert result.eligible

    def test_hide_eligible_wall_between(self):
        """Wall between actor and enemy → cover → Hide eligible."""
        state = _quick_state(pc_overrides={"Erisen": {"position": (5, 5)}})
        grid_w = GridState(rows=10, cols=10, walls={(5, 6)})
        state = replace(state, grid=grid_w)
        action = Action(type=ActionType.HIDE, actor_name="Erisen", action_cost=1)
        result = evaluate_hide(action, state)
        assert result.eligible

    def test_hide_ineligible_bright_no_cover(self):
        """Bright ambient, no walls → no cover/concealment → ineligible."""
        state = _quick_state(pc_overrides={"Erisen": {"position": (0, 0)}})
        action = Action(type=ActionType.HIDE, actor_name="Erisen", action_cost=1)
        result = evaluate_hide(action, state)
        assert not result.eligible
        assert "No cover or concealment" in result.ineligibility_reason

    def test_hide_ineligible_already_hidden(self):
        state = _quick_state(pc_overrides={
            "Erisen": {"position": (0, 0), "conditions": frozenset({"hidden"})},
        })
        state = replace(state, ambient_light=LightLevel.DIM)
        action = Action(type=ActionType.HIDE, actor_name="Erisen", action_cost=1)
        result = evaluate_hide(action, state)
        assert not result.eligible

    def test_hide_strike_hard_scenario_unchanged(self):
        """Default Strike Hard scenario: bright, no walls → Hide ineligible for all."""
        state = _quick_state()
        for name in state.pcs:
            action = Action(type=ActionType.HIDE, actor_name=name, action_cost=1)
            result = evaluate_hide(action, state)
            assert not result.eligible

    def test_hide_darkvision_attacker_in_dark(self):
        """Darkvision enemy sees dark as dim → actor is CONCEALED → Hide eligible.
        But enemies are hardcoded NORMAL vision, so dark → UNDETECTED → still eligible."""
        state = _quick_state(pc_overrides={"Erisen": {"position": (0, 0)}})
        state = replace(state, ambient_light=LightLevel.DARK)
        action = Action(type=ActionType.HIDE, actor_name="Erisen", action_cost=1)
        result = evaluate_hide(action, state)
        assert result.eligible


# ===========================================================================
# _hidden_defensive_value fix (1)
# ===========================================================================

class TestHiddenEVFix:

    def test_hidden_ev_uses_050(self):
        """_hidden_defensive_value should use 0.50 (DC 11 = 10/20), not 0.45."""
        state = _quick_state()
        ev = _hidden_defensive_value(state)
        # With 0.50: attacks_on_me * 0.50 * avg_dmg
        # 2 attacks / 4 PCs = 0.5 attacks_on_me; avg_dmg = 7.5
        # EV = 0.5 * 0.50 * 7.5 = 1.875
        assert ev == pytest.approx(1.875, abs=0.01)


# ===========================================================================
# Character vision_type (3)
# ===========================================================================

class TestCharacterVision:

    def test_default_vision_normal(self):
        from pf2e.character import Character
        from pf2e.abilities import AbilityScores
        from pf2e.types import Ability, ProficiencyRank
        c = Character(
            name="Test", level=1,
            abilities=AbilityScores(10, 10, 10, 10, 10, 10),
            key_ability=Ability.STR,
            weapon_proficiencies={}, armor_proficiency=ProficiencyRank.UNTRAINED,
            perception_rank=ProficiencyRank.TRAINED,
            save_ranks={}, class_dc_rank=ProficiencyRank.TRAINED,
            equipped_weapons=(),
        )
        assert c.vision_type == VisionType.NORMAL

    def test_rook_darkvision(self):
        """Rook (Automaton) should have darkvision from Foundry importer."""
        state = _quick_state()
        assert state.pcs["Rook"].character.vision_type == VisionType.DARKVISION

    def test_erisen_low_light(self):
        """Erisen (Elf) should have low-light vision."""
        state = _quick_state()
        assert state.pcs["Erisen"].character.vision_type == VisionType.LOW_LIGHT


# ===========================================================================
# RoundState lighting fields (3)
# ===========================================================================

class TestRoundStateLighting:

    def test_default_bright_ambient(self):
        state = _quick_state()
        assert state.ambient_light == LightLevel.BRIGHT

    def test_with_light_sources(self):
        state = _quick_state()
        state = replace(state, light_sources=(_CAMPFIRE,))
        assert len(state.light_sources) == 1
        assert state.light_sources[0].name == "campfire"

    def test_dim_ambient(self):
        state = _quick_state()
        state = replace(state, ambient_light=LightLevel.DIM)
        assert state.ambient_light == LightLevel.DIM


# ===========================================================================
# Scenario [lighting] parsing (3)
# ===========================================================================

class TestScenarioLighting:

    def test_parse_no_lighting_defaults(self):
        """Scenario without [lighting] section defaults to bright, no sources."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        assert scenario.ambient_light == LightLevel.BRIGHT
        assert scenario.light_sources == ()

    def test_parse_lighting_ambient_dim(self):
        text = """
[meta]
name = Test
[grid]
. . .
. c .
. m .
[enemies]
m1 name=B1 ac=15 ref=5 fort=3 will=2 atk=7 dmg=1d8 dmg_bonus=3 attacks=2 max_hp=20 perception=4
[lighting]
ambient = dim
"""
        scenario = parse_scenario(text)
        assert scenario.ambient_light == LightLevel.DIM

    def test_parse_lighting_campfire(self):
        text = """
[meta]
name = Test
[grid]
. . .
. c .
. m .
[enemies]
m1 name=B1 ac=15 ref=5 fort=3 will=2 atk=7 dmg=1d8 dmg_bonus=3 attacks=2 max_hp=20 perception=4
[lighting]
ambient = dark
campfire = 1,1
"""
        scenario = parse_scenario(text)
        assert scenario.ambient_light == LightLevel.DARK
        assert len(scenario.light_sources) == 1
        assert scenario.light_sources[0].position == (1, 1)
        assert scenario.light_sources[0].bright_radius_ft == 20


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_35th_verification(self):
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
