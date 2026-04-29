"""Import Foundry VTT pf2e actor JSON into Character dataclass.

Derives all combat stats from raw character creation inputs.
Does not trust Foundry's computed fields — re-derives everything.

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2100)
"""

from __future__ import annotations

import json
from pathlib import Path

from pf2e.abilities import AbilityScores
from pf2e.character import Character
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
# Lookup tables
# ---------------------------------------------------------------------------

RANK_MAP: dict[int, ProficiencyRank] = {
    0: ProficiencyRank.UNTRAINED,
    1: ProficiencyRank.TRAINED,
    2: ProficiencyRank.EXPERT,
    3: ProficiencyRank.MASTER,
    4: ProficiencyRank.LEGENDARY,
}

SKILL_NAME_MAP: dict[str, Skill] = {
    "acrobatics": Skill.ACROBATICS,
    "arcana": Skill.ARCANA,
    "athletics": Skill.ATHLETICS,
    "crafting": Skill.CRAFTING,
    "deception": Skill.DECEPTION,
    "diplomacy": Skill.DIPLOMACY,
    "intimidation": Skill.INTIMIDATION,
    "medicine": Skill.MEDICINE,
    "nature": Skill.NATURE,
    "occultism": Skill.OCCULTISM,
    "performance": Skill.PERFORMANCE,
    "religion": Skill.RELIGION,
    "society": Skill.SOCIETY,
    "stealth": Skill.STEALTH,
    "survival": Skill.SURVIVAL,
    "thievery": Skill.THIEVERY,
}

WEAPON_GROUP_MAP: dict[str, WeaponGroup] = {
    "axe": WeaponGroup.AXE,
    "bomb": WeaponGroup.BOMB,
    "bow": WeaponGroup.BOW,
    "brawling": WeaponGroup.BRAWLING,
    "club": WeaponGroup.CLUB,
    "dart": WeaponGroup.DART,
    "firearm": WeaponGroup.FIREARM,
    "flail": WeaponGroup.FLAIL,
    "hammer": WeaponGroup.HAMMER,
    "knife": WeaponGroup.KNIFE,
    "pick": WeaponGroup.PICK,
    "polearm": WeaponGroup.POLEARM,
    "shield": WeaponGroup.SHIELD,
    "sling": WeaponGroup.SLING,
    "spear": WeaponGroup.SPEAR,
    "sword": WeaponGroup.SWORD,
}

WEAPON_CATEGORY_MAP: dict[str, WeaponCategory] = {
    "simple": WeaponCategory.SIMPLE,
    "martial": WeaponCategory.MARTIAL,
    "advanced": WeaponCategory.ADVANCED,
    "unarmed": WeaponCategory.UNARMED,
}

DAMAGE_TYPE_MAP: dict[str, DamageType] = {
    "bludgeoning": DamageType.BLUDGEONING,
    "piercing": DamageType.PIERCING,
    "slashing": DamageType.SLASHING,
    "fire": DamageType.FIRE,
    "cold": DamageType.COLD,
    "electricity": DamageType.ELECTRICITY,
    "acid": DamageType.ACID,
    "force": DamageType.FORCE,
}

# Maps Foundry feat names to Character boolean flag names.
# Only includes feats that map directly to has_* fields on Character.
FEAT_FLAG_MAP: dict[str, str] = {
    "Deceptive Tactics": "has_deceptive_tactics",
    "Lengthy Diversion": "has_lengthy_diversion",
    "Plant Banner": "has_plant_banner",
    "Shield Block": "has_shield_block",
    "Commander's Banner": "has_commander_banner",
    "Taunt": "has_taunt",
    "Light Mortar Innovation": "has_light_mortar",
}

# Foundry uses lowercase ability abbreviations; AbilityScores uses str_/int_
# to avoid Python keyword conflicts.
ABILITY_FIELD_MAP: dict[str, str] = {
    "str": "str_", "dex": "dex", "con": "con",
    "int": "int_", "wis": "wis", "cha": "cha",
}

KEY_ABILITY_MAP: dict[str, Ability] = {
    "str": Ability.STR, "dex": Ability.DEX, "con": Ability.CON,
    "int": Ability.INT, "wis": Ability.WIS, "cha": Ability.CHA,
}

SAVE_NAME_MAP: dict[str, SaveType] = {
    "fortitude": SaveType.FORTITUDE,
    "reflex": SaveType.REFLEX,
    "will": SaveType.WILL,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_item_by_type(items: list[dict], item_type: str) -> dict:
    """Find first item of given type. Raises ValueError if not found."""
    for item in items:
        if item.get("type") == item_type:
            return item
    raise ValueError(f"No item of type '{item_type}' found in actor data")


def _normalize_trait(trait: str) -> str:
    """Convert Foundry kebab-case trait to our underscore convention.

    Examples: 'thrown-20' → 'thrown_20', 'deadly-d8' → 'deadly_d8'
    """
    return trait.replace("-", "_")


def _extract_ability_scores(data: dict, items: list[dict]) -> AbilityScores:
    """Derive ability scores from ancestry + background + class key + free boosts.

    All ability scores start at 10. Each boost adds +2 (all L1 scores <= 18).
    Flaws subtract 2.

    Foundry stores boosts in a nested structure:
    - Ancestry/background items have numbered boost slots, each with a "value"
      list of options and an optional "selected" field for player choices.
    - Fixed boosts have exactly 1 option in "value" (auto-applied).
    - Choice boosts have multiple options; the player's pick is in "selected".
    - If ancestry has "alternateAncestryBoosts", the player used the optional
      rule: 2 free boosts (listed) replace the standard fixed+free+flaw.
    - build.attributes.boosts["1"] contains the 4 free boosts at level 1.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2100)
    """
    base: dict[str, int] = {ab: 10 for ab in ["str", "dex", "con", "int", "wis", "cha"]}

    # Ancestry boosts and flaws
    for item in items:
        if item.get("type") == "ancestry":
            alt = item["system"].get("alternateAncestryBoosts")
            if alt:
                # Alternate ancestry boosts: 2 free boosts, no flaw
                for ab in alt:
                    base[ab] += 2
            else:
                # Standard: numbered boost slots + flaws
                for _k, slot in item["system"].get("boosts", {}).items():
                    vals = slot.get("value", [])
                    sel = slot.get("selected")
                    if len(vals) == 1:
                        base[vals[0]] += 2
                    elif sel:
                        base[sel] += 2
                for _k, slot in item["system"].get("flaws", {}).items():
                    for ab in slot.get("value", []):
                        base[ab] -= 2

    # Background boosts (numbered slots with "selected" fields)
    for item in items:
        if item.get("type") == "background":
            for _k, slot in item["system"].get("boosts", {}).items():
                sel = slot.get("selected")
                if sel:
                    base[sel] += 2

    # Class key ability boost
    for item in items:
        if item.get("type") == "class":
            key_list = item["system"].get("keyAbility", {}).get("value", [])
            if key_list:
                base[key_list[0]] += 2

    # Free boosts chosen at character creation (build.attributes.boosts["1"])
    free = (data.get("system", {})
               .get("build", {})
               .get("attributes", {})
               .get("boosts", {})
               .get("1", []))
    for ab in free:
        base[ab] += 2

    mapped = {ABILITY_FIELD_MAP[k]: v for k, v in base.items()}
    return AbilityScores(**mapped)


def _extract_class_proficiencies(
    class_item: dict,
) -> tuple[dict[WeaponCategory, ProficiencyRank], ProficiencyRank]:
    """Extract weapon proficiencies and armor proficiency from class item.

    Foundry stores these in system.attacks and system.defenses.
    """
    attacks = class_item["system"].get("attacks", {})
    weapon_profs = {
        WeaponCategory.SIMPLE: RANK_MAP[attacks.get("simple", 0)],
        WeaponCategory.MARTIAL: RANK_MAP[attacks.get("martial", 0)],
        WeaponCategory.ADVANCED: RANK_MAP[attacks.get("advanced", 0)],
        WeaponCategory.UNARMED: RANK_MAP[attacks.get("unarmed", 0)],
    }

    defenses = class_item["system"].get("defenses", {})
    armor_rank = max(
        defenses.get("heavy", 0),
        defenses.get("medium", 0),
        defenses.get("light", 0),
        defenses.get("unarmored", 0),
    )
    armor_prof = RANK_MAP[armor_rank]

    return weapon_profs, armor_prof


def _extract_save_ranks(class_item: dict) -> dict[SaveType, ProficiencyRank]:
    """Extract saving throw ranks from class item system.savingThrows.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2131)
    """
    saving_throws = class_item["system"].get("savingThrows", {})
    return {
        SaveType.FORTITUDE: RANK_MAP[saving_throws.get("fortitude", 0)],
        SaveType.REFLEX: RANK_MAP[saving_throws.get("reflex", 0)],
        SaveType.WILL: RANK_MAP[saving_throws.get("will", 0)],
    }


def _extract_weapons(items: list[dict]) -> tuple[EquippedWeapon, ...]:
    """Extract all weapons, actively held weapons first.

    Active = item.system.equipped.handsHeld > 0.
    Trait names normalized from Foundry kebab-case to our underscore convention.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2176)
    """
    active: list[EquippedWeapon] = []
    stowed: list[EquippedWeapon] = []

    for item in items:
        if item.get("type") != "weapon":
            continue

        wsys = item["system"]
        dmg = wsys.get("damage", {})
        traits_raw = wsys.get("traits", {}).get("value", [])
        traits = frozenset(_normalize_trait(t) for t in traits_raw)

        group_str = wsys.get("group", "")
        group = WEAPON_GROUP_MAP.get(group_str, WeaponGroup.BRAWLING)

        dmg_type_str = dmg.get("damageType", "slashing")
        dmg_type = DAMAGE_TYPE_MAP.get(dmg_type_str, DamageType.SLASHING)

        usage = wsys.get("usage", {}).get("value", "held-in-one-hand")
        hands = 2 if "two-hands" in usage else 1

        category_str = wsys.get("category", "martial")
        category = WEAPON_CATEGORY_MAP.get(category_str, WeaponCategory.MARTIAL)

        # Range increment: from thrown_N traits or from system.range for guns
        range_increment: int | None = None
        for t in traits:
            if t.startswith("thrown_"):
                try:
                    range_increment = int(t.split("_")[1])
                except (IndexError, ValueError):
                    pass
        # Guns and other ranged weapons store range in system.range
        if range_increment is None:
            sys_range = wsys.get("range")
            if sys_range and isinstance(sys_range, (int, float)) and sys_range > 0:
                range_increment = int(sys_range)

        # Phase B+: combination weapons use melee mode only (e.g., Rapier Pistol)
        # Phase B+: two-hand-d10 trait ignored — model base die only
        # Phase B+: concussive, fatal traits not modeled
        weapon = Weapon(
            name=item["name"],
            category=category,
            group=group,
            damage_die=dmg.get("die", "d4"),
            damage_die_count=dmg.get("dice", 1),
            damage_type=dmg_type,
            range_increment=range_increment,
            traits=traits,
            hands=hands,
        )

        equipped_weapon = EquippedWeapon(weapon=weapon)

        hands_held = wsys.get("equipped", {}).get("handsHeld", 0)
        if hands_held > 0:
            active.append(equipped_weapon)
        else:
            stowed.append(equipped_weapon)

    return tuple(active + stowed)


def _extract_armor(items: list[dict]) -> ArmorData | None:
    """Extract equipped armor.

    Foundry stores the required Str modifier in system.strength.
    Our ArmorData.strength_threshold expects the Str score.
    Conversion: score = 10 + 2 * modifier.

    Note: ArmorData has no 'category' field — only ac_bonus, dex_cap, etc.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2168)
    """
    for item in items:
        if item.get("type") != "armor":
            continue

        asys = item["system"]
        # Skip shields that Foundry may categorize as armor
        if asys.get("category", "") == "shield":
            continue

        foundry_strength = asys.get("strength") or 0
        strength_threshold = 10 + 2 * foundry_strength if foundry_strength else 0

        return ArmorData(
            name=item["name"],
            ac_bonus=asys.get("acBonus", 0),
            dex_cap=asys.get("dexCap"),
            check_penalty=asys.get("checkPenalty", 0),
            speed_penalty=asys.get("speedPenalty", 0),
            strength_threshold=strength_threshold,
        )
    return None


def _extract_shield(items: list[dict]) -> Shield | None:
    """Extract shield with hardness, hp, bt.

    Infers broken threshold as hp // 2 when brokenThreshold is null.
    (AoN: https://2e.aonprd.com/Shields.aspx?ID=3)
    """
    for item in items:
        if item.get("type") == "shield":
            ssys = item["system"]
            hp_max = ssys.get("hp", {}).get("max", 20)
            bt = ssys.get("brokenThreshold") or (hp_max // 2)
            return Shield(
                name=item["name"],
                ac_bonus=ssys.get("acBonus", 2),
                hardness=ssys.get("hardness", 5),
                hp=hp_max,
                bt=bt,
            )
    return None


def _extract_skills(system: dict) -> dict[Skill, ProficiencyRank]:
    """Extract skill proficiencies from system.skills.

    Includes all 16 standard skills regardless of rank.
    (AoN: https://2e.aonprd.com/Skills.aspx)
    """
    result: dict[Skill, ProficiencyRank] = {}
    skills_data = system.get("skills", {})
    for skill_name, skill_data in skills_data.items():
        skill = SKILL_NAME_MAP.get(skill_name)
        if skill is None:
            continue
        rank = RANK_MAP[skill_data.get("rank", 0)]
        result[skill] = rank
    return result


def _extract_lores(items: list[dict]) -> dict[str, ProficiencyRank]:
    """Extract lore proficiencies from lore-type items.

    Strips ' Lore' suffix: 'Warfare Lore' -> 'Warfare'.
    (AoN: https://2e.aonprd.com/Skills.aspx?ID=47)
    """
    lores: dict[str, ProficiencyRank] = {}
    for item in items:
        if item.get("type") == "lore":
            name = item["name"].removesuffix(" Lore")
            rank_val = item["system"].get("proficient", {}).get("value", 0)
            lores[name] = RANK_MAP[rank_val]
    return lores


def _extract_feat_names(items: list[dict]) -> set[str]:
    """Collect all feat item names."""
    return {item["name"] for item in items if item.get("type") == "feat"}


def _extract_spell_names(items: list[dict]) -> set[str]:
    """Collect all spell item names."""
    return {item["name"] for item in items if item.get("type") == "spell"}


def _extract_known_spells(items: list[dict]) -> dict[str, int]:
    """Extract known combat spells mapped to rank (0 = cantrip).

    Only includes spells that have a definition in SPELL_REGISTRY.
    Other spells (Figment, Telekinetic Hand, etc.) are ignored.
    """
    from pf2e.spells import SPELL_REGISTRY

    known: dict[str, int] = {}
    for item in items:
        if item.get("type") != "spell":
            continue
        slug = item.get("system", {}).get("slug")
        if not slug:
            continue
        if slug in SPELL_REGISTRY:
            rank = item.get("system", {}).get("level", {}).get("value", 1)
            # Cantrips are rank 0 in our system
            defn = SPELL_REGISTRY[slug]
            known[slug] = defn.rank
    return known


def _resolve_initially_held(items: list[dict]) -> tuple[str, ...]:
    """Resolve which items are initially held, respecting 2-hand limit.

    Foundry can store inconsistent handsHeld totals (>2). Resolve by:
    1. Filter to items with handsHeld > 0 (weapons and shields)
    2. For weapons, use min(handsHeld, usage_hands) — a one-handed weapon
       held two-handed in Foundry uses 1 hand when conflict exists
    3. Sort by effective hands ascending (one-handed items first)
    4. Greedily allocate up to 2 total hand-slots
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2149)
    """
    candidates: list[tuple[str, int]] = []
    for item in items:
        itype = item.get("type", "")
        if itype not in ("weapon", "shield"):
            continue
        hands_held = item.get("system", {}).get("equipped", {}).get("handsHeld", 0)
        if hands_held <= 0:
            continue
        # For weapons: use the weapon's usage-based hands (1 or 2) as minimum.
        # A one-handed weapon (usage=held-in-one-hand) can be held one-handed
        # even if Foundry shows handsHeld=2 (player was two-handing it).
        if itype == "weapon":
            usage = item.get("system", {}).get("usage", {}).get("value", "held-in-one-hand")
            usage_hands = 2 if "two-hands" in usage else 1
            effective_hands = min(hands_held, usage_hands)
        else:
            effective_hands = hands_held
        candidates.append((item["name"], effective_hands))

    candidates.sort(key=lambda x: x[1])  # one-handed first
    held: list[str] = []
    hands_remaining = 2
    for name, hands_needed in candidates:
        if hands_needed <= hands_remaining:
            held.append(name)
            hands_remaining -= hands_needed
    return tuple(held)


def _extract_starting_resources(items: list[dict]) -> dict[str, int]:
    """Extract starting expendable resources from spellcasting entries.

    Reads system.slots on spellcastingEntry items (spontaneous casters).
    E.g. slot1.max=2 → {"spell_slot_1": 2}.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2224)
    """
    resources: dict[str, int] = {}
    for item in items:
        if item.get("type") != "spellcastingEntry":
            continue
        prepared = item.get("system", {}).get("prepared", {})
        # Only spontaneous casters have slot-based tracking
        if isinstance(prepared, dict):
            prep_value = prepared.get("value", "")
        else:
            prep_value = str(prepared)
        if prep_value != "spontaneous":
            continue
        slots = item.get("system", {}).get("slots", {})
        for key, slot_data in slots.items():
            if not isinstance(slot_data, dict):
                continue
            max_slots = slot_data.get("max", 0)
            if max_slots > 0:
                # key is "slot1", "slot2", etc. → "spell_slot_1", "spell_slot_2"
                rank_str = key.replace("slot", "")
                if rank_str.isdigit():
                    resources[f"spell_slot_{rank_str}"] = max_slots
    return resources


def _derive_speed(ancestry_item: dict, feat_names: set[str]) -> int:
    """Derive speed from ancestry base speed + Nimble Elf (+5 if present).

    Phase B: only Nimble Elf speed modification modeled. Other modifiers deferred.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)
    (AoN: https://2e.aonprd.com/Feats.aspx?ID=16 — Nimble Elf)
    """
    base_speed = ancestry_item["system"].get("speed", 25)
    if "Nimble Elf" in feat_names:
        base_speed += 5
    return base_speed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_foundry_actor(path: str) -> Character:
    """Import a Foundry VTT pf2e actor JSON and return a Character.

    Derives all combat stats from raw character creation inputs using the
    same formulas as pf2e/combat_math.py. Does not trust Foundry's computed
    fields (ac, saves, speed) — re-derives everything from source data.

    Raises FileNotFoundError if the JSON file does not exist.
    Raises ValueError if required item types are missing from the JSON.
    """
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(
            f"Foundry actor JSON not found: {path}\n"
            f"Export the character from Foundry VTT and place the file at this path."
        )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    items: list[dict] = data["items"]

    # Find required item types
    class_item = _find_item_by_type(items, "class")
    from pf2e.detection import VisionType
    _ANCESTRY_VISION = {
        "elf": VisionType.LOW_LIGHT,
        "ancient elf": VisionType.LOW_LIGHT,
        "automaton": VisionType.DARKVISION,
        "dwarf": VisionType.DARKVISION,
        "gnome": VisionType.LOW_LIGHT,
        "halfling": VisionType.LOW_LIGHT,
    }
    ancestry_item = _find_item_by_type(items, "ancestry")

    # Core derivations
    abilities = _extract_ability_scores(data, items)
    level: int = data["system"]["details"]["level"]["value"]

    key_ability_str = class_item["system"]["keyAbility"]["value"][0]
    key_ability = KEY_ABILITY_MAP[key_ability_str]

    weapon_profs, armor_prof = _extract_class_proficiencies(class_item)
    perception_rank = RANK_MAP[class_item["system"].get("perception", 1)]
    save_ranks = _extract_save_ranks(class_item)

    # Equipment
    equipped_weapons = _extract_weapons(items)
    armor = _extract_armor(items)
    shield = _extract_shield(items)

    # Skills and knowledge
    skills = _extract_skills(data["system"])
    lores = _extract_lores(items)

    # Feat and spell detection
    feat_names = _extract_feat_names(items)
    spell_names = _extract_spell_names(items)

    # HP components
    ancestry_hp: int = ancestry_item["system"]["hp"]
    class_hp: int = class_item["system"]["hp"]

    # Speed
    speed = _derive_speed(ancestry_item, feat_names)

    # Vision type from ancestry
    ancestry_name_lower = ancestry_item.get("name", "").lower()
    vision_type = _ANCESTRY_VISION.get(ancestry_name_lower, VisionType.NORMAL)

    # Boolean feat flags from FEAT_FLAG_MAP
    feat_flags: dict[str, bool] = {
        flag: (feat_name in feat_names)
        for feat_name, flag in FEAT_FLAG_MAP.items()
    }

    # Special cases outside FEAT_FLAG_MAP:
    # Guardian's Techniques is an umbrella feat containing Intercept Attack.
    # Character has no has_intercept_attack flag; guardian_reactions > 0 serves that role.
    guardian_reactions = 1 if "Guardian's Techniques" in feat_names else 0
    # Spells detected by name in the items array
    has_courageous_anthem = "Courageous Anthem" in spell_names
    has_soothe = "Soothe" in spell_names

    # Known combat spells (CP5.4 spell chassis)
    known_spells = _extract_known_spells(items)

    # Hand state and expendable resources (CP7.2)
    initially_held = _resolve_initially_held(items)
    starting_resources = _extract_starting_resources(items)

    return Character(
        name=data["name"],
        level=level,
        abilities=abilities,
        key_ability=key_ability,
        weapon_proficiencies=weapon_profs,
        armor_proficiency=armor_prof,
        perception_rank=perception_rank,
        save_ranks=save_ranks,
        # Phase B+: class_dc_rank from catalog; hard-coded TRAINED for L1
        class_dc_rank=ProficiencyRank.TRAINED,
        equipped_weapons=equipped_weapons,
        armor=armor,
        shield=shield,
        speed=speed,
        ancestry_hp=ancestry_hp,
        class_hp=class_hp,
        skill_proficiencies=skills,
        lores=lores,
        guardian_reactions=guardian_reactions,
        has_courageous_anthem=has_courageous_anthem,
        has_soothe=has_soothe,
        known_spells=known_spells,
        initially_held=initially_held,
        starting_resources=starting_resources,
        vision_type=vision_type,
        **feat_flags,
    )
