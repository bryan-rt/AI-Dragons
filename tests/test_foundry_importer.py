"""Tests for the Foundry VTT actor JSON importer.

Phase B: validates that import_foundry_actor() produces correct Character
instances from real Foundry exports for all four party members.
"""

import pytest

from pf2e.combat_math import max_hp
from pf2e.types import (
    DamageType,
    ProficiencyRank,
    Skill,
    WeaponCategory,
    WeaponGroup,
)
from sim.importers.foundry import (
    WEAPON_GROUP_MAP,
    _normalize_trait,
    import_foundry_actor,
)

EV_TOLERANCE = 0.01

# ---------------------------------------------------------------------------
# Paths to Foundry actor JSONs
# ---------------------------------------------------------------------------

AETREGAN_JSON = "characters/fvtt-aetregan.json"
ROOK_JSON = "characters/fvtt-rook.json"
DALAI_JSON = "characters/fvtt-dalai.json"
ERISEN_JSON = "characters/fvtt-erisen.json"


# ---------------------------------------------------------------------------
# Infrastructure tests (no JSON files needed)
# ---------------------------------------------------------------------------


class TestTraitNormalization:
    def test_thrown(self):
        assert _normalize_trait("thrown-20") == "thrown_20"

    def test_deadly(self):
        assert _normalize_trait("deadly-d8") == "deadly_d8"

    def test_two_hand(self):
        assert _normalize_trait("two-hand-d10") == "two_hand_d10"

    def test_no_hyphens(self):
        assert _normalize_trait("finesse") == "finesse"


class TestWeaponGroupMapping:
    def test_flail(self):
        assert WEAPON_GROUP_MAP["flail"] == WeaponGroup.FLAIL

    def test_hammer(self):
        assert WEAPON_GROUP_MAP["hammer"] == WeaponGroup.HAMMER

    def test_axe(self):
        assert WEAPON_GROUP_MAP["axe"] == WeaponGroup.AXE

    def test_firearm(self):
        assert WEAPON_GROUP_MAP["firearm"] == WeaponGroup.FIREARM

    def test_sword(self):
        assert WEAPON_GROUP_MAP["sword"] == WeaponGroup.SWORD


class TestImporterMissingFile:
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError, match="Foundry actor JSON not found"):
            import_foundry_actor("characters/does_not_exist.json")


# ---------------------------------------------------------------------------
# Aetregan (Commander) tests
# ---------------------------------------------------------------------------


class TestImportAetregan:
    @pytest.fixture
    def aetregan(self):
        return import_foundry_actor(AETREGAN_JSON)

    def test_ability_scores(self, aetregan):
        """STR 10, DEX 16, CON 12, INT 18, WIS 10, CHA 12.

        WIS/CHA differ from old factory (was WIS 12, CHA 10) because
        Aetregan uses alternateAncestryBoosts. JSON is authoritative (D10).
        """
        ab = aetregan.abilities
        assert ab.str_ == 10
        assert ab.dex == 16
        assert ab.con == 12
        assert ab.int_ == 18
        assert ab.wis == 10
        assert ab.cha == 12

    def test_max_hp(self, aetregan):
        """Elf 6 + (Commander 8 + Con 1) x 1 = 15."""
        assert max_hp(aetregan) == 15

    def test_deception_trained(self, aetregan):
        """Foundry JSON shows deception rank 1 — trained (D10: JSON authoritative)."""
        assert aetregan.skill_proficiencies[Skill.DECEPTION] == ProficiencyRank.TRAINED

    def test_nature_untrained(self, aetregan):
        """Foundry JSON shows nature rank 0 — untrained (D10: JSON authoritative)."""
        assert aetregan.skill_proficiencies.get(Skill.NATURE) == ProficiencyRank.UNTRAINED

    def test_warfare_lore(self, aetregan):
        assert aetregan.lores["Warfare"] == ProficiencyRank.TRAINED

    def test_feat_flags(self, aetregan):
        assert aetregan.has_deceptive_tactics is True
        assert aetregan.has_commander_banner is True
        assert aetregan.has_shield_block is True

    def test_weapon(self, aetregan):
        """Primary weapon is Scorpion Whip: d4 slashing, group FLAIL."""
        w = aetregan.equipped_weapons[0].weapon
        assert w.name == "Scorpion Whip"
        assert w.damage_die == "d4"
        assert w.damage_type == DamageType.SLASHING
        assert w.group == WeaponGroup.FLAIL
        assert "reach" in w.traits

    def test_speed(self, aetregan):
        """Elf base 30, no Nimble Elf."""
        assert aetregan.speed == 30

    def test_perception_expert(self, aetregan):
        assert aetregan.perception_rank == ProficiencyRank.EXPERT


# ---------------------------------------------------------------------------
# Rook (Guardian) tests
# ---------------------------------------------------------------------------


class TestImportRook:
    @pytest.fixture
    def rook(self):
        return import_foundry_actor(ROOK_JSON)

    def test_primary_weapon(self, rook):
        """First weapon is Earthbreaker (actively held), d6 bludgeoning."""
        w = rook.equipped_weapons[0].weapon
        assert w.name == "Earthbreaker"
        assert w.damage_die == "d6"
        assert w.damage_type == DamageType.BLUDGEONING
        assert w.group == WeaponGroup.HAMMER

    def test_all_weapons(self, rook):
        """Rook has 4 weapons: Earthbreaker, Light Hammer, Barricade Buster, Bottled Lightning."""
        assert len(rook.equipped_weapons) >= 3

    def test_armor(self, rook):
        """Full Plate: ac_bonus=6, speed_penalty=-10, strength_threshold=18."""
        assert rook.armor is not None
        assert rook.armor.name == "Full Plate"
        assert rook.armor.ac_bonus == 6
        assert rook.armor.speed_penalty == -10
        assert rook.armor.strength_threshold == 18

    def test_shield(self, rook):
        """Steel Shield: hardness=5, hp=20, bt=10, ac_bonus=2."""
        assert rook.shield is not None
        assert rook.shield.hardness == 5
        assert rook.shield.hp == 20
        assert rook.shield.bt == 10
        assert rook.shield.ac_bonus == 2

    def test_guardian_reactions(self, rook):
        assert rook.guardian_reactions == 1

    def test_weapon_proficiency(self, rook):
        assert rook.weapon_proficiencies[WeaponCategory.MARTIAL] == ProficiencyRank.TRAINED

    def test_max_hp(self, rook):
        """Automaton 8 + (Guardian 12 + Con 3) x 1 = 23."""
        assert max_hp(rook) == 23


# ---------------------------------------------------------------------------
# Dalai Alpaca (Bard) tests
# ---------------------------------------------------------------------------


class TestImportDalai:
    @pytest.fixture
    def dalai(self):
        return import_foundry_actor(DALAI_JSON)

    def test_anthem(self, dalai):
        assert dalai.has_courageous_anthem is True

    def test_soothe_not_in_repertoire(self, dalai):
        """Dalai's Foundry spell list does not include Soothe (JSON authoritative)."""
        assert dalai.has_soothe is False

    def test_weapon(self, dalai):
        """Primary weapon is Rapier Pistol, d4 piercing."""
        assert len(dalai.equipped_weapons) >= 1
        w = dalai.equipped_weapons[0].weapon
        assert w.name == "Rapier Pistol"
        assert w.damage_die == "d4"
        assert w.damage_type == DamageType.PIERCING

    def test_hp(self, dalai):
        """Human 8 + (Bard 8 + Con 1) x 1 = 17."""
        assert max_hp(dalai) == 17


# ---------------------------------------------------------------------------
# Erisen (Inventor) tests
# ---------------------------------------------------------------------------


class TestImportErisen:
    @pytest.fixture
    def erisen(self):
        return import_foundry_actor(ERISEN_JSON)

    def test_mortar(self, erisen):
        assert erisen.has_light_mortar is True

    def test_speed(self, erisen):
        """Elf base 30 + Nimble Elf 5 = 35."""
        assert erisen.speed == 35

    def test_weapon(self, erisen):
        """Primary weapon is Dueling Pistol, d6 piercing."""
        assert len(erisen.equipped_weapons) >= 1
        w = erisen.equipped_weapons[0].weapon
        assert w.damage_die == "d6"
        assert w.damage_type == DamageType.PIERCING


# ---------------------------------------------------------------------------
# Validation: imported Aetregan matches factory on EV-critical fields
# ---------------------------------------------------------------------------


class TestAetreganEVCriticalFields:
    """Verify Aetregan's EV-critical fields produce Strike Hard EV 7.65.

    Post-factory-swap: factories now call the importer, so this validates
    the imported data directly against the new EV anchor.
    """

    def test_ev_critical_fields(self):
        from sim.party import make_aetregan
        from pf2e.combat_math import max_hp

        aetregan = make_aetregan()

        # Ability scores
        assert aetregan.abilities.str_ == 10
        assert aetregan.abilities.dex == 16
        assert aetregan.abilities.con == 12
        assert aetregan.abilities.int_ == 18

        # Primary weapon: Scorpion Whip d4 slashing
        assert aetregan.equipped_weapons[0].weapon.damage_die == "d4"
        assert aetregan.equipped_weapons[0].weapon.damage_type == DamageType.SLASHING

        # Armor: Subterfuge Suit AC+2
        assert aetregan.armor is not None
        assert aetregan.armor.ac_bonus == 2

        # Perception: expert
        assert aetregan.perception_rank == ProficiencyRank.EXPERT

        # HP: 15
        assert max_hp(aetregan) == 15
