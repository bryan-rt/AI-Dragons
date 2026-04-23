"""Factory functions producing the four party characters at level 1.

All stats match the character sheets in Pass 2.5, Section A.2.
These are the canonical source of truth for tests.
"""

from pf2e.abilities import AbilityScores
from pf2e.character import Character
from pf2e.equipment import ArmorData, EquippedWeapon, Shield, Weapon, WeaponRunes
from pf2e.types import (
    Ability,
    DamageType,
    ProficiencyRank,
    SaveType,
    WeaponCategory,
    WeaponGroup,
)

# ---------------------------------------------------------------------------
# Shared equipment
# ---------------------------------------------------------------------------

STEEL_SHIELD = Shield(
    name="Steel Shield",
    ac_bonus=2,
    hardness=5,
    hp=20,
    bt=10,
)

# ---------------------------------------------------------------------------
# Weapons
# ---------------------------------------------------------------------------

WHIP = Weapon(
    name="Whip",
    category=WeaponCategory.MARTIAL,
    group=WeaponGroup.FLAIL,
    damage_die="d4",
    damage_die_count=1,
    damage_type=DamageType.SLASHING,
    range_increment=None,
    traits=frozenset({"finesse", "reach", "trip", "disarm", "nonlethal"}),
    hands=1,
)

LONGSWORD = Weapon(
    name="Longsword",
    category=WeaponCategory.MARTIAL,
    group=WeaponGroup.SWORD,
    damage_die="d8",
    damage_die_count=1,
    damage_type=DamageType.SLASHING,
    range_increment=None,
    traits=frozenset({"versatile_p"}),
    hands=1,
)

RAPIER = Weapon(
    name="Rapier",
    category=WeaponCategory.MARTIAL,
    group=WeaponGroup.SWORD,
    damage_die="d6",
    damage_die_count=1,
    damage_type=DamageType.PIERCING,
    range_increment=None,
    traits=frozenset({"finesse", "deadly_d8", "disarm"}),
    hands=1,
)

DAGGER = Weapon(
    name="Dagger",
    category=WeaponCategory.SIMPLE,
    group=WeaponGroup.KNIFE,
    damage_die="d4",
    damage_die_count=1,
    damage_type=DamageType.PIERCING,
    range_increment=None,  # melee mode (can also be thrown, handled separately)
    traits=frozenset({"agile", "finesse", "thrown_10", "versatile_s"}),
    hands=1,
)


# ---------------------------------------------------------------------------
# Armor
# ---------------------------------------------------------------------------

SUBTERFUGE_SUIT = ArmorData(
    name="Inventor Subterfuge Suit",
    ac_bonus=2,
    dex_cap=None,  # functions as light armor for movement/Dex cap purposes
    check_penalty=0,
    speed_penalty=0,
    strength_threshold=0,
)

FULL_PLATE = ArmorData(
    name="Full Plate",
    ac_bonus=6,
    dex_cap=0,
    check_penalty=-3,
    speed_penalty=-10,
    strength_threshold=18,
)

LEATHER_ARMOR = ArmorData(
    name="Leather Armor",
    ac_bonus=1,
    dex_cap=4,
    check_penalty=-1,
    speed_penalty=0,
    strength_threshold=0,
)

STUDDED_LEATHER = ArmorData(
    name="Studded Leather",
    ac_bonus=2,
    dex_cap=3,
    check_penalty=-1,
    speed_penalty=0,
    strength_threshold=0,
)


# ---------------------------------------------------------------------------
# Character factories
# ---------------------------------------------------------------------------

def make_aetregan() -> Character:
    """Aetregan — Commander (Battlecry!), level 1.

    Key ability: INT. Wields whip (finesse), wears subterfuge suit,
    carries steel shield. Has Shield Block.

    AC: 10 + Dex 3 + trained medium 3 + suit 2 = 18 (no shield)
    Class DC: 10 + Int 4 + trained 3 = 17
    """
    return Character(
        name="Aetregan",
        level=1,
        abilities=AbilityScores(
            str_=10, dex=16, con=12, int_=18, wis=11, cha=12,
        ),
        key_ability=Ability.INT,
        weapon_proficiencies={
            WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
            WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
            WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
            WeaponCategory.ADVANCED: ProficiencyRank.UNTRAINED,
        },
        armor_proficiency=ProficiencyRank.TRAINED,  # medium
        perception_rank=ProficiencyRank.TRAINED,
        save_ranks={
            SaveType.FORTITUDE: ProficiencyRank.TRAINED,
            SaveType.REFLEX: ProficiencyRank.EXPERT,
            SaveType.WILL: ProficiencyRank.EXPERT,
        },
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=(EquippedWeapon(WHIP),),
        armor=SUBTERFUGE_SUIT,
        shield=STEEL_SHIELD,
        has_shield_block=True,
    )


def make_rook() -> Character:
    """Rook — Guardian, level 1.

    Key ability: STR. Wields longsword, wears full plate,
    carries steel shield. Has Shield Block + guardian reactions.

    AC: 10 + Dex 0 (capped 0) + trained heavy 3 + full plate 6 = 19
    Class DC: 10 + Str 4 + trained 3 = 17
    """
    return Character(
        name="Rook",
        level=1,
        abilities=AbilityScores(
            str_=18, dex=10, con=16, int_=10, wis=12, cha=12,
        ),
        key_ability=Ability.STR,
        weapon_proficiencies={
            WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
            WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
            WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
            WeaponCategory.ADVANCED: ProficiencyRank.UNTRAINED,
        },
        armor_proficiency=ProficiencyRank.TRAINED,  # heavy
        perception_rank=ProficiencyRank.EXPERT,
        save_ranks={
            SaveType.FORTITUDE: ProficiencyRank.EXPERT,
            SaveType.REFLEX: ProficiencyRank.TRAINED,
            SaveType.WILL: ProficiencyRank.EXPERT,
        },
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=(EquippedWeapon(LONGSWORD),),
        armor=FULL_PLATE,
        shield=STEEL_SHIELD,
        has_shield_block=True,
        guardian_reactions=1,
    )


def make_dalai() -> Character:
    """Dalai Alpaca — Bard (Warrior Muse), level 1.

    Key ability: CHA. Wields rapier (finesse, deadly d8),
    wears leather armor. No shield.

    AC: 10 + Dex 2 + trained light 3 + leather 1 = 16
    Class DC: 10 + Cha 4 + trained 3 = 17
    """
    return Character(
        name="Dalai Alpaca",
        level=1,
        abilities=AbilityScores(
            str_=10, dex=14, con=12, int_=14, wis=10, cha=18,
        ),
        key_ability=Ability.CHA,
        weapon_proficiencies={
            WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
            WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
            WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
            WeaponCategory.ADVANCED: ProficiencyRank.UNTRAINED,
        },
        armor_proficiency=ProficiencyRank.TRAINED,  # light
        perception_rank=ProficiencyRank.EXPERT,
        save_ranks={
            SaveType.FORTITUDE: ProficiencyRank.TRAINED,
            SaveType.REFLEX: ProficiencyRank.TRAINED,
            SaveType.WILL: ProficiencyRank.EXPERT,
        },
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=(EquippedWeapon(RAPIER),),
        armor=LEATHER_ARMOR,
    )


def make_erisen() -> Character:
    """Erisen — Inventor (Munitions Master), level 1.

    Key ability: INT. Wields dagger (agile, finesse, thrown 10),
    wears studded leather. Has light mortar innovation (siege weapon).

    AC: 10 + Dex 2 (capped 3) + trained medium 3 + studded leather 2 = 17
    Class DC: 10 + Int 4 + trained 3 = 17
    """
    return Character(
        name="Erisen",
        level=1,
        abilities=AbilityScores(
            str_=10, dex=14, con=14, int_=18, wis=10, cha=12,
        ),
        key_ability=Ability.INT,
        weapon_proficiencies={
            WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
            WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
            WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
            WeaponCategory.ADVANCED: ProficiencyRank.UNTRAINED,
        },
        armor_proficiency=ProficiencyRank.TRAINED,  # medium
        perception_rank=ProficiencyRank.TRAINED,
        save_ranks={
            SaveType.FORTITUDE: ProficiencyRank.EXPERT,
            SaveType.REFLEX: ProficiencyRank.EXPERT,
            SaveType.WILL: ProficiencyRank.TRAINED,
        },
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=(EquippedWeapon(DAGGER),),
        armor=STUDDED_LEATHER,
    )
