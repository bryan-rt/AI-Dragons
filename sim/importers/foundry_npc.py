"""Foundry VTT NPC JSON importer.

Loads type='npc' actor JSONs and produces NPCData with pre-calculated
combat stats. Uses _extract_weapons/_extract_armor/_extract_shield from
the PC importer for equipment items (same Foundry format).

Natural attacks (melee items with no matching weapon item) are converted
to synthetic EquippedWeapon instances.
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2187)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pf2e.abilities import AbilityScores
from pf2e.detection import VisionType
from pf2e.equipment import EquippedWeapon, Weapon, WeaponRunes
from pf2e.npc_data import NPCData
from pf2e.types import (
    DamageType, SaveType, Skill, WeaponCategory, WeaponGroup,
)
from sim.importers.foundry import (
    SKILL_NAME_MAP, _extract_armor, _extract_shield, _extract_weapons,
)


# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

_VISION_SENSE_MAP: dict[str, VisionType] = {
    "darkvision": VisionType.DARKVISION,
    "low-light-vision": VisionType.LOW_LIGHT,
    "lowLightVision": VisionType.LOW_LIGHT,
}

_DAMAGE_TYPE_MAP: dict[str, DamageType] = {
    "bludgeoning": DamageType.BLUDGEONING,
    "piercing": DamageType.PIERCING,
    "slashing": DamageType.SLASHING,
}


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _parse_damage_formula(formula: str) -> tuple[str, int]:
    """Parse 'NdM+B' or 'NdM' into (die_str, bonus_int).

    Examples:
        '1d6+2' -> ('1d6', 2)
        '1d6-1' -> ('1d6', -1)
        '1d6'   -> ('1d6', 0)
        '2d4+3' -> ('2d4', 3)
    """
    m = re.match(r'^(\d+d\d+)([+-]\d+)?', formula.strip())
    if not m:
        return ("1d4", 0)
    die = m.group(1)
    bonus = int(m.group(2)) if m.group(2) else 0
    return (die, bonus)


def _normalize_trait(trait: str) -> str:
    """Normalize Foundry kebab-case trait to underscore convention."""
    return trait.replace("-", "_")


def _synthetic_equipped_weapon(melee_item: dict) -> EquippedWeapon | None:
    """Build synthetic EquippedWeapon from a melee stat block entry.

    For natural attacks (Goblin Dog Jaws) that have no weapon inventory
    item — only a pre-calculated melee line.
    """
    system = melee_item.get("system", {})
    name = melee_item["name"]
    traits_raw = system.get("traits", {}).get("value", [])

    damage_rolls = system.get("damageRolls", {})
    if not damage_rolls:
        return None
    first_roll = next(iter(damage_rolls.values()))
    formula = first_roll.get("damage", "1d4")
    dmg_type_str = first_roll.get("damageType", "bludgeoning")

    die_str, bonus = _parse_damage_formula(formula)
    # Split NdM into count and die
    parts = die_str.split("d", 1)
    die_count = int(parts[0]) if len(parts) == 2 else 1
    die_face = f"d{parts[1]}" if len(parts) == 2 else "d4"

    dmg_type = _DAMAGE_TYPE_MAP.get(dmg_type_str, DamageType.BLUDGEONING)
    traits = frozenset(_normalize_trait(t) for t in traits_raw)

    weapon = Weapon(
        name=name,
        category=WeaponCategory.UNARMED,
        group=WeaponGroup.BRAWLING,
        damage_die=die_face,
        damage_die_count=die_count,
        damage_type=dmg_type,
        range_increment=None,
        traits=traits,
        hands=1,
    )
    # Store the flat damage bonus from the formula on the runes object
    # so damage_avg() picks it up via extra_flat or ability mod path.
    # Since NPCData uses override hooks for attack, we just need the
    # weapon structure to be valid for build_strike_outcomes.
    return EquippedWeapon(weapon=weapon)


# -------------------------------------------------------------------
# Main importer
# -------------------------------------------------------------------

def import_foundry_npc(path: str) -> NPCData:
    """Import a Foundry VTT NPC JSON and return NPCData.

    Raises FileNotFoundError if path does not exist.
    Raises ValueError if the JSON is not type='npc'.
    """
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"NPC JSON not found: {path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    if data.get("type") != "npc":
        raise ValueError(
            f"Expected type='npc', got {data.get('type')!r}. "
            f"Use import_foundry_actor() for PC characters."
        )

    system = data["system"]
    items: list[dict] = data.get("items", [])

    # --- Identity ---
    name: str = data["name"]
    level: int = system["details"]["level"]["value"]
    speed: int = (system.get("attributes", {})
                  .get("speed", {}).get("value", 25))

    # --- Ability scores (modifiers only in NPC JSONs) ---
    raw_ab = system.get("abilities", {})

    def _ab(key: str) -> int:
        return raw_ab.get(key, {}).get("mod", 0) * 2 + 10

    abilities = AbilityScores(
        str_=_ab("str"), dex=_ab("dex"), con=_ab("con"),
        int_=_ab("int"), wis=_ab("wis"), cha=_ab("cha"),
    )

    # --- Core pre-calculated stats ---
    attrs = system.get("attributes", {})
    hp_max: int = attrs.get("hp", {}).get("max", 0)
    ac_total: int = attrs.get("ac", {}).get("value", 10)

    saves_raw = system.get("saves", {})
    save_totals = {
        SaveType.FORTITUDE: saves_raw.get("fortitude", {}).get("value", 0),
        SaveType.REFLEX: saves_raw.get("reflex", {}).get("value", 0),
        SaveType.WILL: saves_raw.get("will", {}).get("value", 0),
    }
    perception_total: int = system.get("perception", {}).get("mod", 0)

    # --- Skills ---
    skill_totals: dict[Skill, int] = {}
    for skill_key, skill_data in system.get("skills", {}).items():
        skill = SKILL_NAME_MAP.get(skill_key.lower())
        if skill and isinstance(skill_data, dict):
            base = skill_data.get("base", 0)
            if base:
                skill_totals[skill] = base

    # --- Equipment: weapon items (same format as PCs) ---
    equipped_weapons = list(_extract_weapons(items))
    armor = _extract_armor(items)
    shield = _extract_shield(items)

    # --- Attack totals from melee stat block items ---
    attack_totals: dict[str, int] = {}
    synthetic_weapons: list[EquippedWeapon] = []
    for item in items:
        if item.get("type") != "melee":
            continue
        item_name: str = item["name"]
        bonus: int = (item.get("system", {})
                      .get("bonus", {}).get("value", 0))
        attack_totals[item_name] = bonus

        # If no weapon item matched, create a synthetic EquippedWeapon
        has_weapon_item = any(
            eq.weapon.name.lower() == item_name.lower()
            for eq in equipped_weapons
        )
        if not has_weapon_item:
            synthetic = _synthetic_equipped_weapon(item)
            if synthetic is not None:
                attack_totals[synthetic.weapon.name] = bonus
                synthetic_weapons.append(synthetic)

    all_weapons = tuple(equipped_weapons + synthetic_weapons)

    # --- Spellcasting entry ---
    spell_dc = 0
    spell_attack_total = 0
    for item in items:
        if item.get("type") == "spellcastingEntry":
            spelldc = item.get("system", {}).get("spelldc", {})
            if isinstance(spelldc, dict):
                spell_dc = spelldc.get("dc", 0)
                spell_attack_total = spelldc.get("value", 0)
            break

    # --- Known spells (registry-checked) ---
    from pf2e.spells import SPELL_REGISTRY
    known_spells: dict[str, int] = {}
    for item in items:
        if item.get("type") != "spell":
            continue
        slug: str = item.get("system", {}).get("slug", "")
        if not slug:
            slug = (item.get("name", "").lower()
                    .replace(" ", "-").replace("'", ""))
        if slug in SPELL_REGISTRY:
            rank = item.get("system", {}).get("level", {}).get("value", 1)
            known_spells[slug] = rank

    # --- Vision type ---
    vision_type = VisionType.NORMAL
    for sense in system.get("perception", {}).get("senses", []):
        sense_type = sense.get("type", "")
        mapped = _VISION_SENSE_MAP.get(sense_type)
        if mapped is not None:
            vision_type = mapped
            break

    # --- Immunity tags ---
    immunity_tags: frozenset[str] = frozenset(
        i.get("type", "")
        for i in attrs.get("immunities", [])
        if i.get("type")
    )

    # Determine key ability from highest modifier
    mods = {
        "str": raw_ab.get("str", {}).get("mod", 0),
        "dex": raw_ab.get("dex", {}).get("mod", 0),
        "con": raw_ab.get("con", {}).get("mod", 0),
        "int": raw_ab.get("int", {}).get("mod", 0),
        "wis": raw_ab.get("wis", {}).get("mod", 0),
        "cha": raw_ab.get("cha", {}).get("mod", 0),
    }
    from pf2e.types import Ability
    _ABILITY_KEY_MAP = {
        "str": Ability.STR, "dex": Ability.DEX, "con": Ability.CON,
        "int": Ability.INT, "wis": Ability.WIS, "cha": Ability.CHA,
    }
    best_key = max(mods, key=lambda k: mods[k])
    key_ability = _ABILITY_KEY_MAP[best_key]

    return NPCData(
        name=name,
        level=level,
        speed=speed,
        abilities=abilities,
        equipped_weapons=all_weapons,
        armor=armor,
        shield=shield,
        _attack_totals=attack_totals,
        _ac_total=ac_total,
        _save_totals=save_totals,
        _perception_total=perception_total,
        _skill_totals=skill_totals,
        _spell_dc=spell_dc,
        _spell_attack_total=spell_attack_total,
        _max_hp=hp_max,
        known_spells=known_spells,
        vision_type=vision_type,
        immunity_tags=immunity_tags,
        key_ability=key_ability,
    )
