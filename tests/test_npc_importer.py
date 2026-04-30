"""Tests for NPC importer + EnemyState/Snapshot changes (Phase C.2)."""

import pytest

from pf2e.character import EnemyState
from pf2e.detection import VisionType
from pf2e.types import Ability, SaveType, Skill
from sim.importers.foundry_npc import (
    _parse_damage_formula, import_foundry_npc,
)
from sim.round_state import EnemySnapshot

WARRIOR = "characters/enemies/goblin-warrior.json"
CHANTER = "characters/enemies/goblin-war-chanter.json"
DOG = "characters/enemies/goblin-dog.json"


# -------------------------------------------------------------------
# Damage formula parser
# -------------------------------------------------------------------

class TestDamageFormulaParser:

    def test_basic(self):
        assert _parse_damage_formula("1d6+2") == ("1d6", 2)

    def test_multi_dice(self):
        assert _parse_damage_formula("2d4+3") == ("2d4", 3)

    def test_negative_bonus(self):
        assert _parse_damage_formula("1d6-1") == ("1d6", -1)

    def test_no_bonus(self):
        assert _parse_damage_formula("1d8") == ("1d8", 0)

    def test_malformed_fallback(self):
        assert _parse_damage_formula("bad") == ("1d4", 0)


# -------------------------------------------------------------------
# Goblin Warrior import
# -------------------------------------------------------------------

class TestGoblinWarrior:

    def test_core_stats(self):
        npc = import_foundry_npc(WARRIOR)
        assert npc.name == "Goblin Warrior"
        assert npc.level == -1
        assert npc._max_hp == 6
        assert npc._ac_total == 16
        assert npc.speed == 25

    def test_saves(self):
        npc = import_foundry_npc(WARRIOR)
        assert npc._save_totals[SaveType.FORTITUDE] == 5
        assert npc._save_totals[SaveType.REFLEX] == 7
        assert npc._save_totals[SaveType.WILL] == 3

    def test_perception(self):
        npc = import_foundry_npc(WARRIOR)
        assert npc._perception_total == 2

    def test_vision(self):
        npc = import_foundry_npc(WARRIOR)
        assert npc.vision_type == VisionType.DARKVISION

    def test_ability_mods(self):
        npc = import_foundry_npc(WARRIOR)
        assert npc.abilities.mod(Ability.DEX) == 3
        assert npc.abilities.mod(Ability.STR) == 0
        assert npc.abilities.mod(Ability.WIS) == -1

    def test_dogslicer_attack_total(self):
        npc = import_foundry_npc(WARRIOR)
        # Melee item Dogslicer has bonus.value = 7
        assert npc._attack_totals.get("Dogslicer") == 7

    def test_dogslicer_equipped_weapon(self):
        npc = import_foundry_npc(WARRIOR)
        dogslicer = next(
            (eq for eq in npc.equipped_weapons
             if eq.weapon.name == "Dogslicer"), None)
        assert dogslicer is not None

    def test_dogslicer_is_agile(self):
        npc = import_foundry_npc(WARRIOR)
        dogslicer = next(
            eq for eq in npc.equipped_weapons
            if eq.weapon.name == "Dogslicer")
        assert dogslicer.weapon.is_agile

    def test_skills(self):
        npc = import_foundry_npc(WARRIOR)
        assert npc._skill_totals.get(Skill.STEALTH) == 5
        assert npc._skill_totals.get(Skill.ACROBATICS) == 5


# -------------------------------------------------------------------
# Goblin War Chanter import
# -------------------------------------------------------------------

class TestGoblinWarChanter:

    def test_core_stats(self):
        npc = import_foundry_npc(CHANTER)
        assert npc.name == "Goblin War Chanter"
        assert npc.level == 1
        assert npc._max_hp == 16
        assert npc._ac_total == 17

    def test_spellcasting(self):
        npc = import_foundry_npc(CHANTER)
        assert npc._spell_dc == 17
        assert npc._spell_attack_total == 7

    def test_key_ability_is_cha(self):
        npc = import_foundry_npc(CHANTER)
        assert npc.key_ability == Ability.CHA

    def test_dogslicer_attack_total(self):
        npc = import_foundry_npc(CHANTER)
        assert npc._attack_totals.get("Dogslicer") == 8


# -------------------------------------------------------------------
# Goblin Dog import
# -------------------------------------------------------------------

class TestGoblinDog:

    def test_core_stats(self):
        npc = import_foundry_npc(DOG)
        assert npc.name == "Goblin Dog"
        assert npc.level == 1
        assert npc._max_hp == 17
        assert npc._ac_total == 15
        assert npc.speed == 40

    def test_synthetic_jaws_weapon(self):
        npc = import_foundry_npc(DOG)
        jaws = next(
            (eq for eq in npc.equipped_weapons
             if "Jaws" in eq.weapon.name), None)
        assert jaws is not None, (
            "Goblin Dog Jaws should be synthesized from melee item")
        assert jaws.weapon.damage_die == "d6"

    def test_jaws_attack_total(self):
        npc = import_foundry_npc(DOG)
        assert npc._attack_totals.get("Jaws") == 9

    def test_vision_low_light(self):
        npc = import_foundry_npc(DOG)
        assert npc.vision_type == VisionType.LOW_LIGHT


# -------------------------------------------------------------------
# Error handling
# -------------------------------------------------------------------

class TestImportErrors:

    def test_wrong_type_raises(self):
        with pytest.raises(ValueError, match="type='npc'"):
            import_foundry_npc("characters/fvtt-rook.json")

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            import_foundry_npc("characters/enemies/nonexistent.json")


# -------------------------------------------------------------------
# EnemyState / EnemySnapshot character propagation
# -------------------------------------------------------------------

class TestCharacterPropagation:

    def test_enemy_state_character_field(self):
        npc = import_foundry_npc(WARRIOR)
        state = EnemyState(
            name="Goblin", ac=16,
            saves={SaveType.FORTITUDE: 5, SaveType.REFLEX: 7,
                   SaveType.WILL: 3},
            position=(0, 0), character=npc,
        )
        assert state.character is npc

    def test_enemy_snapshot_propagates_character(self):
        npc = import_foundry_npc(WARRIOR)
        state = EnemyState(
            name="Goblin", ac=16,
            saves={SaveType.FORTITUDE: 5, SaveType.REFLEX: 7,
                   SaveType.WILL: 3},
            position=(0, 0), character=npc,
        )
        snap = EnemySnapshot.from_enemy_state(state)
        assert snap.character is npc

    def test_legacy_enemy_state_character_none(self):
        state = EnemyState(
            name="Bandit", ac=15,
            saves={SaveType.FORTITUDE: 5, SaveType.REFLEX: 7,
                   SaveType.WILL: 3},
            position=(0, 0),
        )
        assert state.character is None
        snap = EnemySnapshot.from_enemy_state(state)
        assert snap.character is None


# -------------------------------------------------------------------
# Regression
# -------------------------------------------------------------------

def test_ev_7_65_regression():
    """EV 7.65 unchanged — 45th verification."""
    from pf2e.tactics import evaluate_tactic, STRIKE_HARD
    from sim.scenario import load_scenario
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    ctx = scenario.build_tactic_context()
    result = evaluate_tactic(STRIKE_HARD, ctx)
    assert result.expected_damage_dealt == pytest.approx(7.65, abs=0.01)
