"""Party definitions for the Outlaws of Alkenstar campaign.

Canonical character builds, equipment constants, and grid-token
factory mappings. Used by the scenario loader and test fixtures.

Phase B: factories now call import_foundry_actor() for all four characters.
Equipment constants retained for backward compatibility with tests.
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
from dataclasses import replace as _replace

from sim.importers.foundry import import_foundry_actor

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
    """Aetregan (Commander). Data sourced from Foundry VTT actor export.

    Foundry name "Jotan Aethregen" → canonical "Aetregan" for scenario compat.
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=66 — Commander)
    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60 — Elf)
    """
    return _replace(import_foundry_actor("characters/fvtt-aetregan.json"), name="Aetregan")


def make_rook() -> Character:
    """Rook (Guardian). Data sourced from Foundry VTT actor export.

    Speed: base 25 (Automaton). Full plate penalty applied via
    CombatantState.current_speed=20 (see make_rook_combat_state).
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=67 — Guardian)
    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=48 — Automaton)
    """
    return import_foundry_actor("characters/fvtt-rook.json")


def make_dalai() -> Character:
    """Dalai Alpaca (Bard). Data sourced from Foundry VTT actor export.

    (AoN: https://2e.aonprd.com/Classes.aspx?ID=62 — Bard)
    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=64 — Human)
    """
    return import_foundry_actor("characters/fvtt-dalai.json")


def make_erisen() -> Character:
    """Erisen (Inventor). Data sourced from Foundry VTT actor export.

    Foundry name "Erizin" → canonical "Erisen" for scenario compat.
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=65 — Inventor)
    (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60 — Elf)
    """
    return _replace(import_foundry_actor("characters/fvtt-erisen.json"), name="Erisen")


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
