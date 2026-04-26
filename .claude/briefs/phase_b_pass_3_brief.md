# Phase B — Pass 3 Brief: Implementation

## Before You Start

Read these files in full before writing a single line of code:

```
pf2e/character.py
pf2e/abilities.py
pf2e/equipment.py
pf2e/types.py
pf2e/combat_math.py
sim/party.py
characters/aetregan.json       (Pathbuilder format — cross-reference only)
```

Do not assume any interface from the briefs. The code is the truth. If anything
contradicts this brief, flag it before proceeding.

---

## Critical Constraints

- **EV 8.55 regression must pass before swapping factories.** Build the importer
  standalone, validate Aetregan matches the existing factory on EV-critical fields,
  then — and only then — update `sim/party.py`.
- **Foundry sheet is authoritative (D10).** Where the JSON contradicts CHARACTERS.md
  or existing factories, the JSON wins.
- **Phase B scope only.** Combination weapons, two-hand upgrades, concussive, and
  fatal traits are all flagged in comments and deferred to Phase B+. Do not implement
  them now.

---

## Implementation Order

Follow this order strictly.

---

### Step 1: Add AXE to WeaponGroup enum

In `pf2e/types.py`, add to the `WeaponGroup` enum:

```python
AXE = auto()
```

Position it alphabetically among existing entries. This is the only change to
`pf2e/types.py` in this checkpoint.

---

### Step 2: Copy Foundry JSONs to characters/

Copy all four uploaded files to `characters/` with clean names:

```bash
cp /mnt/user-data/uploads/fvtt-Actor-jotan-aethregen-hiDy2hZf2KqSewPy.json characters/fvtt-aetregan.json
cp /mnt/user-data/uploads/fvtt-Actor-rook-CaZCAKANLer542FO.json characters/fvtt-rook.json
cp /mnt/user-data/uploads/fvtt-Actor-dalai-alpaca-M1n02jHO7Lt6ZtsJ.json characters/fvtt-dalai.json
cp /mnt/user-data/uploads/fvtt-Actor-erizin-nTcnSbOALfHke9sY.json characters/fvtt-erisen.json
```

---

### Step 3: Create sim/importers/__init__.py

Empty file:

```python
# sim/importers/__init__.py
```

---

### Step 4: Implement sim/importers/foundry.py

Create the full module. Implement all helpers in the order listed below.

#### 4-A: Lookup tables (at module level)

```python
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
    "sword": WeaponGroup.SWORD,
    "knife": WeaponGroup.KNIFE,
    "brawling": WeaponGroup.BRAWLING,
    "flail": WeaponGroup.FLAIL,
    "firearm": WeaponGroup.FIREARM,
    "bomb": WeaponGroup.BOMB,
    "polearm": WeaponGroup.POLEARM,
    "pick": WeaponGroup.PICK,
    "hammer": WeaponGroup.HAMMER,
    "club": WeaponGroup.CLUB,
    "spear": WeaponGroup.SPEAR,
    "dart": WeaponGroup.DART,
    "bow": WeaponGroup.BOW,
    "sling": WeaponGroup.SLING,
    "shield": WeaponGroup.SHIELD,
    "axe": WeaponGroup.AXE,
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
}

FEAT_FLAG_MAP: dict[str, str] = {
    "Deceptive Tactics":       "has_deceptive_tactics",
    "Lengthy Diversion":       "has_lengthy_diversion",
    "Plant Banner":            "has_plant_banner",
    "Shield Block":            "has_shield_block",
    "Commander's Banner":      "has_commander_banner",
    "Taunt":                   "has_taunt",
    "Light Mortar Innovation": "has_light_mortar",
}

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
```

#### 4-B: _find_item_by_type()

```python
def _find_item_by_type(items: list[dict], item_type: str) -> dict:
    """Find first item of given type. Raises ValueError if not found."""
    for item in items:
        if item.get("type") == item_type:
            return item
    raise ValueError(f"No item of type '{item_type}' found in actor data")
```

#### 4-C: _normalize_trait()

```python
def _normalize_trait(trait: str) -> str:
    """Convert Foundry kebab-case trait to our underscore convention.

    Examples: 'thrown-20' → 'thrown_20', 'deadly-d8' → 'deadly_d8'
    """
    return trait.replace("-", "_")
```

#### 4-D: _extract_ability_scores()

```python
def _extract_ability_scores(data: dict, items: list[dict]) -> AbilityScores:
    """Derive ability scores from ancestry + background + class key + free boosts.

    All ability scores start at 10. Each boost adds +2 (all L1 scores ≤ 18).
    Flaws subtract 2. Applied in order: ancestry → background → class key → free.
    """
    base = {ab: 10 for ab in ["str", "dex", "con", "int", "wis", "cha"]}

    # Ancestry boosts and flaws
    for item in items:
        if item.get("type") == "ancestry":
            for ab in item["system"].get("boosts", {}).get("value", []):
                base[ab] += 2
            for ab in item["system"].get("flaws", {}).get("value", []):
                base[ab] -= 2

    # Background boosts
    for item in items:
        if item.get("type") == "background":
            for ab in item["system"].get("boosts", {}).get("value", []):
                base[ab] += 2

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
```

#### 4-E: _extract_class_proficiencies()

```python
def _extract_class_proficiencies(
    class_item: dict,
) -> tuple[dict[WeaponCategory, ProficiencyRank], ProficiencyRank]:
    """Extract weapon proficiencies and armor proficiency from class item.

    Foundry stores these in system.attacks and system.defenses.
    """
    attacks = class_item["system"].get("attacks", {})
    weapon_profs = {
        WeaponCategory.SIMPLE:   RANK_MAP[attacks.get("simple", 0)],
        WeaponCategory.MARTIAL:  RANK_MAP[attacks.get("martial", 0)],
        WeaponCategory.ADVANCED: RANK_MAP[attacks.get("advanced", 0)],
        WeaponCategory.UNARMED:  RANK_MAP[attacks.get("unarmed", 0)],
    }

    defenses = class_item["system"].get("defenses", {})
    # Take the highest armor proficiency available
    armor_rank = max(
        defenses.get("heavy", 0),
        defenses.get("medium", 0),
        defenses.get("light", 0),
        defenses.get("unarmored", 0),
    )
    armor_prof = RANK_MAP[armor_rank]

    return weapon_profs, armor_prof
```

#### 4-F: _extract_save_ranks()

```python
def _extract_save_ranks(class_item: dict) -> dict[SaveType, ProficiencyRank]:
    """Extract saving throw ranks from class item system.savingThrows."""
    saving_throws = class_item["system"].get("savingThrows", {})
    return {
        SaveType.FORTITUDE: RANK_MAP[saving_throws.get("fortitude", 0)],
        SaveType.REFLEX:    RANK_MAP[saving_throws.get("reflex", 0)],
        SaveType.WILL:      RANK_MAP[saving_throws.get("will", 0)],
    }
```

#### 4-G: _extract_weapons()

```python
def _extract_weapons(items: list[dict]) -> tuple[EquippedWeapon, ...]:
    """Extract all weapons, actively held weapons first.

    Active = item.system.equipped.handsHeld > 0.
    Trait names normalized from Foundry kebab-case to our underscore convention.
    Phase B+ notes: combination weapons use melee mode; two-hand upgrades ignored.
    """
    active = []
    stowed = []

    for item in items:
        if item.get("type") != "weapon":
            continue

        wsys = item["system"]
        dmg = wsys.get("damage", {})
        traits_raw = wsys.get("traits", {}).get("value", [])
        traits = frozenset(_normalize_trait(t) for t in traits_raw)

        group_str = wsys.get("group", "")
        group = WEAPON_GROUP_MAP.get(group_str)
        if group is None:
            # Unknown group — use BRAWLING as a safe fallback, log warning
            print(f"[WARNING] Unknown weapon group '{group_str}' for {item['name']} — defaulting to BRAWLING")
            group = WeaponGroup.BRAWLING

        dmg_type_str = dmg.get("damageType", "slashing")
        dmg_type = DAMAGE_TYPE_MAP.get(dmg_type_str, DamageType.SLASHING)

        usage = wsys.get("usage", {}).get("value", "held-in-one-hand")
        hands = 2 if "two-hands" in usage else 1

        category_str = wsys.get("category", "martial")
        category = WEAPON_CATEGORY_MAP.get(category_str, WeaponCategory.MARTIAL)

        # Range increment from traits (thrown_10 → 10, thrown_20 → 20)
        range_increment = None
        for t in traits:
            if t.startswith("thrown_"):
                try:
                    range_increment = int(t.split("_")[1])
                except (IndexError, ValueError):
                    pass

        weapon = Weapon(
            name=item["name"],
            damage_dice=dmg.get("dice", 1),
            damage_die=dmg.get("die", "d4"),
            damage_type=dmg_type,
            group=group,
            category=category,
            hands=hands,
            traits=traits,
            range_increment=range_increment,
            is_agile="agile" in traits,
            is_finesse="finesse" in traits,
            is_reach="reach" in traits,
            is_ranged=range_increment is not None,
        )

        # No runes at L1
        runes = WeaponRunes(potency=0, striking=0)
        equipped_weapon = EquippedWeapon(weapon=weapon, runes=runes)

        hands_held = wsys.get("equipped", {}).get("handsHeld", 0)
        if hands_held > 0:
            active.append(equipped_weapon)
        else:
            stowed.append(equipped_weapon)

    return tuple(active + stowed)
```

#### 4-H: _extract_armor()

```python
def _extract_armor(items: list[dict]) -> ArmorData | None:
    """Extract equipped armor.

    strength_threshold: Foundry stores the required Str modifier.
    Our ArmorData expects the Str score. Conversion: 10 + 2 * modifier.
    """
    for item in items:
        if item.get("type") != "armor":
            continue

        asys = item["system"]
        category = asys.get("category", "light")
        if category == "shield":
            continue  # shields handled separately

        foundry_strength = asys.get("strength") or 0
        strength_threshold = 10 + 2 * foundry_strength if foundry_strength else 0

        return ArmorData(
            name=item["name"],
            category=category,
            ac_bonus=asys.get("acBonus", 0),
            dex_cap=asys.get("dexCap"),           # None = no cap
            check_penalty=asys.get("checkPenalty", 0),
            speed_penalty=asys.get("speedPenalty", 0),
            strength_threshold=strength_threshold,
        )
    return None
```

**Note:** Confirm the exact field names on `ArmorData` by reading
`pf2e/equipment.py` before finalizing this function. If `ArmorData` uses
different names (e.g., `max_dex` instead of `dex_cap`), adapt accordingly.

#### 4-I: _extract_shield()

```python
def _extract_shield(items: list[dict]) -> Shield | None:
    """Extract shield. Infers broken threshold as hp // 2 when None."""
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
```

#### 4-J: _extract_skills()

```python
def _extract_skills(system: dict) -> dict[Skill, ProficiencyRank]:
    """Extract skill proficiencies. Only includes UNTRAINED and above.

    All 16 skills are included regardless of rank — callers can filter.
    """
    result = {}
    skills_data = system.get("skills", {})
    for skill_name, skill_data in skills_data.items():
        skill = SKILL_NAME_MAP.get(skill_name)
        if skill is None:
            continue
        rank = RANK_MAP[skill_data.get("rank", 0)]
        result[skill] = rank
    return result
```

#### 4-K: _extract_lores()

```python
def _extract_lores(items: list[dict]) -> dict[str, ProficiencyRank]:
    """Extract lore proficiencies from lore-type items.

    Strips ' Lore' suffix: 'Warfare Lore' → 'Warfare'.
    """
    lores = {}
    for item in items:
        if item.get("type") == "lore":
            name = item["name"].removesuffix(" Lore")
            rank_val = item["system"].get("proficient", {}).get("value", 0)
            lores[name] = RANK_MAP[rank_val]
    return lores
```

#### 4-L: _extract_feat_names() and _extract_spell_names()

```python
def _extract_feat_names(items: list[dict]) -> set[str]:
    """Collect all feat item names."""
    return {item["name"] for item in items if item.get("type") == "feat"}

def _extract_spell_names(items: list[dict]) -> set[str]:
    """Collect all spell item names."""
    return {item["name"] for item in items if item.get("type") == "spell"}
```

#### 4-M: _derive_speed()

```python
def _derive_speed(ancestry_item: dict, feat_names: set[str]) -> int:
    """Derive speed from ancestry base speed + Nimble Elf (+5 if present).

    Phase B: only Nimble Elf modification modeled. Other speed modifiers deferred.
    """
    base_speed = ancestry_item["system"].get("speed", 25)
    if "Nimble Elf" in feat_names:
        base_speed += 5
    return base_speed
```

#### 4-N: import_foundry_actor() — main function

```python
def import_foundry_actor(path: str) -> Character:
    """Import a Foundry VTT pf2e actor JSON and return a Character.

    Derives all combat stats from raw character creation inputs using the
    same formulas as pf2e/combat_math.py. Does not trust Foundry's computed
    fields (ac, saves, speed) — re-derives everything from source data.

    Raises FileNotFoundError if the JSON file does not exist.
    Raises ValueError if required fields are missing from the JSON.
    """
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(
            f"Foundry actor JSON not found: {path}\n"
            f"Export the character from Foundry VTT and place the file at this path."
        )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    items = data["items"]

    # Find required item types
    class_item    = _find_item_by_type(items, "class")
    ancestry_item = _find_item_by_type(items, "ancestry")

    # Core derivations
    abilities = _extract_ability_scores(data, items)
    level = data["system"]["details"]["level"]["value"]

    key_ability_str = class_item["system"]["keyAbility"]["value"][0]
    key_ability = KEY_ABILITY_MAP[key_ability_str]

    weapon_profs, armor_prof = _extract_class_proficiencies(class_item)
    perception_rank = RANK_MAP[class_item["system"].get("perception", 1)]
    save_ranks = _extract_save_ranks(class_item)

    # Equipment
    equipped_weapons = _extract_weapons(items)
    armor  = _extract_armor(items)
    shield = _extract_shield(items)

    # Skills and knowledge
    skills = _extract_skills(data["system"])
    lores  = _extract_lores(items)

    # Feat and spell detection
    feat_names  = _extract_feat_names(items)
    spell_names = _extract_spell_names(items)

    # HP components
    ancestry_hp = ancestry_item["system"]["hp"]
    class_hp    = class_item["system"]["hp"]

    # Speed
    speed = _derive_speed(ancestry_item, feat_names)

    # Boolean feat flags from FEAT_FLAG_MAP
    feat_flags: dict[str, bool] = {
        flag: (feat_name in feat_names)
        for feat_name, flag in FEAT_FLAG_MAP.items()
    }

    # Special cases outside FEAT_FLAG_MAP
    guardian_reactions  = 1 if "Guardian's Techniques" in feat_names else 0
    has_courageous_anthem = "Courageous Anthem" in spell_names
    has_soothe          = "Soothe" in spell_names

    return Character(
        name=data["name"],
        level=level,
        abilities=abilities,
        key_ability=key_ability,
        weapon_proficiencies=weapon_profs,
        armor_proficiency=armor_prof,
        perception_rank=perception_rank,
        save_ranks=save_ranks,
        class_dc_rank=ProficiencyRank.TRAINED,  # L1 universal; Phase B+ uses catalog
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
        **feat_flags,
    )
```

---

### Step 5: Validate Aetregan before swapping factories

Write the validation test first. Do not touch `sim/party.py` until this passes.

```python
def test_imported_aetregan_ev_critical_fields():
    """Imported Aetregan must match factory on fields that affect EV 8.55."""
    from sim.importers.foundry import import_foundry_actor
    from sim.party import make_aetregan

    imported = import_foundry_actor("characters/fvtt-aetregan.json")
    factory  = make_aetregan()

    # Ability scores
    assert imported.abilities.str_  == factory.abilities.str_
    assert imported.abilities.dex   == factory.abilities.dex
    assert imported.abilities.con   == factory.abilities.con
    assert imported.abilities.int_  == factory.abilities.int_
    assert imported.abilities.wis   == factory.abilities.wis
    assert imported.abilities.cha   == factory.abilities.cha

    # Primary weapon
    assert imported.equipped_weapons[0].weapon.damage_die == \
           factory.equipped_weapons[0].weapon.damage_die
    assert imported.equipped_weapons[0].weapon.damage_type == \
           factory.equipped_weapons[0].weapon.damage_type

    # Armor
    assert imported.armor.ac_bonus      == factory.armor.ac_bonus
    assert imported.armor.speed_penalty == factory.armor.speed_penalty

    # Perception rank (affects initiative)
    assert imported.perception_rank == factory.perception_rank

    # HP components
    assert imported.ancestry_hp == factory.ancestry_hp
    assert imported.class_hp    == factory.class_hp
```

---

### Step 6: Update sim/party.py factories

After the validation test passes, update each factory to call the importer:

```python
from sim.importers.foundry import import_foundry_actor

def make_aetregan() -> Character:
    """Aetregan (Commander). Data sourced from Foundry VTT actor export.
    (AoN: https://2e.aonprd.com/Classes.aspx?ID=66)
    """
    return import_foundry_actor("characters/fvtt-aetregan.json")

def make_rook() -> Character:
    """Rook (Guardian). Data sourced from Foundry VTT actor export."""
    return import_foundry_actor("characters/fvtt-rook.json")

def make_dalai() -> Character:
    """Dalai Alpaca (Bard). Data sourced from Foundry VTT actor export."""
    return import_foundry_actor("characters/fvtt-dalai.json")

def make_erisen() -> Character:
    """Erisen (Inventor). Data sourced from Foundry VTT actor export."""
    return import_foundry_actor("characters/fvtt-erisen.json")
```

Keep `make_rook_combat_state()` intact — it still applies full plate speed
penalty at runtime.

---

### Step 7: Update CHARACTERS.md

Correct the two skill discrepancies for Aetregan:
- Deception: **trained** (not untrained — JSON authoritative per D10)
- Nature: **untrained** (not trained — JSON authoritative)

Add a note at the top of the Aetregan section:
```
**Data source:** `characters/fvtt-aetregan.json` (Foundry VTT export, authoritative).
Pathbuilder JSON at `characters/aetregan.json` is superseded.
```

---

### Step 8: Write all tests

New test file: `tests/test_foundry_importer.py`

```python
# Ability scores
def test_import_aetregan_ability_scores():
    # STR 10, DEX 16, CON 12, INT 18, WIS 12, CHA 10

def test_import_aetregan_max_hp():
    # max_hp(imported) == 15

def test_import_aetregan_deception_trained():
    # skill_proficiencies[Skill.DECEPTION] == ProficiencyRank.TRAINED

def test_import_aetregan_nature_untrained():
    # skill_proficiencies[Skill.NATURE] == ProficiencyRank.UNTRAINED

def test_import_aetregan_warfare_lore():
    # lores["Warfare"] == ProficiencyRank.TRAINED

def test_import_aetregan_feat_flags():
    # has_deceptive_tactics=True, has_commander_banner=True, has_shield_block=True

def test_import_aetregan_weapon():
    # Scorpion Whip, d4 slashing, group=FLAIL, traits include "reach"

def test_import_aetregan_speed():
    # speed == 30 (Elf base, no Nimble Elf)

# Rook
def test_import_rook_primary_weapon():
    # First weapon is Earthbreaker, d6 bludgeoning, group=HAMMER

def test_import_rook_all_weapons():
    # len(equipped_weapons) == 4

def test_import_rook_armor():
    # Full Plate, ac_bonus=6, speed_penalty=-10, strength_threshold=18

def test_import_rook_shield():
    # Steel Shield, hardness=5, hp=20, bt=10, ac_bonus=2

def test_import_rook_guardian_reactions():
    # guardian_reactions == 1

def test_import_rook_weapon_proficiency():
    # weapon_proficiencies[WeaponCategory.MARTIAL] == TRAINED

# Dalai
def test_import_dalai_anthem():
    # has_courageous_anthem == True

def test_import_dalai_soothe():
    # has_soothe == True

def test_import_dalai_weapon():
    # First weapon is Rapier Pistol or Dagger depending on handsHeld
    # Verify name and damage type

def test_import_dalai_hp():
    # max_hp(dalai) == 17

# Erisen
def test_import_erisen_mortar():
    # has_light_mortar == True

def test_import_erisen_speed():
    # speed == 35 (Elf 30 + Nimble Elf 5)

def test_import_erisen_weapon():
    # Dueling Pistol or similar, d6 piercing

# Infrastructure
def test_importer_missing_file_raises():
    # import_foundry_actor("characters/does_not_exist.json")
    # raises FileNotFoundError with descriptive message

def test_trait_normalization():
    # _normalize_trait("thrown-20") == "thrown_20"
    # _normalize_trait("deadly-d8") == "deadly_d8"

def test_weapon_group_mapping():
    # WEAPON_GROUP_MAP["flail"] == WeaponGroup.FLAIL
    # WEAPON_GROUP_MAP["hammer"] == WeaponGroup.HAMMER
    # WEAPON_GROUP_MAP["axe"] == WeaponGroup.AXE

# Validation
def test_imported_aetregan_ev_critical_fields():
    # (see Step 5 above)
```

---

### Step 9: Full regression

```bash
pytest tests/ -v
```

All 466+ existing tests must pass. New tests bring total to approximately 490.

---

### Step 10: EV 8.55 regression (13th verification)

```bash
pytest tests/ -k "ev_8_55" -v
```

If Rook's weapon change (Longsword → Earthbreaker) alters the EV — report the
new value. Do not force 8.55. Establish the new target and update the regression
test accordingly.

If Aetregan's skills change (Deception now trained) has no effect on EV —
confirm in the test output.

---

### Step 11: Run full combat with imported party

```bash
python -m sim --scenario scenarios/checkpoint_2_two_bandits.scenario \
  --full-combat --seed 42
```

Paste output for review. The notable change to watch: Rook's Earthbreaker is
bludgeoning, so he naturally counters Bandit2's weakness profile (bludgeoning +3)
without Recall Knowledge being used first.

---

### Step 12: CHANGELOG and current_state.md

**CHANGELOG.md:**

```markdown
## [Phase B] — {date}
### Added
- sim/importers/foundry.py — Foundry VTT pf2e actor JSON importer
- sim/importers/__init__.py
- characters/fvtt-aetregan.json, fvtt-rook.json, fvtt-dalai.json, fvtt-erisen.json
- WeaponGroup.AXE added to pf2e/types.py
- tests/test_foundry_importer.py — 24 new tests

### Changed
- sim/party.py factories now call import_foundry_actor() for all four characters
- Aetregan: Deception now trained (JSON authoritative, was untrained in defaults)
- Aetregan: Nature now untrained (JSON authoritative, was trained in defaults)
- Rook: Primary weapon changed to Earthbreaker (bludgeoning) — replaces Longsword
- Rook: All 4 weapons imported (Earthbreaker, Light Hammer, Barricade Buster, bomb)
- Dalai: Rapier Pistol replaces Rapier as primary weapon
- Erisen: Dueling Pistol replaces Dagger as primary weapon

### Known Phase B+ deferred items (flagged in code comments)
- Combination weapon dual-mode (Dalai's Rapier Pistol ranged mode)
- Two-hand damage die upgrade (Rook's Earthbreaker d6→d10)
- Gun traits: concussive, fatal, kickback (Erisen's Dueling Pistol, Barricade Buster)
- class_dc_rank sourced from catalog (currently hard-coded TRAINED)

### Regressions
- Strike Hard EV: {new value or 8.55} (13th verification)
```

**current_state.md:**

```markdown
## Current State

**Checkpoint:** Phase B complete
**Tests:** ~490 passing
**Last commit:** {commit hash}
**Killer regression:** Strike Hard EV {value} (13th verification)

**Next checkpoint:** Phase B+ — Foundry catalog ingestion, predicate evaluator,
effect handler registry

**Character data:** All four party members now sourced from Foundry VTT exports.
JSON files in characters/. Factories in sim/party.py call importer directly.
```

---

## Common Pitfalls

1. **ArmorData field names:** Read `pf2e/equipment.py` carefully before writing
   `_extract_armor()`. Field names may differ from what's shown here
   (e.g., `max_dex` vs `dex_cap`). The code is the truth.

2. **Aetregan's armor:** The Subterfuge Suit has `rules` entries in the Foundry
   JSON (AdjustModifier rule elements). These are Phase B+ concern — ignore the
   `rules` array entirely in the importer. Just read `acBonus`, `dexCap`, etc.

3. **Shield vs armor:** Foundry has a `shield` item type separate from `armor`.
   In `_extract_armor()`, skip items where `category == "shield"` to avoid
   accidentally treating a shield as armor.

4. **AbilityScores field names:** `str_` and `int_` — use `ABILITY_FIELD_MAP`
   to handle these correctly. Never pass `str=10` or `int=18` directly.

5. **Rook's Earthbreaker EV change:** If the new EV is not 8.55, update the
   regression test with the real value. Report it clearly. Do not hunt for the
   old value.

6. **Dalai's weapon:** The Rapier Pistol may have `handsHeld=0` if she's not
   currently holding it in the Foundry session. Check which weapon is active
   and document it. If no weapon is active, use the first weapon in the items
   array as primary.

7. **Phase B+ comments:** Every simplification must have a code comment:
   ```python
   # Phase B+: two-hand-d10 trait ignored — Rook carries shield, can't two-hand
   # Phase B+: combination weapon — melee mode only for Rapier Pistol
   # Phase B+: class_dc_rank from catalog; hard-coded TRAINED for L1
   ```

---

## Validation Checklist

- [ ] `WeaponGroup.AXE` added to `pf2e/types.py`
- [ ] Four Foundry JSONs copied to `characters/`
- [ ] `sim/importers/__init__.py` created
- [ ] `sim/importers/foundry.py` created with all helpers
- [ ] All lookup tables correct (check WeaponGroup enum values before writing)
- [ ] `_extract_ability_scores()` applies boosts in correct order
- [ ] `_extract_class_proficiencies()` reads from class item, not lookup table
- [ ] `_extract_armor()` converts strength modifier to score (10 + 2 * mod)
- [ ] `_extract_shield()` infers bt as hp // 2 when null
- [ ] `_extract_lores()` strips " Lore" suffix correctly
- [ ] `_normalize_trait()` converts all kebab-case traits
- [ ] Phase B+ simplifications commented in code
- [ ] `test_imported_aetregan_ev_critical_fields` passes before factories updated
- [ ] `sim/party.py` factories updated to call importer
- [ ] `make_rook_combat_state()` unchanged
- [ ] `CHARACTERS.md` updated for Aetregan Deception/Nature
- [ ] All 24 tests written and passing
- [ ] `pytest tests/ -v` passes 490+ tests
- [ ] Strike Hard EV reported (new target if changed)
- [ ] Full combat CLI run with imported party reviewed
- [ ] CHANGELOG.md and current_state.md updated
- [ ] Commit pushed
