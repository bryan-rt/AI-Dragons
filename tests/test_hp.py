"""Tests for HP infrastructure added in Checkpoint 4.5."""

from pf2e.abilities import AbilityScores
from pf2e.character import Character
from pf2e.combat_math import max_hp
from pf2e.equipment import EquippedWeapon
from pf2e.types import Ability, ProficiencyRank, SaveType, WeaponCategory
from tests.fixtures import WHIP, make_aetregan, make_dalai, make_erisen, make_rook


class TestMaxHp:

    def test_aetregan_max_hp_15(self) -> None:
        """Elf 6 + (Commander 8 + Con +1) x L1 = 15."""
        assert max_hp(make_aetregan()) == 15

    def test_rook_hp_populated(self) -> None:
        """Rook HP populated in CP5.1 Pass 3a.

        Automaton 10 + (Guardian 10 + Con +3) x 1 = 23.
        """
        rook = make_rook()
        assert rook.ancestry_hp == 10
        assert rook.class_hp == 10
        assert max_hp(rook) == 23

    def test_max_hp_scales_with_level(self) -> None:
        """Formula: ancestry_hp + (class_hp + Con) x level."""
        abilities = AbilityScores(
            str_=10, dex=14, con=14, int_=18, wis=10, cha=10,
        )
        c5 = Character(
            name="Test",
            level=5,
            abilities=abilities,
            key_ability=Ability.INT,
            weapon_proficiencies={
                WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
                WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
                WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
                WeaponCategory.ADVANCED: ProficiencyRank.UNTRAINED,
            },
            armor_proficiency=ProficiencyRank.TRAINED,
            perception_rank=ProficiencyRank.EXPERT,
            save_ranks={
                SaveType.FORTITUDE: ProficiencyRank.TRAINED,
                SaveType.REFLEX: ProficiencyRank.EXPERT,
                SaveType.WILL: ProficiencyRank.EXPERT,
            },
            class_dc_rank=ProficiencyRank.TRAINED,
            equipped_weapons=(EquippedWeapon(WHIP),),
            ancestry_hp=6,
            class_hp=8,
        )
        # 6 + (8 + 2) x 5 = 56
        assert max_hp(c5) == 56
