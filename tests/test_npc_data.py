"""Tests for NPCData + combat_math override hooks (Phase C.1)."""

import pytest

from pf2e.abilities import AbilityScores
from pf2e.combat_math import (
    armor_class, attack_bonus, class_dc, max_hp,
    perception_bonus, save_bonus, skill_bonus, spell_attack_bonus,
)
from pf2e.character import Character, CombatantState
from pf2e.equipment import ArmorData, EquippedWeapon, Weapon, WeaponRunes
from pf2e.npc_data import NPCData
from pf2e.types import (
    Ability, DamageType, ProficiencyRank, SaveType, Skill,
    WeaponCategory, WeaponGroup,
)

SCENARIO_1 = "scenarios/checkpoint_1_strike_hard.scenario"
EV_TOLERANCE = 0.01


def _make_npc(**kwargs) -> NPCData:
    """Build a minimal NPCData with overridable defaults."""
    defaults = dict(
        name="Test NPC", level=1, speed=25,
        abilities=AbilityScores(
            str_=10, dex=16, con=12, int_=10, wis=10, cha=10),
    )
    defaults.update(kwargs)
    return NPCData(**defaults)


def _make_npc_state(npc: NPCData) -> CombatantState:
    """Build a minimal CombatantState with NPCData as character."""
    return CombatantState(character=npc, position=(0, 0))


# -------------------------------------------------------------------
# Override hook return values
# -------------------------------------------------------------------

class TestOverrideHooks:

    def test_npc_attack_total_returns_stored(self):
        npc = _make_npc(_attack_totals={"Dogslicer": 8})
        assert npc.npc_attack_total("Dogslicer") == 8

    def test_npc_attack_total_missing_returns_none(self):
        npc = _make_npc(_attack_totals={"Dogslicer": 8})
        assert npc.npc_attack_total("Nonexistent") is None

    def test_npc_ac_total(self):
        npc = _make_npc(_ac_total=16)
        assert npc.npc_ac_total() == 16

    def test_npc_save_total(self):
        npc = _make_npc(_save_totals={
            SaveType.FORTITUDE: 5, SaveType.REFLEX: 7, SaveType.WILL: 3})
        assert npc.npc_save_total(SaveType.REFLEX) == 7

    def test_npc_perception_total(self):
        npc = _make_npc(_perception_total=2)
        assert npc.npc_perception_total() == 2

    def test_npc_max_hp(self):
        npc = _make_npc(_max_hp=6)
        assert npc.npc_max_hp() == 6

    def test_npc_class_dc_zero_returns_none(self):
        npc = _make_npc(_spell_dc=0)
        assert npc.npc_class_dc() is None

    def test_npc_class_dc_nonzero(self):
        npc = _make_npc(_spell_dc=17)
        assert npc.npc_class_dc() == 17

    def test_npc_spell_attack_zero_returns_none(self):
        npc = _make_npc(_spell_attack_total=0)
        assert npc.npc_spell_attack() is None

    def test_npc_spell_attack_nonzero(self):
        npc = _make_npc(_spell_attack_total=7)
        assert npc.npc_spell_attack() == 7

    def test_npc_skill_total(self):
        npc = _make_npc(_skill_totals={Skill.STEALTH: 5})
        assert npc.npc_skill_total(Skill.STEALTH) == 5
        assert npc.npc_skill_total(Skill.ATHLETICS) is None


# -------------------------------------------------------------------
# combat_math.py uses NPC overrides
# -------------------------------------------------------------------

class TestCombatMathOverrides:

    def test_max_hp_uses_npc_override(self):
        npc = _make_npc(_max_hp=17)
        assert max_hp(npc) == 17

    def test_save_bonus_uses_npc_override(self):
        npc = _make_npc(_save_totals={SaveType.FORTITUDE: 8})
        assert save_bonus(npc, SaveType.FORTITUDE) == 8

    def test_perception_uses_npc_override(self):
        npc = _make_npc(_perception_total=6)
        assert perception_bonus(npc) == 6

    def test_class_dc_uses_npc_override(self):
        npc = _make_npc(_spell_dc=17)
        assert class_dc(npc) == 17

    def test_spell_attack_uses_npc_override(self):
        npc = _make_npc(_spell_attack_total=7)
        assert spell_attack_bonus(npc) == 7

    def test_skill_bonus_uses_npc_override(self):
        npc = _make_npc(_skill_totals={Skill.STEALTH: 5})
        assert skill_bonus(npc, Skill.STEALTH) == 5

    def test_attack_bonus_uses_npc_override(self):
        """NPC base attack total + MAP applied correctly."""
        weapon = Weapon(
            name="Dogslicer", category=WeaponCategory.MARTIAL,
            group=WeaponGroup.SWORD, damage_die="d6",
            damage_die_count=1, damage_type=DamageType.SLASHING,
            range_increment=None, traits=frozenset({"agile", "finesse"}),
            hands=1,
        )
        equipped = EquippedWeapon(weapon=weapon)
        npc = _make_npc(_attack_totals={"Dogslicer": 8})
        state = _make_npc_state(npc)
        # No MAP
        assert attack_bonus(state, equipped, map_penalty=0) == 8
        # With MAP -4 (agile second attack)
        assert attack_bonus(state, equipped, map_penalty=-4) == 4

    def test_armor_class_uses_npc_override(self):
        npc = _make_npc(_ac_total=16)
        state = _make_npc_state(npc)
        assert armor_class(state) == 16

    def test_armor_class_npc_off_guard_penalty(self):
        npc = _make_npc(_ac_total=16)
        state = CombatantState(
            character=npc, position=(0, 0), off_guard=True)
        assert armor_class(state) == 14  # 16 - 2


# -------------------------------------------------------------------
# PC behavior unchanged
# -------------------------------------------------------------------

class TestPCUnchanged:

    def test_max_hp_pc_unchanged(self):
        """PC max_hp derivation unaffected by override hooks."""
        from sim.scenario import load_scenario
        scenario = load_scenario(SCENARIO_1)
        all_pcs = [scenario.commander] + scenario.squadmates
        for pc in all_pcs:
            # PC Characters have no npc_max_hp method
            assert not hasattr(pc.character, 'npc_max_hp')
            hp = max_hp(pc.character)
            assert hp > 0

    def test_ev_7_65_regression(self):
        """EV 7.65 unchanged — 44th verification."""
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD
        from sim.scenario import load_scenario
        scenario = load_scenario(SCENARIO_1)
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(
            7.65, abs=EV_TOLERANCE)
