# Task Brief Pass 2.5: PF2e Simulator — Clarifications + Foundation Implementation

## Context

Your Pass 2 architectural plan is **approved** with corrections. This brief does two things:

1. **Part A** answers your open questions and provides full character data so you stop guessing.
2. **Part B** authorizes you to implement the **foundation layer only** (rules engine + tests), not the simulator yet. Tactic dispatch and turn evaluation remain in planning until Pass 3.

The reasoning for splitting implementation: the foundation (Character, Weapon, combat math derivation functions) is well-specified and stable. Implementing it now lets us validate the rules engine against concrete test numbers before we build the more architecturally novel turn-planning layer on top of it.

**Cite Archives of Nethys URLs for every mechanical claim**, same rule as Pass 1.5. Mark anything you cannot verify as `(UNVERIFIED — please confirm)`.

---

# Part A: Clarifications and Character Data

## A.1 Answers to your Pass 2 open questions

### 7.1 Thrown weapon attack ability — Dex for attack, Str for damage

**Confirmed.** Thrown weapons make a ranged attack roll (uses Dex per the general ranged rule), but they add full Str modifier to damage (per the thrown trait). If a weapon is BOTH thrown AND finesse (rare, e.g., dagger), the finesse trait applies to its melee Strike only. When thrown, it uses Dex for attack regardless. (AoN: https://2e.aonprd.com/Traits.aspx?ID=195)

Implementation: your `attack_ability()` function as written is correct. Remove the UNVERIFIED tag.

### 7.2 Frightened does NOT apply to damage rolls

**Confirmed.** Frightened applies a status penalty equal to its value to "all your checks and DCs." Damage rolls are not checks. They are damage rolls. The penalty does NOT apply to damage. (AoN: https://2e.aonprd.com/Conditions.aspx?ID=42)

Implementation: remove the frightened penalty from `damage_avg()`. Keep it in `attack_bonus()` (attack rolls are checks) and `armor_class()` (AC is a DC).

### 7.3 Guardian key ability is the player's choice

Guardians get a free attribute boost choice between Str and Dex at level 1, then another boost into the same one for the +4 starting ability. (AoN: https://2e.aonprd.com/Classes.aspx?ID=67) Rook's player chose Str. See Rook's character sheet below.

### 7.4 Aetregan IS the Commander

Full sheet below in A.2. Int 18 is correct, key ability is Int.

### 7.5 The four UNVERIFIED tactics — corrected list

The Commander's prepared tactics for this campaign are NOT the eight you listed. Aetregan's actual folio at level 1 contains **5 tactics** (the first-level allowance), and he prepares **3 of those 5 per day**. Here's the correct full picture:

**Aetregan's folio (5 tactics — all level-1 mobility/offensive options):**
1. **Strike Hard!** — confirmed (AoN: https://2e.aonprd.com/Tactics.aspx?ID=13)
2. **Gather to Me!** — confirmed (AoN: https://2e.aonprd.com/Tactics.aspx?ID=2)
3. **Tactical Takedown** — confirmed (AoN: https://2e.aonprd.com/Tactics.aspx?ID=14)
4. **Defensive Retreat** — confirmed exists (AoN: https://2e.aonprd.com/Tactics.aspx — search "Defensive Retreat")
5. **Mountaineering Training** — confirmed (AoN: https://2e.aonprd.com/Tactics.aspx — search "Mountaineering Training")

**Tactics he prepares (default, can change daily):** Strike Hard!, Gather to Me!, Tactical Takedown.

**Drop the following from the registry — they are not in his folio:**
- ~~Shields Up!~~ (not prepared)
- ~~Reload!~~ (not prepared)
- ~~Form Up!~~ (not prepared, also we couldn't confirm exact name)
- ~~Coordinating Maneuvers~~ (not prepared)
- ~~Passage of Lines~~ (not prepared)

**Note for the registry:** still implement the data model to support the full Battlecry tactic catalog (so future scenarios can use other tactics as the player levels up), but the Pass 3 evaluator only needs to handle the three currently-prepared ones plus Defensive Retreat and Mountaineering Training as fallbacks.

### 7.6 Confirming the prepared list

Three tactics: Strike Hard!, Gather to Me!, Tactical Takedown. See A.1 / 7.5 above.

### 7.7 Commander's own Strike capability

Aetregan wields a **whip** (1-handed melee, finesse, reach 10 ft, trip, disarm, nonlethal, 1d4 slashing). With Dex 16 and Str 10, attacks at +6 (3 Dex + 3 trained martial), damages at 1d4 + 0 = 2.5 average per hit. **Yes, this is correct math — 1.75 EV vs AC 15 is the right answer.** Pass 1.5's "~2-3 EV" estimate was wrong.

(AoN: https://2e.aonprd.com/Weapons.aspx — search "Whip")

### 7.8 Rook wears full plate

Full plate armor: +6 AC, Dex cap +0, check penalty -3, speed penalty -10, Str threshold 18, Bulk 4. (AoN: https://2e.aonprd.com/Armor.aspx — search "Full Plate")

Rook AC derivation at level 1:
- Base 10 + Dex (+0, capped at +0 by armor) + trained heavy armor (rank 2 + level 1 = +3) + full plate (+6) = **19**
- The brief's earlier target of AC 18 was wrong. Use **AC 19** as the validation target.

Note: Full plate has a Str threshold of 18. Rook has Str 18, so he ignores the check penalty and reduces speed penalty by 5 (so speed penalty becomes -5). Heavy armor proficiency is required — Rook has it via Guardian class.

### 7.9 Dalai's Anthem range — assume always covers party

For the foundation layer, hardcode `anthem_active=True` as a CombatantState construction parameter. Distance checking from Dalai's grid position is a Pass 3 concern (the simulator layer). For the rules engine tests, the +1 status bonus is just an input parameter to the test scenarios.

### 7.10 Allies use default turn templates

Confirmed. Pass 3 will model only the Commander's full turn. Allies are assumed to play "default" turns: Rook does Defensive Advance + Strike, Erisen reloads/aims/launches mortar, Dalai casts Anthem then Strikes. The simulator can let the user override these defaults per scenario.

---

## A.2 Full character sheets

Use these as the source of truth. If anything contradicts earlier briefs, these win.

### Aetregan (the player's character — Commander)

```
Name: Aetregan
Class: Commander (Battlecry!)
Level: 1
Ancestry: Elf
Heritage: Ancient Elf
Background: Disciple of the Gear
Key Ability: Intelligence

Ability Scores: Str 10, Dex 16, Con 12, Int 18, Wis 11, Cha 12
  (Note: Wis is 11 in current build, was 10 originally; user
   swapped Cha boost into Wis. Use 11.)

Proficiencies (level 1):
  Perception: Trained (+4 = Wis +1, +2 trained, +1 level)
  Saves:
    Fortitude: Trained (+4 = Con +2, +2 trained, +1 level)
    Reflex: Expert (+8 = Dex +3, +4 expert, +1 level)
    Will: Expert (+6 = Wis +1, +4 expert, +1 level)
  Class DC: Expert (+6 = Int +4, +4 expert... wait, level 1 Commander
    has class DC at expert? Verify on AoN.)
    NOTE: At level 1, Commander class DC proficiency is trained
    per published Battlecry. Use trained: +6 (Int 4 + trained 2 + level 1 = 7? Wait.)
    Class DC = 10 + Int 4 + trained 2 + level 1 = 17.
    (UNVERIFIED on Commander class DC progression — please verify
     against https://2e.aonprd.com/Classes.aspx?ID=66)

  Weapons:
    Simple: Trained
    Martial: Trained
    Unarmed: Trained
    Advanced: Untrained
  Armor:
    Light: Trained
    Medium: Trained
    Heavy: Trained
    Unarmored: Trained

  Skills (trained):
    Acrobatics, Arcana, Crafting, Occultism, Society, Stealth, Thievery,
    Lore: Warfare, Lore: Deity (deity TBD)
    Plus from updated build: Medicine, Religion, Survival
    (User dropped Deception/Diplomacy/Intimidation when swapping Cha→Wis)

Equipment:
  Armor: Inventor Subterfuge Suit (medium armor that functions as light
    for movement/skills; AC bonus +2)
  Shield: Steel Shield (+2 AC raised, Hardness 5, HP 20)
  Weapon: Whip (1d4 slashing, finesse, reach, trip, disarm, nonlethal)

Class Features (level 1):
  Commander's Banner (carried or planted; 30-ft aura when visible)
  Tactics: Folio of 5, prepared 3 (Strike Hard!, Gather to Me!,
    Tactical Takedown)
  Drilled Reactions (1/round, grant 1 ally extra reaction for tactic)
  Shield Block (general feat from class)

Class Feats:
  Plant Banner (level 1 Commander feat)

Ancestry / Background Feats:
  Free Heart (Elf ancestry — also grants Trick Magic Item skill feat)
  Multitalented (Ancient Elf — granted Inventor Dedication archetype)
  Inventor Dedication (archetype, free from Multitalented)
    Note: Per house rule discussion, Inventor Dedication grants the
    subterfuge suit at level 1 with one initial armor modification:
    Metallic Reactance (resistance 3 to acid and electricity).
  Quick Repair (background-granted skill feat from Disciple of the Gear)

AC Computation:
  10 + Dex (+3, no cap on subterfuge suit which acts as light)
  + trained medium armor (+3) + subterfuge suit item bonus (+2)
  + steel shield raised (+2 if applicable) = 18 (without shield) or 20 (raised)
  Brief's earlier "AC 18" reflects shield-not-raised state. Use 18.

HP:
  8 (Commander class) + 2 (Con) + 6 (Elf ancestry) = 16
```

### Rook (Guardian, Automaton ancestry)

```
Name: Rook
Class: Guardian (Battlecry!)
Level: 1
Ancestry: Automaton (Versatile heritage in CLI's notes — but actual
  ancestry is Automaton. Versatile in the original notes was wrong.)
Heritage: Automaton-specific (Rook should pick one — for now
  treat as default Automaton without heritage features beyond ancestry HP)
Background: Laborer
Key Ability: Strength

Ability Scores: Str 18, Dex 10, Con 16, Int 10, Wis 12, Cha 10
  (Approximate; original notes showed Str+4, Dex+0, Con+3, Wis+1, Cha+1.
   Reconcile: Str 18, Dex 10, Con 16, Int 10, Wis 12, Cha 12. Use these.)

Proficiencies (level 1):
  Perception: Expert (+5 = Wis +1, +4 expert, +1 level)
    NOTE: Verify Guardian perception starts at expert.
    (UNVERIFIED — check https://2e.aonprd.com/Classes.aspx?ID=67)
  Saves:
    Fortitude: Expert (+8 = Con +3, +4 expert, +1 level)
    Reflex: Trained (+4 = Dex +0, +2 trained, +1 level... wait, +3? Verify)
    Will: Expert (+6 = Wis +1, +4 expert, +1 level)
  Class DC: Trained = 10 + Str +4 + trained +2 + level 1 = 17

  Weapons:
    Simple: Trained
    Martial: Trained
    Unarmed: Trained
  Armor:
    Light: Trained
    Medium: Trained
    Heavy: Trained
    Unarmored: Trained

  Skills (trained): Athletics, Crafting, Diplomacy, Lore: Labor,
    Medicine, Survival
  Skill Feats: Hefty Hauler

Equipment:
  Armor: FULL PLATE (+6 AC, Dex cap +0, check penalty -3,
    speed penalty -10 reduced to -5 by Str 18, Str threshold 18, Bulk 4)
  Shield: (TBD — sheet doesn't specify; assume Steel Shield for now)
  Weapon: Longsword (martial 1d8 slashing, versatile P)

Class Features (level 1):
  Guardian's Techniques (Taunt action + Intercept Attack reaction)
  Bonus guardian-only reaction per round
  Shield Block (general feat from class)
  Ever Ready (always gain a reaction at start of combat,
    usable only for guardian feats/features)

Class Feats:
  Defensive Advance (level 1 Guardian feat)

AC Computation:
  10 + Dex (+0, capped at +0 by full plate) + trained heavy (+3)
  + full plate (+6) = 19
  With shield raised: 21

HP:
  10 (Guardian class) + 3 (Con) + ancestry HP (Automaton TBD,
    assume 8 for hardy construct) = 21
  (Original prototype said 22; close enough — verify ancestry HP)
```

### Dalai (Bard, Warrior Muse)

```
Name: Dalai Alpaca
Class: Bard (Warrior Muse subclass)
Level: 1
Ancestry: Human (Vudrani / Indian)
Heritage: Versatile Human
Background: Root Worker
Deity: Shelyn
Key Ability: Charisma

Ability Scores: Str 10, Dex 14, Con 12, Int 14, Wis 10, Cha 18

Proficiencies (level 1):
  Perception: Expert
  Saves:
    Fortitude: Trained
    Reflex: Trained
    Will: Expert
  Class DC: Trained = 10 + Cha +4 + trained +2 + level 1 = 17

  Weapons (Warrior Muse): Simple, Martial, Unarmed all Trained
  Armor: Light, Unarmored Trained
  Spell Attack/DC: Trained, Occult tradition

  Skills (trained): Acrobatics, Deception, Diplomacy, Lore: Herbalism,
    Occultism, Performance, Society, Stealth, Survival, Thievery
  Skill Feats: Root Magic (Occultism)

Equipment:
  Armor: Leather (or studded leather) — assume Leather (+1 AC, Dex cap +4)
  Weapon: Rapier (1d6 piercing, finesse, deadly d8, disarm)

Class Features (level 1):
  Spellcasting (Occult, Spontaneous, Spell Repertoire)
  Composition Spells (Counter Performance focus spell)
  Composition Cantrips (Courageous Anthem)
  Muse: Warrior

Class Feats:
  Hymn of Healing (level 1 Bard feat — adds composition spell)

Ancestry Feats:
  Natural Ambition (free 1st-level Bard class feat — already accounted for)

AC Computation:
  10 + Dex (+2, no cap) + trained light (+3) + leather (+1) = 16

HP:
  8 (Bard) + 1 (Con) + 8 (Human ancestry) = 17
  (Prototype said 16; ancestry HP for Human is 8, so 17 is correct.
   Use 17 in tests.)

Spells:
  Cantrips (5): Courageous Anthem (composition), 4 others TBD
  1st-rank slots: 2 (player chooses spells)
```

### Erisen (Inventor, Munitions Master archetype, Light Mortar Innovation)

```
Name: Erisen
Class: Inventor (Munitions Master class archetype)
Level: 1
Ancestry: Elf
Heritage: Ancient Elf
Background: Alkenstar Sojourner
Deity: Brigh
Key Ability: Intelligence

Ability Scores: Str 10, Dex 14, Con 14, Int 18, Wis 10, Cha 12

Proficiencies (level 1):
  Perception: Trained
  Saves:
    Fortitude: Expert
    Reflex: Expert
    Will: Trained
  Class DC: Trained = 10 + Int +4 + trained +2 + level 1 = 17

  Weapons: Simple, Martial, Unarmed Trained; Light Mortar Trained (martial)
  Armor: Light, Medium, Unarmored Trained

  Skills (trained): Arcana, Athletics, Crafting, Intimidation,
    Lore: Engineering, Medicine, Performance, Society, Stealth, Survival
  Skill Feats: Streetwise (Society)

Equipment:
  Armor: Studded Leather (+2 AC, Dex cap +3)
  Weapon: Dagger (1d4 piercing, agile, finesse, thrown 10ft, versatile S)
  Innovation: Light Mortar (siege weapon)
    - 2d6 bludgeoning at level 1 (scales: 3d6 at 5, 4d6 at 9, etc.)
    - 10-ft burst, 120-ft range increment, basic Reflex save vs Erisen's
      class DC (17 at level 1)
    - Action sequence: Deploy + Aim + Load + Launch (assume pre-deployed
      and pre-loaded for scenario start)
    - Initial Mortar Modification: Spring-Loaded (free-action deploy)

Class Features (level 1):
  Innovation (Light Mortar, with one initial mortar modification)
  Munitions Master (class archetype)
  Nimble Elf (Elf ancestry feat)

Class Feats:
  Explosive Leap (level 1 Inventor feat)

AC Computation:
  10 + Dex (+2, capped) + trained medium (+3) + studded leather (+2) = 17

HP:
  8 (Inventor) + 2 (Con) + 6 (Elf ancestry) = 16
  (Prototype said 18; reconcile by checking Elf base HP — it's 6.
   Use 16 in tests. Or if user wants 18, Toughness general feat could
   account for it, but not at level 1 by default.)
```

---

## A.3 Validation targets for the foundation tests

These are the numbers your foundation implementation MUST reproduce. If any test fails, fix the implementation, not the target.

### Attack and damage EVs

```
Rook longsword Strike vs AC 15:
  attack_bonus = +7  (Str +4, trained martial +3)
  damage_avg on hit = 8.5  (1d8 avg 4.5 + Str 4)
  EV vs AC 15 = 6.80

Aetregan whip Strike vs AC 15 (without Anthem buff):
  attack_bonus = +6  (Dex +3 via finesse, trained martial +3)
  damage_avg on hit = 2.5  (1d4 avg 2.5 + Str 0)
  EV vs AC 15 = 1.75

Aetregan whip Strike vs AC 15 (WITH Courageous Anthem +1 status):
  attack_bonus = +7  (above + 1 status)
  damage_avg on hit = 3.5  (above + 1 status)
  EV vs AC 15 = 2.45  (rough; verify with full enumeration)

Dalai rapier Strike vs AC 15:
  attack_bonus = +5  (Dex +2 via finesse, trained martial +3)
  damage_avg on hit = 3.5  (1d6 avg 3.5 + Str 0)
  Deadly d8 trait adds +1d8 (avg 4.5) on critical hit only.
  EV vs AC 15 = compute and report; should be ~2-3 range

Erisen dagger Strike vs AC 15 (melee, finesse):
  attack_bonus = +5  (Dex +2 via finesse, trained martial +3)
  damage_avg on hit = 2.5  (1d4 avg 2.5 + Str 0)
  EV vs AC 15 = ~1.5
```

### Class DC

```
Aetregan class DC = 17  (10 + Int 4 + trained 2 + level 1)
Erisen class DC = 17    (10 + Int 4 + trained 2 + level 1)
Rook class DC = 17      (10 + Str 4 + trained 2 + level 1)
Dalai class DC = 17     (10 + Cha 4 + trained 2 + level 1)
```

### AC

```
Aetregan AC = 18 without shield, 20 with shield raised
  10 + Dex 3 + trained medium 3 + subterfuge suit 2 [+ shield 2]
Rook AC = 19 without shield, 21 with shield raised
  10 + Dex 0 + trained heavy 3 + full plate 6 [+ shield 2]
Dalai AC = 16
  10 + Dex 2 + trained light 3 + leather 1
Erisen AC = 17
  10 + Dex 2 + trained medium 3 + studded leather 2
```

### Save bonuses

```
Aetregan: Fort +4, Ref +8, Will +6
Rook: Fort +8, Ref +4, Will +6
Dalai: Fort +4, Ref +6, Will +6
Erisen: Fort +6, Ref +6, Will +4
```

### Mortar AoE

```
Erisen mortar (2d6, DC 17, basic Reflex):
  vs target with Reflex +5 (typical low-level enemy):
    EV per target = 5.60
  vs 2 targets in burst: EV total = 11.20
```

---

## A.4 Supplementary action vocabulary for Pass 3

For the eventual turn-planning evaluator, the Commander's supplementary actions (after spending tactic actions) include:

- **Strike** — Commander makes a melee/ranged attack with their own weapon (1 action)
- **Stride** — move up to Speed (1 action)
- **Step** — 5 ft move that doesn't trigger reactive strikes (1 action)
- **Raise a Shield** — +2 circumstance AC until next turn start (1 action)
- **Plant Banner** — deploy banner at current position, grants temp HP aura (1 action)
- **Sustain a Spell** — extend a sustained spell (1 action; not relevant for Aetregan unless multiclass)
- **Recall Knowledge** — ID a creature/feature using a Lore or trained skill (1 action)
- **Demoralize** — Intimidation action to frighten a foe (1 action; Aetregan has Cha 12, low priority)
- **Create a Diversion** — Deception (or Warfare Lore via Deceptive Tactics) to become hidden (1 action)
- **Feint** — Deception (or Warfare Lore via Deceptive Tactics) to make an enemy off-guard to your next attack (1 action)
- **Take Cover** — increases AC against ranged when applicable (1 action)
- **Interact** — manipulate an object, draw a weapon, etc. (1 action)
- **Aid** — prepare to assist an ally's roll (1 action; trigger-based reaction follows)

**Don't implement these in Pass 2.5.** They're documented here so the foundation knows what supplementary actions exist for Pass 3's TurnPlan enumeration.

---

# Part B: Foundation Implementation Brief

## What to implement now

Implement the following modules with full working code and unit tests. **Do NOT implement the simulator (sim/) layer or the tactic dispatcher.** Those are Pass 3.

### Module list

```
pf2e/
├── __init__.py
├── types.py           # Enums: Ability, ProficiencyRank, WeaponCategory,
│                      # WeaponGroup, DamageType, SaveType
├── abilities.py       # AbilityScores dataclass + mod() method
├── proficiency.py     # proficiency_bonus(rank, level) function
├── equipment.py       # Weapon, EquippedWeapon, WeaponRunes, Shield, ArmorData
├── character.py       # Character (frozen=True) + CombatantState (mutable)
└── combat_math.py     # All derivation functions

tests/
├── __init__.py
├── test_abilities.py
├── test_proficiency.py
├── test_equipment.py
├── test_combat_math.py    # Reproduces every validation target in A.3
└── fixtures.py            # make_aetregan(), make_rook(), make_dalai(),
                           # make_erisen() factory functions matching A.2 sheets
```

### What each module owns

**types.py** — Pure enum definitions. No logic, no dependencies. Match the structure proposed in your Pass 2 plan but verify each enum's members are complete enough for the test cases.

**abilities.py** — `AbilityScores` frozen dataclass with `mod(ability) -> int`. Standard `(score - 10) // 2` math.

**proficiency.py** — Single function: `proficiency_bonus(rank: ProficiencyRank, level: int) -> int`. Returns 0 if untrained, else `rank.value + level`.

**equipment.py** — Frozen dataclasses for `Weapon`, `WeaponRunes`, `EquippedWeapon`, `Shield`, `ArmorData`. The `Weapon` dataclass must include traits as a `frozenset[str]`. `EquippedWeapon` wraps a `Weapon` with optional `WeaponRunes`. Helper properties on `Weapon`: `is_melee`, `is_ranged`, `is_finesse`, `is_agile`, `is_thrown`, `is_propulsive`.

**character.py** — `Character` (frozen) with all the fields from your Pass 2 plan. `CombatantState` (mutable) wraps a `Character` with transient combat state. Include the `from_character()` classmethod for clean construction.

**combat_math.py** — All derivation functions:
- `proficiency_bonus()` (re-export from proficiency.py, or just import in tests)
- `attack_ability(character, weapon) -> Ability`
- `damage_ability_mod(character, weapon) -> int`
- `weapon_spec_damage(character) -> int` (returns 0 at level 1, ramps later)
- `die_average(die: str) -> float`
- `attack_bonus(state, equipped, map_penalty=0) -> int`
- `damage_avg(state, equipped, extra_dice=0, extra_flat=0) -> float`
- `armor_class(state) -> int`
- `class_dc(character) -> int`
- `save_bonus(character, save) -> int`
- `perception_bonus(character) -> int`
- `map_penalty(attack_number, agile) -> int`
- `expected_strike_damage(...)` with d20 enumeration as in your Pass 2 plan
- `expected_aoe_damage(...)` with save d20 enumeration
- `siege_save_dc(operator) -> int` (alias for class_dc, but named for clarity)

**fixtures.py** — Factory functions that produce the four party characters at level 1 matching Section A.2 exactly. Used across all tests.

### What NOT to implement

- `pf2e/tactics.py` — design is mostly settled but the modifier vocabulary needs Pass 3 work
- `pf2e/conditions.py` — the flat-fields-on-CombatantState approach replaces this
- Anything in `sim/` — grid, scenario, evaluator, formatter all wait for Pass 3
- Any tactic execution logic
- Any turn planning logic
- Any output formatting

## Test requirements

Write `pytest` tests (Python stdlib `unittest` is also acceptable, but pytest is preferred for readability) that verify:

### test_abilities.py
- Mod calculation for scores 8, 10, 11, 14, 16, 18, 19, 20
- Indexing via Ability enum returns correct value

### test_proficiency.py
- `proficiency_bonus(UNTRAINED, level)` returns 0 for any level
- `proficiency_bonus(TRAINED, 1) == 3`, `(EXPERT, 1) == 5`, `(MASTER, 1) == 7`, `(LEGENDARY, 1) == 9`
- `proficiency_bonus(TRAINED, 5) == 7`, `(MASTER, 10) == 16`

### test_equipment.py
- Whip has finesse, reach, trip, disarm, nonlethal traits
- Longsword is martial, sword group, 1d8 slashing
- Steel Shield has +2 AC, Hardness 5, HP 20
- Full Plate has +6 AC, Dex cap 0, check penalty -3, Str threshold 18

### test_combat_math.py — the critical tests

For each character in fixtures.py, verify the exact numbers from A.3:
- Class DC = 17 for all four PCs
- AC values match A.3 (Aetregan 18, Rook 19, Dalai 16, Erisen 17)
- Save bonuses match A.3
- Rook longsword Strike vs AC 15: EV == 6.80 (within 0.01 tolerance)
- Aetregan whip Strike vs AC 15 (no Anthem): EV == 1.75 (within 0.01)
- Aetregan whip Strike vs AC 15 WITH Anthem: EV computed and explained
- Erisen mortar 2d6 vs single target Reflex +5, DC 17: EV == 5.60 (within 0.01)
- Erisen mortar vs 2 such targets: EV == 11.20

Also test:
- Off-guard reduces effective AC by 2 in EV calculation
- MAP penalty: 1st attack 0, 2nd attack -5, 3rd -10
- Agile MAP: 1st 0, 2nd -4, 3rd -8
- Reaction Strike (`is_reaction=True`) ignores MAP regardless of attack_number
- Frightened reduces attack_bonus and AC by frightened value, but NOT damage
- Nat 1 downgrades hit to miss, nat 20 upgrades miss to hit

### test_combat_math.py — the d20 enumeration helper

Document and test the d20 enumeration logic explicitly. For each (bonus, AC) pair, count the number of d20 faces that produce critical success / success / failure / critical failure, accounting for nat 1 downgrade and nat 20 upgrade. This is the foundation of every EV calculation; if it's wrong, every other test fails.

## Implementation guidance

### File order
Implement in this order to minimize churn:
1. `types.py` — pure enums
2. `proficiency.py` — pure function
3. `abilities.py` — small dataclass
4. `equipment.py` — dataclasses, no logic
5. `character.py` — Character + CombatantState dataclasses
6. `combat_math.py` — derivation functions (the heaviest module)
7. `fixtures.py` — factories
8. Tests as you go

### Coding standards

- Python 3.10+ syntax (use `|` for unions, `dict[K, V]` not `Dict`, etc.)
- All public functions get docstrings citing AoN URLs
- All dataclasses use `@dataclass(frozen=True)` unless they specifically need mutation (CombatantState only)
- Type hints everywhere
- No third-party deps (pytest is allowed for tests; that's it)
- Keep each function under ~30 lines; if longer, extract helpers

### Output organization

Place all source files under a top-level directory of your choosing (e.g., `pf2e_sim/`). Use a clear `README.md` at the top level explaining:
- How to run the tests (`pytest tests/`)
- The module structure
- That this is the foundation layer only; the simulator comes later

## Validation checklist before declaring done

- [ ] All listed modules exist and import without errors
- [ ] All four character fixtures match Section A.2 exactly
- [ ] All validation targets in Section A.3 pass as tests
- [ ] AoN URLs cited in docstrings for any non-trivial mechanic
- [ ] No code from `sim/` exists yet
- [ ] No tactic dispatcher exists yet
- [ ] Tests pass with `pytest tests/` from the project root
- [ ] README explains the layer split (foundation done, simulator pending)

If any validation target doesn't pass, do NOT silently change the target. Surface the discrepancy and explain what number you got and why. We'll resolve it together before moving to Pass 3.

---

# What Happens Next

After this implementation lands and tests pass:

1. **You demonstrate the foundation works** by running the test suite and showing the output.
2. **We do Pass 3 planning** for the tactic dispatcher and turn evaluator, which can now reference concrete code.
3. **You implement Pass 3** which builds on the foundation without changing it.
4. **We have a working simulator** that produces tactic rankings for arbitrary scenarios.

If during implementation you discover the foundation needs a field or function we didn't anticipate (e.g., something specific to how tactics will need to query character state), surface it as a question rather than silently adding it. Small additions are fine; structural changes need approval.
