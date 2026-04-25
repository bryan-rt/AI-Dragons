"""Party definitions for the Outlaws of Alkenstar campaign.

Canonical character builds, equipment constants, and grid-token
factory mappings. Used by the scenario loader and test fixtures.
"""

from __future__ import annotations

from typing import Callable

from pf2e.abilities import AbilityScores
from pf2e.character import Character, CombatantState
from pf2e.equipment import ArmorData, EquippedWeapon, Shield, Weapon, WeaponRunes
from pf2e.types import (
    Ability,
    DamageType,
    ProficiencyRank,
    SaveType,
    Skill,
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

SCORPION_WHIP = Weapon(
    name="Scorpion Whip",
    category=WeaponCategory.MARTIAL,
    group=WeaponGroup.FLAIL,
    damage_die="d4",
    damage_die_count=1,
    damage_type=DamageType.SLASHING,
    range_increment=None,
    # Same as Whip minus nonlethal: scorpion whips deal lethal damage.
    # (AoN: https://2e.aonprd.com/Weapons.aspx?ID=114)
    traits=frozenset({"finesse", "reach", "trip", "disarm"}),
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

JAVELIN = Weapon(
    name="Javelin",
    category=WeaponCategory.SIMPLE,
    group=WeaponGroup.DART,
    damage_die="d6",
    damage_die_count=1,
    damage_type=DamageType.PIERCING,
    range_increment=30,
    traits=frozenset({"thrown_30"}),
    hands=1,
)

DAGGER = Weapon(
    name="Dagger",
    category=WeaponCategory.SIMPLE,
    group=WeaponGroup.KNIFE,
    damage_die="d4",
    damage_die_count=1,
    damage_type=DamageType.PIERCING,
    range_increment=10,
    traits=frozenset({"agile", "finesse", "thrown_10", "versatile_s"}),
    hands=1,
)

# ---------------------------------------------------------------------------
# Armor
# ---------------------------------------------------------------------------

SUBTERFUGE_SUIT = ArmorData(
    name="Inventor Subterfuge Suit",
    ac_bonus=2,
    dex_cap=None,
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

    Key ability: INT. Wields Scorpion Whip (finesse, reach, trip, disarm),
    wears Inventor Subterfuge Suit, carries Steel Shield. Has Shield Block.

    AC: 10 + Dex 3 + trained medium 3 + suit 2 = 18 (no shield).
    Class DC: 10 + Int 4 + trained 3 = 17.
    Perception: Wis 1 + expert 5 = +6.
    Max HP: 6 (Elf) + (8 (Commander) + 1 (Con)) x 1 = 15.

    L1 Commander Feat: Deceptive Tactics (use Warfare Lore for Create
    a Diversion and Feint). Skill action modeling is CP5 work.
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=7794)

    Folio (5 tactics): Strike Hard!, Gather to Me!, Tactical Takedown,
    Mountaineering Training, Shields Up!.
    Prepared (3): Strike Hard!, Gather to Me!, Tactical Takedown.

    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60 — Elf)
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=66 — Commander)
    """
    return Character(
        name="Aetregan",
        level=1,
        abilities=AbilityScores(
            str_=10, dex=16, con=12, int_=18, wis=12, cha=10,
        ),
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
        equipped_weapons=(EquippedWeapon(SCORPION_WHIP),),
        armor=SUBTERFUGE_SUIT,
        shield=STEEL_SHIELD,
        has_shield_block=True,
        speed=30,
        ancestry_hp=6,
        class_hp=8,
        skill_proficiencies={
            Skill.ACROBATICS: ProficiencyRank.TRAINED,
            Skill.ARCANA: ProficiencyRank.TRAINED,
            Skill.CRAFTING: ProficiencyRank.TRAINED,
            Skill.NATURE: ProficiencyRank.TRAINED,
            Skill.OCCULTISM: ProficiencyRank.TRAINED,
            Skill.RELIGION: ProficiencyRank.TRAINED,
            Skill.SOCIETY: ProficiencyRank.TRAINED,
            Skill.STEALTH: ProficiencyRank.TRAINED,
            Skill.SURVIVAL: ProficiencyRank.TRAINED,
            Skill.THIEVERY: ProficiencyRank.TRAINED,
        },
        lores={
            "Warfare": ProficiencyRank.TRAINED,
            "Deity": ProficiencyRank.TRAINED,
        },
        has_plant_banner=False,
        has_deceptive_tactics=True,
        has_lengthy_diversion=True,
        has_commander_banner=True,
    )


def make_rook() -> Character:
    """Rook — Guardian, level 1.

    Key ability: STR. Wields longsword, wears full plate,
    carries steel shield. Has Shield Block + guardian reactions.

    AC: 10 + Dex 0 (capped 0) + trained heavy 3 + full plate 6 = 19
    Class DC: 10 + Str 4 + trained 3 = 17

    Speed: base 25 (Automaton). Full plate penalty applied via
    CombatantState.current_speed=20 (see make_rook_combat_state).
    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=48)
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
        armor_proficiency=ProficiencyRank.TRAINED,
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
        ancestry_hp=10,   # Automaton
        class_hp=10,      # Guardian
        skill_proficiencies={
            Skill.ATHLETICS: ProficiencyRank.TRAINED,
            Skill.INTIMIDATION: ProficiencyRank.TRAINED,
            Skill.SOCIETY: ProficiencyRank.TRAINED,
            Skill.CRAFTING: ProficiencyRank.TRAINED,
        },
    )


def make_dalai() -> Character:
    """Dalai Alpaca — Bard (Warrior Muse), level 1.

    Key ability: CHA. Wields rapier (finesse, deadly d8),
    wears leather armor. No shield.

    AC: 10 + Dex 2 + trained light 3 + leather 1 = 16
    Class DC: 10 + Cha 4 + trained 3 = 17
    Speed: 25 ft (Human base).
    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=64)
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
        armor_proficiency=ProficiencyRank.TRAINED,
        perception_rank=ProficiencyRank.EXPERT,
        save_ranks={
            SaveType.FORTITUDE: ProficiencyRank.TRAINED,
            SaveType.REFLEX: ProficiencyRank.TRAINED,
            SaveType.WILL: ProficiencyRank.EXPERT,
        },
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=(EquippedWeapon(RAPIER),),
        armor=LEATHER_ARMOR,
        ancestry_hp=8,    # Human
        class_hp=8,       # Bard
        skill_proficiencies={
            Skill.OCCULTISM: ProficiencyRank.TRAINED,
            Skill.PERFORMANCE: ProficiencyRank.TRAINED,
            Skill.DIPLOMACY: ProficiencyRank.TRAINED,
            Skill.INTIMIDATION: ProficiencyRank.TRAINED,
            Skill.ATHLETICS: ProficiencyRank.TRAINED,
            Skill.ACROBATICS: ProficiencyRank.TRAINED,
        },
        lores={
            "Bardic": ProficiencyRank.TRAINED,
            "Warfare": ProficiencyRank.TRAINED,
        },
    )


def make_erisen() -> Character:
    """Erisen — Inventor (Munitions Master), level 1.

    Key ability: INT. Wields dagger (agile, finesse, thrown 10),
    wears studded leather. Has light mortar innovation (siege weapon).

    AC: 10 + Dex 2 (capped 3) + trained medium 3 + studded leather 2 = 17
    Class DC: 10 + Int 4 + trained 3 = 17
    Speed: 35 ft (Elf base 30 + Nimble Elf +5).
    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60)
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=16)
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
        armor_proficiency=ProficiencyRank.TRAINED,
        perception_rank=ProficiencyRank.TRAINED,
        save_ranks={
            SaveType.FORTITUDE: ProficiencyRank.EXPERT,
            SaveType.REFLEX: ProficiencyRank.EXPERT,
            SaveType.WILL: ProficiencyRank.TRAINED,
        },
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=(EquippedWeapon(DAGGER),),
        armor=STUDDED_LEATHER,
        speed=35,
        ancestry_hp=6,    # Elf
        class_hp=8,       # Inventor
        skill_proficiencies={
            Skill.CRAFTING: ProficiencyRank.TRAINED,
            Skill.ARCANA: ProficiencyRank.TRAINED,
            Skill.SOCIETY: ProficiencyRank.TRAINED,
            Skill.ATHLETICS: ProficiencyRank.TRAINED,
            Skill.NATURE: ProficiencyRank.TRAINED,
        },
        lores={
            "Engineering": ProficiencyRank.TRAINED,
            "Alkenstar": ProficiencyRank.TRAINED,
        },
    )


def make_rook_combat_state(anthem_active: bool = False) -> CombatantState:
    """Rook's CombatantState with full plate speed penalty applied.

    Base Speed 25 - full plate penalty 10 + Str 18 threshold reduction 5 = 20 ft.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2169)
    """
    state = CombatantState.from_character(make_rook(), anthem_active=anthem_active)
    state.current_speed = 20
    return state


# ---------------------------------------------------------------------------
# Grid token → factory mapping
# ---------------------------------------------------------------------------

TOKEN_TO_FACTORY: dict[str, Callable[[], Character]] = {
    "c": make_aetregan,
    "g": make_rook,
    "b": make_dalai,
    "i": make_erisen,
}

COMMANDER_TOKEN = "c"
SQUADMATE_TOKENS: tuple[str, ...] = ("g", "b", "i")
