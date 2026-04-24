# Checkpoint 4 Pass 1: Defensive Value Computation — Architectural Plan

## Context

Checkpoints 1–3 are complete (181 tests passing). The simulator can load scenarios, build tactic contexts, and compute offensive EV. The `expected_damage_avoided` field on `TacticResult` is always 0. Checkpoint 4 fills it in.

This is the architecturally novel checkpoint. Getting defensive mechanics right is foundational — every downstream turn evaluation (Checkpoint 5) depends on it. If we miscount even one mechanic, the simulator's advice will be wrong.

## Two Errors I Want to Correct from the Preview

In my Checkpoint 3 closeout, I listed defensive mechanics to address in Checkpoint 4 and made two factual errors:

1. **"Intercept Attack" is NOT a Commander reaction.** It's a Guardian class feature (Rook's, in this party). The Guardian class from Battlecry! has intercept-style reactions as a core identity mechanic. I mixed up "defensive reaction in this party" with "Commander-granted reaction."

2. **I omitted planted-banner temp HP entirely.** Aetregan has the "Plant Banner" feat per the Checkpoint 0 party build, and the Commander's banner ecosystem includes temp HP mechanics at various levels. I don't remember the exact mechanics off the top of my head, and that's exactly why this has to be researched rather than assumed.

The upshot: Pass 1 of Checkpoint 4 must verify the defensive mechanics inventory on AoN BEFORE architectural decisions. The inventory drives the architecture — not the other way around.

## Standing Rules (Extra Emphasis This Checkpoint)

1. **Verify rules against Archives of Nethys.** This is MANDATORY for Checkpoint 4. Every defensive mechanic we include must have a cited AoN URL. If a mechanic can't be verified, it's either flagged as UNVERIFIED (needs user input) or dropped from scope.
2. Cite AoN URLs in docstrings.
3. Read existing code first: `pf2e/tactics.py` (for TacticResult structure), `pf2e/equipment.py` (for Shield mechanics), `pf2e/character.py`, `sim/party.py` (for the exact builds of each party member).
4. **Surface discrepancies.** If AoN contradicts my brief or the existing character sheets, flag it in your plan. Do not silently paper over mismatches.
5. Don't expand scope. Defensive value computation only. No turn evaluator logic.
6. Describe test cases, don't write them.

## Your Task: Two-Phase Deliverable

Produce both phases in a single Pass 1 document. Phase A drives Phase B.

### Phase A: Defensive Mechanics Inventory (research deliverable)

Enumerate and verify every defensive mechanic available to this party at their current level (all party members level 1). For each mechanic, provide:

1. **Name and mechanical description** (verbatim or paraphrased — follow copyright rules)
2. **AoN URL** (direct link to the rule, feat, or class feature page)
3. **Who has access** (which party member, or all, or whoever has a shield, etc.)
4. **Type**: passive buff, active action, free action, reaction, or conditional trigger
5. **Action/reaction cost and trigger** (if applicable)
6. **Frequency** (at-will, once per round, once per day, etc.)
7. **What it prevents/reduces** (damage, hit probability, condition, etc.)
8. **What we need to compute it** (enemy attack profile? specific trigger state?)

Organize by party member, then by general rules available to anyone. At minimum, research the following. This list may not be complete — add anything you find during research.

#### Aetregan (Commander, level 1)

- **Banner class feature** — verify exact mechanics of the base Commander banner. Specifically: does it grant temp HP on plant? On allies entering the aura? Or is temp HP only from specific feats/features? What IS the base banner's defensive contribution?
- **Plant Banner feat** (if it exists at level 1) — verify its specific effects. Does it grant temp HP? Modify banner mechanics?
- **Drilled Reactions** — does this have any defensive component beyond granting reactions for tactics?
- **Tactics in folio with defensive value** — Gather to Me!, Defensive Retreat (both already in dispatcher as placeholders). Plus any other prepared tactic.
- **Disciple of the Gear background** — any defensive feature?
- **Ancient Elf ancestry** — any defensive feature (besides the free dedication)?
- **Other level 1 class features or feats**
- Fetch: https://2e.aonprd.com/Classes.aspx (find Commander) and related pages

#### Rook (Automaton, Guardian, level 1)

- **Intercept Strike / Intercept Attack** (whatever the exact name is) — verify the exact mechanics. Trigger? Range? What does it actually do (swap positions, redirect the attack, take damage for the ally)?
- **Guardian's Armor / armor proficiency** — any defensive features unique to this class?
- **Raise Shield** (+2 AC while raised) — general action, confirm for Rook specifically
- **Shield Block** (reaction on hit to reduce damage by Hardness 5 with steel shield) — confirm, and note Hardness/HP values
- **Unshakable / Tough Guy / other level 1 Guardian features** — research class page thoroughly
- **Automaton ancestry defensive features** (e.g., Automaton's Electrical Resistance? Reclaim Soul? etc.)
- Fetch: https://2e.aonprd.com/Classes.aspx (find Guardian) and https://2e.aonprd.com/Ancestries.aspx?ID=48 (Automaton)

#### Dalai (Bard, Warrior Muse, Shelyn, level 1)

- **Courageous Anthem** — purely offensive (+1 to attack/damage) or defensive components too? Verify against https://2e.aonprd.com/Spells.aspx?ID=1763
- **Other composition spells available at level 1** — Inspire Defense? (confirm availability at level 1 or higher)
- **Warrior Muse features**
- **Shelyn-specific features** (if deity grants anything)
- Human ancestry feats
- Fetch: https://2e.aonprd.com/Classes.aspx (find Bard)

#### Erisen (Elf, Inventor Munitions Master, level 1)

- Probably mostly offensive but verify: any level 1 defensive Inventor features?
- Elf ancestry defensive features
- Nimble Elf feat (movement, likely no defensive component but verify)

#### Party-independent PF2e mechanics

- **Raise Shield** — general action, anyone with a shield. Aetregan has a steel shield too (from the party build). Does he raise it?
- **Shield Block** — general reaction, anyone with a shield. Who has one on this party?
- **Tumble Through** — movement action to avoid reactive strikes (offensive more than defensive but relevant)
- **Cover rules** — +1 AC lesser cover, +2 AC standard cover, etc. (AoN: https://2e.aonprd.com/Rules.aspx — find Cover)
- **Taking cover behind a creature** — is this a thing in PF2e? Research.

Present your findings as a structured inventory. Mark each entry: "IN SCOPE" (Checkpoint 4 will model it), "OUT OF SCOPE FOR C4" (deferred to C5+), or "UNVERIFIED" (need user input).

### Phase B: Architectural Plan

After the inventory, design the defensive value computation layer. Cover the following:

#### 1. Enemy attack profile modeling

To compute "damage prevented," we need to estimate what damage enemies *would deal* if the defensive action didn't happen. This means enriching `EnemyState` with offensive stats.

Decide:

- **What fields to add to EnemyState**: attack bonus, damage dice (string like "1d8+3" or structured), crit range (usually nat 20 but some enemies have enhanced crits), MAP sequence, any special attack effects (trip, grab, etc.)?
- **How many attacks per enemy turn?** Most martial enemies have 2-3 Strikes. Some spellcasters have 1. Do we model all of them, or just the "expected damage per attack" averaged over a standard 3-action turn?
- **How to choose targets?** "Nearest reachable PC" is a reasonable heuristic. Preference for squishy targets (low HP, low AC)? For Checkpoint 4, keep target selection simple; flag smarter AI as future work.
- **How to update the scenario file format** to include enemy offensive stats? Extend the `[enemies]` line format? New section?

Propose concrete field additions and parser extensions.

#### 2. Expected incoming damage calculation

A primitive function that computes expected damage from an enemy's attack against a specific target, accounting for:

- Attacker's attack bonus vs. target's AC (via `enumerate_d20_outcomes`)
- Damage dice average
- Target conditions (off-guard gives +2 attack to attacker → higher EV)
- Target's shield (raised? shield block reaction available?)

Sketch the signature:

```python
def expected_incoming_damage(
    attacker: EnemyState,
    target: CombatantState,
    ...
) -> float:
    ...
```

This is the load-bearing primitive for the entire defensive layer.

#### 3. Shield Block and Raise Shield

For combatants with shields:

- **Raise Shield**: +2 circumstance bonus to AC while raised (spends 1 action, lasts until next turn). 
- **Shield Block**: reaction triggered when hit by a physical attack, reduces damage by Hardness. If damage exceeds Hardness + Shield HP, shield breaks.

Design:

- How to represent "shield is currently raised" on CombatantState (might already exist — check)
- How to compute EV benefit of raising the shield (reduced hit probability × prevented damage)
- How to compute EV benefit of using Shield Block reaction (prevented damage per triggered attack)
- Whether raised shield affects `expected_incoming_damage` by modifying the target's AC

#### 4. Guardian Intercept mechanics (Rook-specific)

Whatever the verified Intercept feature is (Phase A), model its EV contribution:

- When does Rook use it? (e.g., Dalai being crit, Erisen being targeted by high-damage attack)
- What's the damage trade (Rook takes damage instead of the targeted ally, possibly reduced by his own defenses)?
- Action cost (reaction)

Design the evaluation function that decides "is intercepting this attack worth it?" 

#### 5. Banner-related defensive mechanics

Depending on Phase A verification:

- Base banner aura effect (whatever it is)
- Plant Banner feat effect (whatever it is, if it grants temp HP or anything else)
- How temp HP from planting propagates to squadmates in aura

If temp HP exists, this changes how Gather to Me! is evaluated — pulling squadmates into aura is now worth real EV (temp HP × hit probability × some factor).

#### 6. Gather to Me! defensive evaluation

The placeholder from Checkpoint 1 currently returns `expected_damage_avoided = 0`. Checkpoint 4 fills it in:

- If a squadmate Strides INTO the aura (and banner gives temp HP), that's +temp HP worth of EV
- If a squadmate Strides OUT of an enemy's reach, that's prevented damage EV
- Combine both contributions per squadmate, aggregate across all squadmates

Sketch the computation. Handle edge cases: squadmate already in aura (no new temp HP), squadmate not in reach of any enemy (no damage to prevent).

#### 7. Defensive Retreat evaluation

Similar but different: allies get 3 free Steps away from enemies.

- Each Step moves 5 ft
- Must move away from at least one observed hostile
- Up to 3 Steps per squadmate
- No reactions consumed

If the resulting position is out of the enemy's reach, that's prevented damage. Compute per-squadmate EV, aggregate.

Flag: does Defensive Retreat move break Strides somehow (e.g., can the squadmate then reach a better position)? Keep the model simple for Checkpoint 4.

#### 8. AoE friendly-fire (Erisen's mortar)

If Erisen fires a mortar burst, any squadmate in the burst area takes (probable) damage. This is negative EV for an offensive tactic.

Design:

- How to extend the offensive tactic evaluators to check friendly-fire
- Is this a Checkpoint 4 concern, or does it belong in Checkpoint 5 (turn evaluator)? Recommend.
- If in scope: enrich the mortar's damage profile to compute expected damage to each ally in the burst

Frankly, this might be deferrable to Checkpoint 5 since it involves Erisen's action selection rather than pure defensive reaction. Propose a recommendation.

#### 9. Courageous Anthem defensive contribution (if any)

Phase A verification will confirm whether Anthem has defensive components. If yes, model them.

#### 10. TacticResult field changes

`expected_damage_avoided` already exists. Do we need additional fields for reporting? E.g., `damage_prevented_sources: dict[str, float]` mapping mechanism name ("Gather to Me aura entry", "Shield Block", "Intercept") to EV contribution. This helps users understand WHY a tactic is valued highly.

Propose field changes if needed.

#### 11. Integration tests

Describe 3-5 integration tests that prove defensive value computation works end-to-end. At minimum:

- A scenario where Gather to Me has clear positive defensive value (squadmates leaving enemy reach, gaining temp HP)
- A scenario where Intercept has positive value (Dalai being critically hit, Rook intercepts)
- A scenario where Shield Block has positive value (Rook with shield raised vs. heavy hitter)
- A regression test: the existing Strike Hard killer scenario still produces EV 8.55 on `expected_damage_dealt` (no regression from the new fields)

#### 12. Module structure

Where does this code live? New module `sim/defense.py`? Extend `pf2e/combat_math.py`? Extend `pf2e/tactics.py`? Recommend and justify.

## Open Questions for Pass 2

List decisions where you want my input. Examples I'd expect:

- Scope of enemy behavior modeling (simple "attacks nearest" vs. something smarter)
- Whether AoE friendly-fire is Checkpoint 4 or Checkpoint 5
- Whether to model every defensive mechanic or prioritize the high-value ones
- How to handle reactions that compete (e.g., Rook only has one reaction — if he could Shield Block OR Intercept, which does he do?)

## Output Format

Produce a single markdown document with:

- **Phase A: Defensive Mechanics Inventory** — structured by party member, each entry with all the fields listed above, AoN URLs, and IN SCOPE / OUT OF SCOPE / UNVERIFIED marking
- **Phase B: Architectural Plan** — sections 1–12 as described above

Phase A is research; Phase B is design. If Phase A surfaces a mechanic I didn't mention that has significant defensive value, Phase B must accommodate it.

Cite AoN URLs for every mechanical claim. Mark anything you can't verify as `(UNVERIFIED — user input needed)`.

When done, output the plan as a single document and wait for review.

## What Comes After

1. You produce this Pass 1 plan (both phases).
2. I review — the Phase A inventory especially. I'll confirm the research before engaging with architecture.
3. I write Pass 2 corrections.
4. You produce Pass 2 refined plan.
5. I write Pass 3 implementation brief.
6. You implement.
7. We close Checkpoint 4 and move to Checkpoint 5: turn evaluator with best-3-action enumeration.

This checkpoint has more rules-research surface area than any previous checkpoint. Budget time accordingly. Verification quality matters more than speed here.
