# Phase B — Pass 2 Brief: Corrections and Refinements

## Purpose

This brief applies corrections to the Pass 1 plan. Read Pass 1 alongside this
document. Where Pass 2 contradicts Pass 1, Pass 2 wins.

All ten design questions from Pass 1 are resolved below. No blockers remain.

---

## Correction 1: Weapon/Armor Proficiency Comes from Class Item (Not Lookup Table)

**Pass 1 proposed:** `CLASS_PROFICIENCY_PROFILES` lookup table (Option C).

**Pass 2 rejects this.** Direct inspection of the Foundry JSON confirms the
class item stores proficiency ranks in structured fields:

```python
# From Guardian class item (Rook):
item['system']['attacks'] = {
    'simple': 1,    # trained
    'martial': 1,   # trained
    'advanced': 0,  # untrained
    'unarmed': 1    # trained
}
item['system']['defenses'] = {
    'heavy': 1,     # trained
    'medium': 1,
    'light': 1,
    'unarmored': 1
}
```

Extract directly. No lookup table needed. The class item IS the source for
`weapon_proficiencies` and `armor_proficiency` on `Character`.

```python
def _extract_class_proficiencies(class_item: dict) -> tuple:
    attacks = class_item['system']['attacks']
    weapon_profs = {
        WeaponCategory.SIMPLE:   RANK_MAP[attacks.get('simple', 0)],
        WeaponCategory.MARTIAL:  RANK_MAP[attacks.get('martial', 0)],
        WeaponCategory.ADVANCED: RANK_MAP[attacks.get('advanced', 0)],
        WeaponCategory.UNARMED:  RANK_MAP[attacks.get('unarmed', 0)],
    }

    defenses = class_item['system']['defenses']
    # Take the best armor proficiency rank (heavy > medium > light)
    armor_rank = max(
        defenses.get('heavy', 0),
        defenses.get('medium', 0),
        defenses.get('light', 0),
    )
    armor_prof = RANK_MAP[armor_rank]

    return weapon_profs, armor_prof
```

`class_dc_rank` = TRAINED (rank 1) for all four classes at L1. Hard-coded as a
constant — it doesn't appear to be stored separately in the class item.

---

## Correction 2: Foundry JSONs Are Already Uploaded

**Pass 1 said:** Foundry JSONs are a blocker — not in repo yet.

**Pass 2 resolves:** The four files were uploaded by Bryan and are available at:

```
/mnt/user-data/uploads/fvtt-Actor-jotan-aethregen-hiDy2hZf2KqSewPy.json
/mnt/user-data/uploads/fvtt-Actor-rook-CaZCAKANLer542FO.json
/mnt/user-data/uploads/fvtt-Actor-dalai-alpaca-M1n02jHO7Lt6ZtsJ.json
/mnt/user-data/uploads/fvtt-Actor-erizin-nTcnSbOALfHke9sY.json
```

Copy all four to `characters/` with clean names:

```
characters/fvtt-aetregan.json
characters/fvtt-rook.json
characters/fvtt-dalai.json
characters/fvtt-erisen.json
```

---

## Correction 3: Shield Data Is Structured — Not from Description HTML

**Pass 1 was uncertain** about where shield hardness, HP, and BT come from.

**Pass 2 confirms:** All values are directly on the shield item's system dict:

```python
# Steel Shield (confirmed from Rook and Aetregan JSONs):
item['system']['hardness']         = 5
item['system']['hp']['max']        = 20
item['system']['brokenThreshold']  = None   # infer as hp.max // 2 when None
item['system']['acBonus']          = 2
```

```python
def _extract_shield(items: list) -> Shield | None:
    for item in items:
        if item.get('type') == 'shield':
            sys = item['system']
            hp_max = sys.get('hp', {}).get('max', 20)
            bt = sys.get('brokenThreshold') or hp_max // 2
            return Shield(
                name=item['name'],
                ac_bonus=sys.get('acBonus', 2),
                hardness=sys.get('hardness', 5),
                hp=hp_max,
                bt=bt,
            )
    return None
```

---

## Correction 4: Weapon Group Is in item.system.group

**Pass 1 was uncertain** about WeaponGroup source.

**Pass 2 confirms:** The group is a lowercase string in `item['system']['group']`.

Add to the importer:

```python
WEAPON_GROUP_MAP = {
    'flail':   WeaponGroup.FLAIL,
    'hammer':  WeaponGroup.HAMMER,
    'sword':   WeaponGroup.SWORD,
    'knife':   WeaponGroup.KNIFE,
    'firearm': WeaponGroup.FIREARM,
    'bomb':    WeaponGroup.BOMB,
    'bow':     WeaponGroup.BOW,
    'dart':    WeaponGroup.DART,
    'axe':     WeaponGroup.AXE,
    'brawling':WeaponGroup.BRAWLING,
    'club':    WeaponGroup.CLUB,
    'polearm': WeaponGroup.POLEARM,
    'shield':  WeaponGroup.SHIELD,
    'sling':   WeaponGroup.SLING,
    'spear':   WeaponGroup.SPEAR,
    'whip':    WeaponGroup.FLAIL,  # Scorpion Whip is group=flail
}
```

Confirm the full `WeaponGroup` enum values by reading `pf2e/types.py` before
writing this mapping.

---

## Correction 5: Weapon Hands from usage Field

**Pass 1 missed** the `hands` field on `Weapon`.

**Pass 2 confirms:** Foundry stores hands in `item['system']['usage']['value']`:
- `"held-in-one-hand"` → `hands=1`
- `"held-in-two-hands"` → `hands=2`

For the **equipped/active weapon** determination, use
`item['system']['equipped']['handsHeld'] > 0`. For Rook:
- Earthbreaker: `handsHeld=2` → currently held (active)
- Light Hammer, Barricade Buster, Bottled Lightning: `handsHeld=0` → worn/stowed

Import all weapons but flag the active ones. The `equipped_weapons` tuple should
put actively held weapons first.

**Earthbreaker two-hand note:** Earthbreaker has `usage="held-in-one-hand"` but
Rook is holding it in two hands (`handsHeld=2`). When wielded two-handed, the
damage die upgrades to d10 via the `two-hand-d10` trait. For Phase B, model it
as d6 (base) since Rook carries a shield — a character can't simultaneously
wield a two-handed weapon and hold a shield. Flag in code as Phase B+ enhancement
for two-hand mode detection.

---

## Correction 6: Armor Strength Threshold

**Pass 1 missed** `strength_threshold` on `ArmorData`.

**Pass 2 confirms:** Stored as `item['system']['strength']` — an integer
representing the Strength **modifier** required (not the score). Full Plate
has `strength=4` meaning Str modifier +4 (= Str 18) to avoid check penalty.

Our `ArmorData.strength_threshold` field — confirm whether it expects the
modifier or the score by reading `pf2e/character.py` before writing the
extraction. Map accordingly.

---

## Correction 7: Aetregan's Deception Is Trained in Real Sheet

**Pass 1 brief and CHARACTERS.md both said:** Deception untrained.

**Pass 2 correction:** The Foundry JSON shows `deception: { rank: 1 }` —
Deception is trained. This is a discrepancy from CHARACTERS.md. Per D10,
the Foundry sheet is authoritative.

**Impact:** With Deception trained, Aetregan can use Create a Diversion and
Feint with her Deception bonus, not just via the Deceptive Tactics substitution.
However, her Warfare Lore (+8) is still higher than trained Deception (+4), so
Deceptive Tactics still improves her rolls on those actions. The flag
`has_deceptive_tactics=True` remains correct.

Update CHARACTERS.md to reflect Deception trained. The importer will import
it correctly from the JSON.

**Also note:** Aetregan's `nature` skill shows rank 0 (untrained) in the JSON.
CHARACTERS.md listed Nature as trained. The JSON is authoritative — Nature is
untrained for Aetregan. The importer will correctly set it as untrained.

---

## Correction 8: Non-Existent Flags from Brief's FEAT_FLAG_MAP

**Pass 1 brief proposed** flags that don't exist on `Character`:
- `has_intercept_attack` — does not exist. Use `guardian_reactions=1` instead.
- `has_guardians_armor` — does not exist. Derived from `guardian_reactions > 0`.
- `has_nimble_elf` — does not exist. Set `speed += 5` when "Nimble Elf" in feats.
- `has_overdrive` — does not exist. Not currently modeled on `Character`.

**Corrected FEAT_FLAG_MAP:**

```python
FEAT_FLAG_MAP = {
    "Deceptive Tactics":       "has_deceptive_tactics",
    "Lengthy Diversion":       "has_lengthy_diversion",
    "Plant Banner":            "has_plant_banner",
    "Shield Block":            "has_shield_block",
    "Commander's Banner":      "has_commander_banner",
    "Taunt":                   "has_taunt",
    "Light Mortar Innovation": "has_light_mortar",
    # Anthem and Soothe detected from spell items, not feats (see Pass 1 Q4)
}

# Separate handling (not in FEAT_FLAG_MAP):
# "Guardian's Techniques" → guardian_reactions = 1
# "Nimble Elf" → speed += 5
# "Courageous Anthem" (spell) → has_courageous_anthem = True
# "Soothe" (spell) → has_soothe = True
```

---

## Correction 9: boosts["1"] Structure Confirmed

**Pass 2 confirms** from direct JSON inspection: `system.build.attributes.boosts["1"]`
contains the four free ability boosts chosen at level 1 character creation.
For Aetregan: `["dex", "con", "int", "cha"]`. The key `"1"` is the level
milestone (not a sequential index).

Higher-level characters would have `"5"`, `"10"`, `"15"`, `"20"` keys. Phase B
handles L1 only — only key `"1"` is needed.

---

## Confirmed: All Other Design Decisions

**Q4 — Soothe/Anthem detection:** Check spell items by name. Iterate items of
type `"spell"`, collect names into `spell_names` set, check membership.

**Q6 — Multiple weapons:** Import ALL weapons. The `equipped_weapons` tuple
supports multiple. Order: actively held weapons first (handsHeld > 0), then
stowed weapons.

**Q7 — Trait normalization:** `trait.replace("-", "_")` throughout.

**Q9 — Factory transition (phased):**
1. Build importer as standalone `import_foundry_actor()` function
2. Add test: `imported_aetregan` matches `make_aetregan()` on EV-critical fields
3. Only after that test passes, update `make_aetregan()` to call the importer
4. For Rook/Dalai/Erisen: accept real data — it replaces grounded defaults

**Fallback factories:** Keep old `make_aetregan()` code as a comment block for
reference, but the function body becomes a one-liner calling the importer. If
the JSON file is missing, raise a descriptive error (not a silent fallback) —
makes missing files obvious rather than hiding them behind stale defaults.

---

## Updated Architecture

No structural changes from Pass 1. The module layout stands:

```
sim/importers/__init__.py     (empty)
sim/importers/foundry.py      (main module)
```

Updated lookup tables (all confirmed from JSON inspection):

```python
# Weapon group mapping (Foundry string → WeaponGroup enum)
WEAPON_GROUP_MAP = { ... }   # see Correction 4

# Feat flag mapping (feat name → Character field name)
FEAT_FLAG_MAP = { ... }      # see Correction 8

# Skill name mapping (Foundry lowercase → Skill enum)
SKILL_NAME_MAP = { ... }     # unchanged from Pass 1

# Proficiency rank mapping (integer → ProficiencyRank enum)
RANK_MAP = {
    0: ProficiencyRank.UNTRAINED,
    1: ProficiencyRank.TRAINED,
    2: ProficiencyRank.EXPERT,
    3: ProficiencyRank.MASTER,
    4: ProficiencyRank.LEGENDARY,
}
```

---

## Pass 3 Implementation Order

1. Copy four Foundry JSONs from uploads to `characters/`
2. Create `sim/importers/__init__.py` (empty)
3. Create `sim/importers/foundry.py` skeleton with all lookup tables
4. Implement `_extract_ability_scores()` from ancestry + background + class
   key ability + build boosts
5. Implement `_extract_class_proficiencies()` from class item attacks/defenses
6. Implement `_extract_weapons()` — all weapons, active first, trait normalization
7. Implement `_extract_armor()` with strength_threshold
8. Implement `_extract_shield()` with hardness/hp/bt
9. Implement `_extract_skills()` from system.skills ranks
10. Implement `_extract_lores()` from lore-type items
11. Implement `_detect_feat_flags()` — feats + spells + special cases
12. Implement `_derive_speed()` from ancestry base speed + Nimble Elf feat
13. Implement `import_foundry_actor()` — assemble all components into Character
14. Write test: `imported_aetregan` matches `make_aetregan()` on key fields
15. Write remaining tests (see strategy)
16. Run `pytest` — all existing tests pass
17. Strike Hard EV 8.55 regression with imported Aetregan (13th verification)
18. Update `make_aetregan()` and other factories to call importer
19. Update CHARACTERS.md: Aetregan Deception trained; Nature untrained
20. Run full combat with imported party, paste output for review
21. CHANGELOG + current_state.md update

---

## Test Strategy

Expected range: 466 → ~490 (24 new tests).

| Test | What to assert |
|---|---|
| `test_import_aetregan_ability_scores` | STR 10, DEX 16, CON 12, INT 18, WIS 12, CHA 10 |
| `test_import_aetregan_max_hp` | 15 (Elf 6 + Commander 8 + Con 1) |
| `test_import_aetregan_deception_trained` | skill_proficiencies[Skill.DECEPTION] == TRAINED |
| `test_import_aetregan_nature_untrained` | skill_proficiencies[Skill.NATURE] == UNTRAINED |
| `test_import_aetregan_warfare_lore` | lores["Warfare"] == TRAINED |
| `test_import_aetregan_feat_flags` | has_deceptive_tactics=True, has_commander_banner=True |
| `test_import_aetregan_weapon` | Scorpion Whip, d4 slashing, group=FLAIL |
| `test_import_rook_primary_weapon` | Earthbreaker first in tuple, d6 bludgeoning, group=HAMMER |
| `test_import_rook_all_weapons` | 4 weapons in equipped_weapons tuple |
| `test_import_rook_armor` | Full Plate, acBonus=6, speedPenalty=-10 |
| `test_import_rook_shield` | Steel Shield, hardness=5, hp=20, bt=10 |
| `test_import_rook_guardian_reactions` | guardian_reactions=1 |
| `test_import_rook_weapon_proficiency` | MARTIAL=TRAINED, HEAVY_ARMOR=TRAINED |
| `test_import_dalai_anthem` | has_courageous_anthem=True |
| `test_import_dalai_soothe` | has_soothe=True |
| `test_import_dalai_weapon` | Rapier Pistol, d4 piercing |
| `test_import_erisen_mortar` | has_light_mortar=True |
| `test_import_erisen_speed` | speed=35 (Elf 30 + Nimble Elf 5) |
| `test_import_erisen_weapon` | Dueling Pistol, d6 piercing |
| `test_importer_aetregan_ev_critical_fields` | abilities, armor, weapon, perception match factory |
| `test_strike_hard_ev_8_55_with_imported_aetregan` | 13th verification |
| `test_foundry_json_missing_raises_error` | FileNotFoundError with clear message |
| `test_trait_normalization` | "thrown-20" → "thrown_20" |
| `test_weapon_group_mapping` | "flail" → WeaponGroup.FLAIL |

---

## Common Pitfalls

1. **AbilityScores field names:** `str_` and `int_` (not `str` and `int`) due
   to Python keyword conflicts. The importer must map `"str"` → `str_` and
   `"int"` → `int_` when constructing `AbilityScores`.

2. **Earthbreaker two-hand:** Rook holds the Earthbreaker with `handsHeld=2`
   but uses a shield. The importer should import it as d6 (base die) and flag
   `# two-hand-d10 ignored: Rook carries shield` in a comment. Do not apply
   the d10 upgrade.

3. **BrokenThreshold None:** When `brokenThreshold` is null in the JSON, infer
   as `hp.max // 2`. Never leave it as None — `Shield.bt` expects an int.

4. **Proficiency rank for class_dc:** Not stored in the class item's attacks or
   defenses. Hard-code as `ProficiencyRank.TRAINED` for all four classes at L1.

5. **EV 8.55 regression timing:** Run the regression test before updating the
   factory functions. If the imported Aetregan doesn't match on EV-critical
   fields, fix the importer first — don't swap the factory until it passes.

6. **Dalai's Rapier Pistol:** Type is `weapon` in Foundry but it's a combination
   weapon. Import as melee d4 piercing. Add a comment:
   `# Combination weapon: melee mode only. Phase B+ handles ranged mode.`

7. **Nature skill:** Aetregan's Foundry JSON shows nature as rank 0 (untrained).
   CHARACTERS.md had it as trained. The JSON wins — import as untrained and
   update CHARACTERS.md.
