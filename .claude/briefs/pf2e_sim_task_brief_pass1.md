# Task Brief: PF2e Tactical Combat Simulator — Architectural Refactor

## Context

This is a Python simulator that helps a Pathfinder 2e (Remaster) player evaluate Commander class tactic choices during combat encounters. The player is running a Commander in the *Outlaws of Alkenstar* adventure path and wants to optimize their per-turn decision-making by simulating expected damage outcomes across all tactic options for a given grid scenario.

A working prototype exists in this directory across four files:
- `characters.py` — character dataclasses with hardcoded stats
- `sim_engine.py` — map parsing, tactic logic, AoE math
- `run_sim.py` — orchestration and output formatting
- `my_scenario.py` — user-facing scenario definition

**The prototype works but the data model is poorly designed.** This refactor is about fixing the architectural foundations before adding more features.

## Your Task: First-Pass Architectural Planning

Do not write any code yet. Produce a high-level architectural plan that addresses the problems below and the goals that follow.

## Core Problem to Solve

The current `Strike` dataclass stores a pre-computed `attack_bonus` (e.g., `+7`) and `damage_avg` (e.g., `8.5`). This is wrong because:

1. **Attack bonuses derive from character ability scores, not from the weapon.** A Strike's accuracy comes from the *character* wielding it: their key ability mod (Str for most melee, Dex for finesse/ranged), their proficiency rank in the weapon's category (simple/martial/advanced/unarmed), their level, plus item bonuses (potency runes), plus situational modifiers (off-guard, MAP, frightened, etc.).

2. **Damage similarly derives from character + weapon + context.** Damage dice come from the weapon. Damage modifier comes from Str (melee, or thrown, or propulsive bows) — not Dex even when Dex is used for the attack roll. Weapon specialization (a class feature at level 7+) adds flat damage by proficiency tier. Striking runes add dice. Precision damage (sneak attack) and trait-based bonuses stack.

3. **Different characters use different ability scores for the same weapon.** Aetregan (Dex 16, Str 10) using a finesse weapon attacks with Dex but damages with Str. Rook (Str 18, Dex 10) wielding a longsword attacks AND damages with Str. Erisen (Dex, ranged) attacks with Dex on his ranged weapons. The current model can't express this — the bonuses are baked into the Strike instance.

4. **Saves, AC, perception, and class DC also have to derive properly.** Class DC = 10 + key ability mod + proficiency + level. Save bonuses = key save ability + proficiency + level + item bonuses. AC = 10 + Dex (capped by armor) + proficiency + item bonus. The current model has these as raw integers, which means they can't be recalculated when the character levels up or changes equipment.

## Goals

The refactored architecture should:

1. **Derive all combat numbers from underlying character data.** Ability scores, proficiency ranks, level, equipment, and conditions should be the source of truth. Attack rolls, damage rolls, save bonuses, AC, perception, and class DC should be computed from these inputs rather than stored as flat numbers.

2. **Support proper PF2e weapon mechanics:**
   - Finesse trait: use higher of Str or Dex for attack roll
   - Ranged weapons: use Dex for attack roll
   - Thrown weapons: use Dex for attack, Str for damage
   - Propulsive trait: add half Str mod to damage on ranged Strikes
   - Agile trait: -4/-8 MAP instead of -5/-10
   - Reach weapons: extended threatened range
   - Properly handle off-guard (-2 AC), frightened, sickened, etc.

3. **Support the Inventor mortar properly.** It's a siege weapon with its own action sequence (Deploy/Aim/Load/Launch), Reflex save DC (= Erisen's class DC), AoE shape (10-ft burst at level 1), and damage scaling (extra die at levels 5/9/13/17).

4. **Support Commander tactics as first-class entities** with their own metadata (action cost, range/aura requirement, prerequisites, target type) so new tactics can be added declaratively rather than as one-off Python functions. The current eight prepared tactics in this campaign are: Strike Hard!, Gather to Me!, Tactical Takedown, Defensive Retreat, Form Up, Reload, Coordinating Maneuvers, and Passage of Lines (player will eventually expand).

5. **Allow for level scaling.** The simulator should be able to evaluate scenarios at any character level by recomputing all derived stats. Don't hardcode "level 1" values anywhere.

6. **Allow swappable equipment.** Aetregan might switch from a whip (reach + trip) to a rapier (deadly d8) between encounters. Adding/removing potency runes, striking runes, and property runes should be easy.

7. **Keep the user-facing API simple.** The user edits a scenario file (grid + banner position + character level + maybe equipment overrides) and runs it. They should not need to compute attack bonuses by hand.

## Constraints

- **Python 3.10+ standard library only.** No third-party dependencies.
- **Maintain expected-value math for "best play" analysis** — don't switch to dice rolling. The current `expected_strike_damage` and `expected_aoe_damage` functions are correct in approach; refactor them to take the derived inputs cleanly.
- **Preserve the current tactic ranking output format** (or improve on it). The user wants to see ranked tactics with damage dealt / avoided / net value and brief justification per tactic.
- **The grid representation works fine** — parse_map and the ASCII map renderer don't need redesign. Focus the refactor on the character/weapon/combat-math layer.

## What "Architectural Plan" Means

Produce a written plan covering:

1. **Proposed module structure** — what files exist, what each owns, how they import from each other.

2. **Core data model** — the new dataclass hierarchy. At minimum I'd expect:
   - `Character` (ability scores, proficiencies, level, equipment, conditions)
   - `Weapon` / `WeaponInstance` (separates the weapon's intrinsic properties from a character-specific instance with runes)
   - `Strike` as an *action* that computes attack/damage at the moment of use, given a character + weapon + target + situation
   - Some representation of `Proficiency` rank (untrained, trained, expert, master, legendary) and how it maps to the +0/+2/+4/+6/+8 bonus
   - Conditions (off-guard, frightened, sickened, prone, hidden, etc.)
   - Tactics as data-driven entities

3. **Key derivation functions** — pseudocode or signatures for the most important "compute X from character + context" functions. Specifically:
   - How to compute attack bonus for a given Strike
   - How to compute damage for a given Strike
   - How to compute AC, saves, class DC, perception, skill bonuses
   - How to apply conditions to these derivations

4. **How tactics interact with the new model** — show how Strike Hard!, Gather to Me!, and Tactical Takedown would express themselves under the new architecture. Are tactics declarative dataclasses + a small executor, or still functions but cleaner?

5. **Migration path** — how do we get from the current four-file prototype to the new structure? What gets thrown away, what gets refactored, what gets kept?

6. **Open questions / decisions to make** — call out anything where there are multiple reasonable approaches and you want input before committing. Examples: do conditions live on the Character or in a separate ConditionSet? Are weapon traits enums or strings? Is the mortar a Weapon subclass or its own class entirely?

## What Not To Do

- Don't write code in this pass. Plans only.
- Don't add new features beyond what's described above (no AI improvements, no multi-round simulation, no GUI). Scope discipline matters.
- Don't redesign the grid/map system; it works.
- Don't propose a database, web service, or persistence layer; this is a single-player local CLI tool.
- Don't introduce dependencies (no `attrs`, no `pydantic`, no `numpy`).

## Output Format

Markdown document with sections matching the six items in "What 'Architectural Plan' Means" above. Use code blocks for dataclass sketches and function signatures. Aim for thorough but skimmable — this is a plan a human will review before approving.

When you're done, output the plan as a single document. Do not commit anything. Wait for review.
