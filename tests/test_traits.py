"""Tests for pf2e/traits.py — CP10.2 Trait System.

30 tests covering:
- TraitDef structure (5)
- is_immune() (8)
- has_trait() (8)
- Character.immunity_tags (4)
- CombatantSnapshot.used_flourish_this_turn (4)
- Regression (1)
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError, replace

from pf2e.traits import (
    TRAIT_REGISTRY,
    TraitCategory,
    TraitDef,
    has_trait,
    is_immune,
)
from pf2e.character import Character
from sim.round_state import CombatantSnapshot

EV_TOLERANCE = 0.01


# -------------------------------------------------------------------------
# TraitDef structure (5)
# -------------------------------------------------------------------------

class TestTraitDefStructure:

    def test_traitdef_is_frozen(self):
        defn = TRAIT_REGISTRY["attack"]
        with pytest.raises(FrozenInstanceError):
            defn.slug = "modified"  # type: ignore[misc]

    def test_all_9_slugs_in_registry(self):
        assert len(TRAIT_REGISTRY) == 9
        expected = {
            "attack", "flourish", "open", "press",
            "mental", "emotion", "fear", "auditory", "visual",
        }
        assert set(TRAIT_REGISTRY.keys()) == expected

    def test_fear_is_descriptor_not_immunity(self):
        """Fear is a descriptor — immunity flows through emotion, not fear."""
        assert TRAIT_REGISTRY["fear"].category == TraitCategory.DESCRIPTOR
        assert TRAIT_REGISTRY["fear"].immunity_tag == ""

    def test_immunity_traits_have_nonempty_tag(self):
        immunity_traits = [
            d for d in TRAIT_REGISTRY.values()
            if d.category == TraitCategory.IMMUNITY
        ]
        assert len(immunity_traits) >= 1
        for defn in immunity_traits:
            assert defn.immunity_tag != "", f"{defn.slug} should have nonempty immunity_tag"

    def test_map_traits_have_empty_immunity_tag(self):
        map_traits = [
            d for d in TRAIT_REGISTRY.values()
            if d.category == TraitCategory.MAP
        ]
        assert len(map_traits) >= 1
        for defn in map_traits:
            assert defn.immunity_tag == "", f"{defn.slug} should have empty immunity_tag"


# -------------------------------------------------------------------------
# is_immune() (8)
# -------------------------------------------------------------------------

class TestIsImmune:

    def test_is_immune_mental_vs_mental_target(self):
        assert is_immune({"mental"}, {"mental"}) is True

    def test_is_immune_mental_vs_empty_tags(self):
        assert is_immune({"mental"}, set()) is False

    def test_is_immune_emotion_vs_emotion_target(self):
        assert is_immune({"emotion"}, {"emotion"}) is True

    def test_is_immune_fear_vs_emotion_target(self):
        """Fear is a descriptor — does NOT gate immunity directly."""
        assert is_immune({"fear"}, {"emotion"}) is False

    def test_is_immune_unknown_slug_skipped(self):
        """Unknown slugs like 'finesse' are silently skipped."""
        assert is_immune({"finesse"}, {"mental"}) is False

    def test_is_immune_empty_action_traits(self):
        assert is_immune(set(), {"mental"}) is False

    def test_is_immune_multiple_traits_one_match(self):
        """If any action trait matches, immune."""
        assert is_immune({"fear", "mental", "emotion"}, {"mental"}) is True

    def test_is_immune_auditory_vs_auditory(self):
        assert is_immune({"auditory"}, {"auditory"}) is True


# -------------------------------------------------------------------------
# has_trait() (8)
# -------------------------------------------------------------------------

class TestHasTrait:

    def test_has_trait_attack_is_map(self):
        assert has_trait({"attack"}, TraitCategory.MAP) is True

    def test_has_trait_flourish_is_flourish(self):
        assert has_trait({"flourish"}, TraitCategory.FLOURISH) is True

    def test_has_trait_open_is_open(self):
        assert has_trait({"open"}, TraitCategory.OPEN) is True

    def test_has_trait_press_is_press(self):
        assert has_trait({"press"}, TraitCategory.PRESS) is True

    def test_has_trait_mental_is_immunity(self):
        assert has_trait({"mental"}, TraitCategory.IMMUNITY) is True

    def test_has_trait_fear_is_descriptor(self):
        assert has_trait({"fear"}, TraitCategory.DESCRIPTOR) is True

    def test_has_trait_unknown_slug(self):
        """Unknown slugs silently return False."""
        assert has_trait({"finesse"}, TraitCategory.FLOURISH) is False

    def test_has_trait_empty_set(self):
        assert has_trait(set(), TraitCategory.MAP) is False


# -------------------------------------------------------------------------
# Character.immunity_tags (4)
# -------------------------------------------------------------------------

class TestCharacterImmunityTags:

    def test_aetregan_immunity_tags_empty(self):
        from tests.fixtures import make_aetregan
        char = make_aetregan()
        assert char.immunity_tags == frozenset()

    def test_rook_immunity_tags_empty(self):
        """Automaton Constructed Body waives construct immunities.
        (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=48)
        """
        from tests.fixtures import make_rook
        char = make_rook()
        assert char.immunity_tags == frozenset()

    def test_immunity_tags_default_is_frozenset(self):
        from tests.fixtures import make_aetregan
        char = make_aetregan()
        assert isinstance(char.immunity_tags, frozenset)

    def test_synthetic_character_with_immunity_tags(self):
        """Build a Character with mental immunity, verify field."""
        from tests.fixtures import make_aetregan
        base = make_aetregan()
        modified = replace(base, immunity_tags=frozenset({"mental"}))
        assert "mental" in modified.immunity_tags
        assert modified.immunity_tags == frozenset({"mental"})


# -------------------------------------------------------------------------
# CombatantSnapshot.used_flourish_this_turn (4)
# -------------------------------------------------------------------------

class TestUsedFlourishThisTurn:

    def test_used_flourish_defaults_false(self):
        from tests.fixtures import make_rook_combat_state
        state = make_rook_combat_state()
        snap = CombatantSnapshot.from_combatant_state(state)
        assert snap.used_flourish_this_turn is False

    def test_used_flourish_on_snapshot_from_state(self):
        """from_combatant_state() produces False by default."""
        from tests.fixtures import make_aetregan
        from pf2e.character import CombatantState
        state = CombatantState.from_character(make_aetregan())
        snap = CombatantSnapshot.from_combatant_state(state)
        assert snap.used_flourish_this_turn is False

    def test_reset_turn_state_clears_flourish(self):
        """_reset_turn_state must reset used_flourish_this_turn to False."""
        from sim.solver import _reset_turn_state
        from sim.scenario import load_scenario

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        from sim.initiative import roll_initiative
        from sim.round_state import RoundState

        dummy = RoundState.from_scenario(scenario, [])
        order = roll_initiative(
            list(dummy.pcs.values()),
            list(dummy.enemies.values()),
            seed=42,
        )
        state = RoundState.from_scenario(scenario, order)

        # Find a PC name
        pc_name = list(state.pcs.keys())[0]

        # Set flourish to True, then reset
        state = state.with_pc_update(pc_name, used_flourish_this_turn=True)
        assert state.pcs[pc_name].used_flourish_this_turn is True

        state = _reset_turn_state(state, pc_name)
        assert state.pcs[pc_name].used_flourish_this_turn is False

    def test_used_flourish_independent_across_snapshots(self):
        """Updating flourish on one snapshot doesn't affect another."""
        from tests.fixtures import make_rook_combat_state
        state = make_rook_combat_state()
        snap1 = CombatantSnapshot.from_combatant_state(state)
        snap2 = replace(snap1, used_flourish_this_turn=True)
        assert snap1.used_flourish_this_turn is False
        assert snap2.used_flourish_this_turn is True


# -------------------------------------------------------------------------
# Regression (1)
# -------------------------------------------------------------------------

class TestRegression:

    def test_ev_7_65_regression(self):
        """25th verification: Strike Hard EV 7.65 after CP10.2."""
        from sim.scenario import load_scenario
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)
