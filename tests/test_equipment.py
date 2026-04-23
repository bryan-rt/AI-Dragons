"""Tests for weapon, armor, and shield dataclasses."""

from tests.fixtures import (
    DAGGER,
    FULL_PLATE,
    JAVELIN,
    LEATHER_ARMOR,
    LONGSWORD,
    RAPIER,
    STEEL_SHIELD,
    STUDDED_LEATHER,
    SUBTERFUGE_SUIT,
    WHIP,
)
from pf2e.equipment import EquippedWeapon, Weapon, WeaponRunes
from pf2e.types import DamageType, WeaponCategory, WeaponGroup


class TestWhip:
    def test_traits(self) -> None:
        assert WHIP.is_finesse
        assert not WHIP.is_agile
        assert not WHIP.is_thrown
        assert not WHIP.is_propulsive
        assert "reach" in WHIP.traits
        assert "trip" in WHIP.traits
        assert "disarm" in WHIP.traits
        assert "nonlethal" in WHIP.traits

    def test_melee(self) -> None:
        assert WHIP.is_melee
        assert not WHIP.is_ranged

    def test_stats(self) -> None:
        assert WHIP.category == WeaponCategory.MARTIAL
        assert WHIP.group == WeaponGroup.FLAIL
        assert WHIP.damage_die == "d4"
        assert WHIP.damage_die_count == 1
        assert WHIP.damage_type == DamageType.SLASHING


class TestLongsword:
    def test_stats(self) -> None:
        assert LONGSWORD.category == WeaponCategory.MARTIAL
        assert LONGSWORD.group == WeaponGroup.SWORD
        assert LONGSWORD.damage_die == "d8"
        assert LONGSWORD.damage_die_count == 1
        assert LONGSWORD.damage_type == DamageType.SLASHING

    def test_traits(self) -> None:
        assert not LONGSWORD.is_finesse
        assert not LONGSWORD.is_agile
        assert "versatile_p" in LONGSWORD.traits

    def test_melee(self) -> None:
        assert LONGSWORD.is_melee
        assert not LONGSWORD.is_ranged


class TestRapier:
    def test_finesse_and_deadly(self) -> None:
        assert RAPIER.is_finesse
        assert RAPIER.deadly_die == "d8"
        assert "disarm" in RAPIER.traits

    def test_stats(self) -> None:
        assert RAPIER.damage_die == "d6"
        assert RAPIER.category == WeaponCategory.MARTIAL


class TestDagger:
    def test_traits(self) -> None:
        assert DAGGER.is_agile
        assert DAGGER.is_finesse
        assert DAGGER.is_thrown
        assert "versatile_s" in DAGGER.traits

    def test_stats(self) -> None:
        assert DAGGER.category == WeaponCategory.SIMPLE
        assert DAGGER.damage_die == "d4"
        assert DAGGER.range_increment == 10

    def test_dual_mode(self) -> None:
        """Dagger is both melee (thrown-melee) and ranged (has range increment).

        (AoN: https://2e.aonprd.com/Weapons.aspx?ID=358)
        (AoN: https://2e.aonprd.com/Traits.aspx?ID=195)
        """
        assert DAGGER.is_melee   # thrown-melee weapon usable in melee
        assert DAGGER.is_ranged  # has range increment, can be thrown


class TestJavelin:
    """Javelin: pure thrown weapon (melee + ranged).

    (AoN: https://2e.aonprd.com/Weapons.aspx?ID=71)
    """

    def test_thrown(self) -> None:
        assert JAVELIN.is_thrown
        assert JAVELIN.range_increment == 30

    def test_dual_mode(self) -> None:
        """Javelin is both melee (thrown trait) and ranged (range increment)."""
        assert JAVELIN.is_melee
        assert JAVELIN.is_ranged

    def test_not_finesse(self) -> None:
        assert not JAVELIN.is_finesse
        assert not JAVELIN.is_agile


class TestMeleeRangedClassification:
    """Verify is_melee/is_ranged for all weapon archetypes."""

    def test_pure_melee(self) -> None:
        """Longsword: no range increment, no thrown → melee only."""
        assert LONGSWORD.is_melee
        assert not LONGSWORD.is_ranged

    def test_thrown_melee(self) -> None:
        """Dagger: thrown trait + range increment → both melee and ranged."""
        assert DAGGER.is_melee
        assert DAGGER.is_ranged

    def test_pure_ranged(self) -> None:
        """A longbow (no thrown trait, has range) → ranged only."""
        longbow = Weapon(
            name="Longbow",
            category=WeaponCategory.MARTIAL,
            group=WeaponGroup.BOW,
            damage_die="d8",
            damage_die_count=1,
            damage_type=DamageType.PIERCING,
            range_increment=100,
            traits=frozenset({"deadly_d10", "volley_30"}),
            hands=2,
        )
        assert not longbow.is_melee
        assert longbow.is_ranged


class TestSteelShield:
    def test_stats(self) -> None:
        assert STEEL_SHIELD.ac_bonus == 2
        assert STEEL_SHIELD.hardness == 5
        assert STEEL_SHIELD.hp == 20
        assert STEEL_SHIELD.bt == 10


class TestFullPlate:
    def test_stats(self) -> None:
        assert FULL_PLATE.ac_bonus == 6
        assert FULL_PLATE.dex_cap == 0
        assert FULL_PLATE.check_penalty == -3
        assert FULL_PLATE.strength_threshold == 18


class TestEquippedWeapon:
    def test_no_runes(self) -> None:
        eq = EquippedWeapon(LONGSWORD)
        assert eq.potency_bonus == 0
        assert eq.total_damage_dice == 1

    def test_with_runes(self) -> None:
        runes = WeaponRunes(potency=1, striking=1)
        eq = EquippedWeapon(LONGSWORD, runes)
        assert eq.potency_bonus == 1
        assert eq.total_damage_dice == 2
