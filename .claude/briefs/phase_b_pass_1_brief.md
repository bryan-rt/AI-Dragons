# Phase B — Pass 1 Brief: Foundry Actor Importer

## Context

This is a **Pass 1 architectural planning brief**. Do not write production code.
Read the existing codebase, surface design questions, and report findings.

**State at handoff:**

- CP7 complete, 466+ tests, EV 8.55 (12th verification)
- All four party member Foundry actor JSONs examined
- Significant discrepancies found between grounded defaults and real sheets
  (documented below — these are bugs in our defaults, not the importer)
- Architecture decisions D25–D28 are binding

**Goal:** Build a Foundry actor JSON importer in `sim/importers/foundry.py` that
produces the same `Character` dataclass as the existing factory functions, but
sourced from real character data instead of hand-coded defaults.

---

## Critical Discrepancies Found in Real Character Sheets

Before writing the importer, these grounded-default bugs must be documented.
They are corrected as part of the importer implementation (real data wins).

### Rook (Guardian)

| Field | Grounded Default | Real Sheet | Impact |
|---|---|---|---|
| Primary weapon | Longsword (d8 slashing) | Earthbreaker (d6 bludgeoning, two-hand d10) | High — bludgeoning vs Bandit2 changes recommendations |
| Secondary weapons | None | Light Hammer (d6 bludgeoning agile thrown-20), Barricade Buster (d10 gun), Bottled Lightning | Medium |
| Trained skills | Athletics, Intimidation, Society, Crafting | Diplomacy, Crafting, Survival, Medicine | Low |
| Feats | Intercept Attack explicit | Guardian's Techniques (umbrella feat containing Intercept Attack) | Low |

Rook's Earthbreaker is bludgeoning — this means he naturally counters Bandit2's
resistance/weakness profile without needing Recall Knowledge. This changes the
tactical recommendations significantly.

### Dalai Alpaca (Bard)

| Field | Grounded Default | Real Sheet | Impact |
|---|---|---|---|
| Primary weapon | Rapier (d6 piercing, finesse, deadly d8, disarm) | Rapier Pistol (d4 piercing, backstabber, concussive, fatal-d8, combination) | Medium |
| Secondary weapon | None | Dagger (d4 piercing, agile, finesse, thrown-10) | Low |
| Feats | Basic bard | Hymn of Healing, Natural Ambition, Martial Performance, Warrior muse | Medium |
| Spells | Courageous Anthem, Soothe | 11 spells in spellcastingEntry | Medium |
| Trained skills | Occultism, Performance, Diplomacy, Intimidation, Athletics, Acrobatics | Diplomacy, Thievery, Acrobatics, Society, Survival, Deception | Low-Medium |

Dalai's Rapier Pistol is a combination weapon (melee + ranged). The importer
needs to handle both modes. For CP Phase B, model it as the melee mode (d4
piercing) for simplicity — flag as Phase B+ for full combination weapon support.

### Erisen (Inventor)

| Field | Grounded Default | Real Sheet | Impact |
|---|---|---|---|
| Primary weapon | Dagger (d4 piercing, agile, finesse, thrown-10) | Dueling Pistol (d6 piercing, concussive, fatal-d10) | Medium |
| Armor | Studded Leather (+2 AC, dex cap 3) | Leather Armor (+1 AC, dex cap 4) | Low |
| Feats | Light Mortar, Overdrive, Nimble Elf | Light Mortar, Overdrive, Nimble Elf, Wizard Dedication, Explosive Leap, Peerless Inventor | Low |

### Aetregan (Commander)

Aetregan's sheet largely matches CHARACTERS.md (already reconciled in CP4.5).
Minor note: the Foundry sheet shows deception rank 1 in the first 5 skills
listed — agent must verify the full skills dict to confirm whether Deception
is actually trained or if the Foundry sheet differs from our canonical data.

---

## Foundry Actor JSON Structure

From direct inspection of the four uploaded files:

```
{
  "name": "Jotan Aethregen",
  "type": "character",
  "system": {
    "abilities": null,                    # Always null — ability scores live elsewhere
    "build": {
      "attributes": {
        "boosts": {
          "1": ["dex", "con", "int", "cha"]  # Boosts chosen at each milestone
        }
      }
    },
    "attributes": {
      "hp": { "value": 15, "temp": 0 },   # Current HP only — max not stored here
      "ac": {},                            # Empty — computed by Foundry
      "speed": {},                         # Empty — computed by Foundry
      "saves": {},                         # Empty — computed by Foundry
      "perception": {}                     # Empty — computed by Foundry
    },
    "details": {
      "level": { "value": 1 },
      "languages": { "value": ["dwarven", "osiriani", ...] }
    },
    "skills": {
      "acrobatics": { "rank": 1 },         # 0=untrained, 1=trained, 2=expert, etc.
      "deception": { "rank": 0 },          # Rank 0 = untrained
      ...
    },
    "initiative": { "statistic": "perception" }
  },
  "items": [                               # Array of embedded items
    {
      "name": "Scorpion Whip",
      "type": "weapon",
      "system": {
        "damage": { "dice": 1, "die": "d4", "damageType": "slashing" },
        "traits": { "value": ["disarm", "finesse", "reach", "trip"] },
        "category": "martial"
      }
    },
    {
      "name": "Full Plate",
      "type": "armor",
      "system": {
        "category": "heavy",
        "acBonus": 6,
        "dexCap": 0,
        "checkPenalty": -3,
        "speedPenalty": -10
      }
    },
    {
      "name": "Deceptive Tactics",
      "type": "feat",
      "system": { "category": "class", ... }
    },
    {
      "type": "class",
      "name": "Commander",
      "system": {
        "keyAbility": { "value": ["int"] },
        "hp": 8,                           # Class HP per level
        "perception": 2,                   # Proficiency rank (2=expert)
        "savingThrows": {
          "fortitude": 1, "reflex": 2, "will": 2
        }
      }
    },
    {
      "type": "ancestry",
      "name": "Elf",
      "system": {
        "hp": 6,                           # Ancestry HP
        "speed": 30,
        "boosts": { "value": ["dex", "int"] }
      }
    },
    {
      "type": "lore",
      "name": "Warfare Lore",
      "system": { "proficient": { "value": 1 } }
    }
  ]
}
```

**Key insight:** Foundry stores the *inputs* to character creation, not the
*derived* stats. AC, saves, perception, speed are all computed at runtime by
Foundry's rules engine. The importer must re-derive these from the raw inputs
using the same formulas our `pf2e/combat_math.py` already implements.

This is actually ideal — it matches our "derive, don't store" philosophy exactly.

---

## Pre-Implementation Reading List

```
pf2e/character.py            — Character dataclass, all fields and flags
pf2e/combat_math.py          — armor_class(), save_bonus(), perception_bonus(),
                               skill_bonus(), lore_bonus(), max_hp()
pf2e/abilities.py            — AbilityScores, mod()
pf2e/proficiency.py          — proficiency_bonus(), ProficiencyRank
pf2e/equipment.py            — Weapon, ArmorData, Shield, WeaponRunes, EquippedWeapon
pf2e/types.py                — Ability, Skill, DamageType, WeaponCategory enums
sim/party.py                 — make_aetregan(), make_rook() etc. — target interface
characters/aetregan.json     — existing Pathbuilder JSON for cross-reference
```

After reading, report:
- Exact fields on `Character` that the importer must populate
- Which `has_*` flags exist and what feat names trigger them
- Whether `Character` currently supports multiple weapons or just one primary

---

## Scope

Deliver the following in this checkpoint:

1. New module: `sim/importers/foundry.py`
2. `import_foundry_actor(path: str) -> Character` — main entry point
3. Updated factory functions in `sim/party.py` — thin wrappers calling importer
4. Ability score derivation from `build.attributes.boosts`
5. Derived stat computation (AC, saves, perception, speed) from raw inputs
6. Feat flag detection from item names
7. Skill proficiency import from `system.skills` ranks
8. Weapon and armor import from items array
9. HP derivation from ancestry HP + class HP + Con modifier
10. Lore detection from `lore` type items
11. Validation: importer produces same `Character` as current factory functions
    for Aetregan (killer regression — EV 8.55 must hold)
12. Import all four party members and update `sim/party.py` to use real data

**Out of scope:** Spellcasting full import (Dalai's 11 spells), combination
weapon dual-mode (Dalai's Rapier Pistol), gun mechanics (Erisen's Dueling
Pistol beyond basic damage), Phase B+ effects catalog.

---

## Architecture

### Module: sim/importers/foundry.py

```python
def import_foundry_actor(path: str) -> Character:
    """Import a Foundry VTT pf2e actor JSON and return a Character.

    Derives all stats from raw character creation inputs using the same
    formulas as pf2e/combat_math.py. Does not trust Foundry's computed
    fields (ac, saves, speed) — re-derives them.
    """
```

Internal helpers (all private):

```python
def _extract_ability_scores(data: dict) -> AbilityScores
def _extract_class_data(items: list) -> dict      # hp, key_ability, saves, perception
def _extract_ancestry_data(items: list) -> dict   # hp, speed, boosts
def _extract_weapons(items: list) -> list[EquippedWeapon]
def _extract_armor(items: list) -> ArmorData | None
def _extract_shield(items: list) -> Shield | None
def _extract_feats(items: list) -> set[str]       # normalized feat name set
def _extract_skills(system: dict) -> dict[Skill, ProficiencyRank]
def _extract_lores(items: list) -> dict[str, ProficiencyRank]
def _feat_flags(feat_names: set[str], level: int) -> dict  # has_* flags
```

### Ability Score Derivation

Foundry stores boosts taken at each level milestone in
`system.build.attributes.boosts`. At L1, every character starts with 10 in all
abilities, then applies:

1. Ancestry boosts (from the ancestry item's `system.boosts.value`)
2. Background boosts (from the background item's `system.boosts.value`)
3. Class key ability boost (from the class item's `system.keyAbility.value[0]`)
4. Free boosts chosen by player (in `system.build.attributes.boosts["1"]`)

Each boost raises a score by 2 (if ≤ 18) or 1 (if > 18). At L1, all scores
start ≤ 18, so each boost is always +2.

```python
def _extract_ability_scores(data: dict) -> AbilityScores:
    base = {ab: 10 for ab in ['str','dex','con','int','wis','cha']}

    # Ancestry boosts
    for item in items:
        if item['type'] == 'ancestry':
            for ab in item['system']['boosts']['value']:
                base[ab] += 2
            # Ancestry flaws (if any)
            for ab in item['system'].get('flaws', {}).get('value', []):
                base[ab] -= 2

    # Background boosts
    for item in items:
        if item['type'] == 'background':
            for ab in item['system']['boosts']['value']:
                base[ab] += 2

    # Class key ability
    for item in items:
        if item['type'] == 'class':
            key = item['system']['keyAbility']['value'][0]
            base[key] += 2

    # Player-chosen free boosts at level 1
    free_boosts = data['system']['build']['attributes']['boosts'].get('1', [])
    for ab in free_boosts:
        base[ab] += 2

    return AbilityScores(**base)
```

**Note:** Some boosts may overlap (ancestry + free). The system handles this
correctly — each is additive, scored to total ability score.

### Derived Stat Computation

Do not read Foundry's computed AC, saves, or perception. Re-derive:

```python
level = data['system']['details']['level']['value']

# Max HP = ancestry_hp + (class_hp + con_mod) × level
ancestry_hp = <from ancestry item system.hp>
class_hp = <from class item system.hp>
con_mod = ability_scores.mod(Ability.CON)
max_hp = ancestry_hp + (class_hp + con_mod) * level

# AC = 10 + dex_mod (capped by armor dex cap) + armor_bonus + proficiency_bonus
# proficiency_bonus = armor proficiency rank + level
# Use existing armor_class() from combat_math.py

# Saves = ability_mod + proficiency_bonus(rank, level)
# Ranks come from class item: system.savingThrows.fortitude/reflex/will
# 1=trained, 2=expert etc. → ProficiencyRank enum

# Perception = wis_mod + proficiency_bonus(perception_rank, level)
# perception_rank from class item: system.perception
```

### Feat Flag Detection

Map feat names found in items array to `has_*` flags on `Character`:

```python
FEAT_FLAG_MAP = {
    "Deceptive Tactics":    "has_deceptive_tactics",
    "Lengthy Diversion":    "has_lengthy_diversion",
    "Plant Banner":         "has_plant_banner",
    "Shield Block":         "has_shield_block",
    "Commander's Banner":   "has_commander_banner",
    "Guardian's Techniques":"has_intercept_attack",  # umbrella feat
    "Guardian's Armor":     "has_guardians_armor",
    "Taunt":                "has_taunt",
    "Light Mortar Innovation": "has_light_mortar",
    "Overdrive":            "has_overdrive",
    "Nimble Elf":           "has_nimble_elf",
    # Bard features (from class item or specific feats)
    "Composition Spells":   "has_courageous_anthem",
    "Spell Repertoire":     "has_soothe",  # Dalai has both — verify spell list
}
```

**Design question for Pass 2:** Dalai has 11 spells. Should the importer check
the spells list for "Soothe" specifically (more accurate) or infer from class
feats (simpler)? Recommend checking spells list: iterate items of type `spell`,
look for name == "Soothe".

### Weapon Import

For each item of type `weapon`:

```python
weapon = Weapon(
    name=item['name'],
    damage_dice=item['system']['damage']['dice'],
    damage_die=item['system']['damage']['die'],        # "d6", "d8" etc.
    damage_type=DamageType[item['system']['damage']['damageType'].upper()],
    traits=item['system']['traits']['value'],
    category=item['system'].get('category', 'martial'),
    # Derived from traits:
    is_agile='agile' in traits,
    is_finesse='finesse' in traits,
    is_reach='reach' in traits,
    has_thrown='thrown-10' in traits or 'thrown-20' in traits,
    is_ranged=False,  # melee default; override for guns
)
```

**Primary weapon selection:** If multiple weapons, pick the primary by priority:
1. The weapon equipped in the main hand (check `system.equipped.inSlot` or
   `system.equipped.handsHeld`)
2. If no equipped indicator, pick highest damage die

**Rook's Earthbreaker note:** The Earthbreaker has `two-hand-d10` trait — when
wielded two-handed, the damage die upgrades to d10. For CP Phase B, model it as
the one-hand die (d6) since Rook carries a shield. Flag as Phase B+ enhancement.

**Erisen's Dueling Pistol note:** Guns have `concussive` and `fatal-d10` traits.
Concussive means the weapon uses the better of piercing or bludgeoning resistance
against the target. For CP Phase B, model as flat piercing damage. Flag as Phase
B+ enhancement.

**Dalai's Rapier Pistol note:** Combination weapon — melee or ranged. For Phase
B, model as melee d4 piercing. Flag as Phase B+ enhancement.

### Armor Import

```python
armor = ArmorData(
    name=item['name'],
    category=item['system']['category'],           # "light", "medium", "heavy"
    ac_bonus=item['system']['acBonus'],
    dex_cap=item['system'].get('dexCap'),          # None = no cap
    check_penalty=item['system'].get('checkPenalty', 0),
    speed_penalty=item['system'].get('speedPenalty', 0),
)
```

### Skill Import

```python
SKILL_NAME_MAP = {
    'acrobatics': Skill.ACROBATICS,
    'arcana': Skill.ARCANA,
    'athletics': Skill.ATHLETICS,
    'crafting': Skill.CRAFTING,
    'deception': Skill.DECEPTION,
    'diplomacy': Skill.DIPLOMACY,
    'intimidation': Skill.INTIMIDATION,
    'medicine': Skill.MEDICINE,
    'nature': Skill.NATURE,
    'occultism': Skill.OCCULTISM,
    'performance': Skill.PERFORMANCE,
    'religion': Skill.RELIGION,
    'society': Skill.SOCIETY,
    'stealth': Skill.STEALTH,
    'survival': Skill.SURVIVAL,
    'thievery': Skill.THIEVERY,
}

RANK_MAP = {0: ProficiencyRank.UNTRAINED, 1: ProficiencyRank.TRAINED,
            2: ProficiencyRank.EXPERT, 3: ProficiencyRank.MASTER,
            4: ProficiencyRank.LEGENDARY}
```

### Lore Import

```python
lores = {}
for item in items:
    if item['type'] == 'lore':
        name = item['name'].replace(' Lore', '')  # "Warfare Lore" → "Warfare"
        rank = item['system']['proficient']['value']
        lores[name] = RANK_MAP[rank]
```

---

## Updated sim/party.py

After the importer is built, update factory functions to call it:

```python
def make_aetregan() -> Character:
    return import_foundry_actor("characters/fvtt-aetregan.json")

def make_rook() -> Character:
    return import_foundry_actor("characters/fvtt-rook.json")
```

Copy the four uploaded JSONs to `characters/` directory with clean names.

The old hand-coded factories remain as fallbacks (in case JSON is missing)
but the importer is the primary path.

---

## Validation — Killer Regression

The importer must produce a `Character` for Aetregan that, when used in the
Strike Hard scenario, still produces EV 8.55.

```python
def test_foundry_importer_aetregan_matches_factory():
    """Imported Aetregan produces same Character as make_aetregan()."""
    imported = import_foundry_actor("characters/fvtt-aetregan.json")
    factory = make_aetregan()
    # Key fields must match exactly:
    assert imported.ability_scores == factory.ability_scores
    assert imported.max_hp == factory.max_hp  # derived, not stored
    assert imported.skill_proficiencies == factory.skill_proficiencies
    # etc.

def test_strike_hard_ev_8_55_with_imported_characters():
    """13th verification — EV 8.55 with importer-sourced characters."""
    # Load scenario, but override party with imported characters
    # EV must still be 8.55
```

**Note:** Rook's weapon change (Longsword → Earthbreaker) will change some EVs
in the two-bandit scenario. The EV 8.55 regression uses Rook's Longsword Strike
in the canonical single-bandit scenario. Confirm whether Rook's equipped weapon
in that scenario changes. If the scenario hardcodes the weapon, EV 8.55 holds.
If Rook's weapon comes from the character factory, EV may change — establish a
new target if needed.

---

## Design Questions to Surface After Reading

1. Does `Character` support multiple weapons, or only one primary? If one,
   how should the importer select the primary from Rook's 4 weapons?
2. Does `Character` currently have an `armor_proficiency_rank` field, or is
   it inferred from character class? Needed to compute AC correctly.
3. Where does the class's save proficiency rank live on `Character`? The class
   item in Foundry provides it — does our `Character` store it or re-derive?
4. Is `has_soothe` currently checking the spells list or inferring from feats?
   Confirm before the importer implements the same logic.
5. What is Rook's equipped weapon slot in his Foundry JSON? (Check
   `item['system']['equipped']` for each of his 4 weapons.)

---

## Test Strategy

Expected range: 466 → ~490 (24 new tests).

| Test | What to assert |
|---|---|
| `test_import_aetregan_ability_scores` | STR 10, DEX 16, CON 12, INT 18, WIS 12, CHA 10 |
| `test_import_aetregan_max_hp` | 15 (Elf 6 + Commander 8 + Con 1) |
| `test_import_aetregan_feat_flags` | has_deceptive_tactics=True, has_commander_banner=True |
| `test_import_aetregan_skills` | Acrobatics trained, Deception untrained (verify from JSON) |
| `test_import_aetregan_lores` | Warfare Lore trained |
| `test_import_rook_weapon` | Primary weapon is Earthbreaker, bludgeoning |
| `test_import_rook_armor` | Full plate, AC bonus 6, speed penalty -10 |
| `test_import_rook_feat_flags` | has_taunt=True, has_intercept_attack=True |
| `test_import_dalai_spells` | has_soothe=True (Soothe in spell list) |
| `test_import_dalai_anthem` | has_courageous_anthem=True |
| `test_import_erisen_mortar` | has_light_mortar=True |
| `test_import_erisen_weapon` | Primary weapon is Dueling Pistol, d6 piercing |
| `test_importer_produces_same_aetregan_as_factory` | All key fields match |
| `test_strike_hard_ev_8_55_with_imported_party` | 13th verification |
| `test_full_combat_with_imported_party` | solve_combat() produces victory |
