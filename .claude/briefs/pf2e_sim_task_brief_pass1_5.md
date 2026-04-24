# Task Brief Pass 1.5: PF2e Simulator — Rules Corrections & Missed Mechanics

## Context

This is a follow-up to your first-pass architectural plan for the PF2e Tactical Combat Simulator. Your plan's overall structure (`pf2e/` package + `sim/` package, derivation functions, data-driven tactics, Weapon/EquippedWeapon split) is **approved** and we'll build on it.

However, audit against [Archives of Nethys](https://2e.aonprd.com/) revealed several rules errors and missed mechanics that must be corrected before you produce the refined plan in Pass 2. The plan also missed some class features that materially affect tactic evaluation.

**Read the prototype files in this directory before doing anything else.** The four files are `characters.py`, `sim_engine.py`, `run_sim.py`, and `my_scenario.py`. They contain working baseline numbers your refined plan must be able to reproduce. If any file is missing, stop and tell the user before proceeding.

## Hard Requirement: Cite Sources

For every mechanical claim in your refined plan, cite the Archives of Nethys URL. Format: `(AoN: https://2e.aonprd.com/...)`. This makes our review pass much faster. If you cannot find a citation for a mechanic, mark it as `(UNVERIFIED)` and we'll check it together.

---

## Part A: Rules Corrections to the Pass-1 Plan

### A.1 Strike Hard! is 2 actions, not 1

**Source:** https://2e.aonprd.com/Tactics.aspx?ID=13

> Strike Hard! [two-actions] Offensive Brandish Commander Tactic. You command an ally to attack. Signal a squadmate within the aura of your commander's banner. That ally immediately attempts a Strike as a reaction.

**Correction:** Strike Hard's `action_cost` field must be `2`, not `1`. The plan currently shows it as 1 action.

**Also:** Strike Hard does **not** add a damage die, accuracy bonus, or any other modifier. The Pass-1 plan's `modifiers={"bonus_damage_dice": 1}` is wrong. The benefit is purely "ally gets a reaction Strike outside their turn (so MAP 0)." Replace the modifiers dict with empty/just `{}` for this tactic.

### A.2 Tactical Takedown is 2 actions, and its mechanic is repositioning + prone, not "Strike with off-guard"

**Source:** https://2e.aonprd.com/Tactics.aspx?ID=14

> Tactical Takedown [two-actions] Offensive Commander Tactic. You direct a coordinated maneuver that sends an enemy tumbling down. Signal up to two squadmates within the aura of your commander's banner. Each of those allies can Stride up to half their Speed as a reaction. If they both end this movement adjacent to an enemy, that enemy must succeed at a Reflex save against your class DC or fall prone.

**Correction:** Pass-1 plan said `target_type="one_ally"` and `granted_action="strike"` with off-guard modifier. All wrong. Correct fields:
- `action_cost`: 2
- `target_type`: "two_squadmates"
- `granted_action`: "stride_half_speed"
- `prerequisites`: ["two_squadmates_in_aura", "shared_enemy_reachable_by_both"]
- Effect: enemy makes Reflex save vs commander class DC; on failure → prone (which gives off-guard + -2 attack penalty + costs an action to Stand)

The value of Tactical Takedown comes from imposing **prone** on an enemy (which then helps subsequent attacks), not from any direct damage in the tactic itself.

### A.3 Gather to Me does NOT grant temp HP

**Source:** https://2e.aonprd.com/Tactics.aspx?ID=2

> Gather to Me! [one-action] Mobility. You signal your team to move into position together. Signal all squadmates; each can immediately Stride as a reaction, though each must end their movement inside your banner's aura, or as close to your banner's aura as their movement Speed allows.

**Correction:** Pass-1 plan had `modifiers={"grant_temp_hp": True, "temp_hp_formula": "level"}`. This is **wrong** — that's confusing Gather to Me with **Plant Banner** (a separate Commander class feat).

Plant Banner reference (https://2e.aonprd.com/Feats.aspx?ID=7891 if it works, or search "Plant Banner Commander"):
> Plant Banner [one-action] Commander Manipulate. ... All allies within a 30-foot burst immediately gain a number of temporary Hit Points equal to half your Intelligence modifier.

Gather to Me has no temp HP. Its only effect is the reaction Stride. Remove the temp HP modifier.

### A.4 Off-guard handling: simpler than the Pass-1 plan suggested

**Source:** https://2e.aonprd.com/Conditions.aspx?ID=58

> Off-Guard. You're distracted or otherwise unable to focus your full attention on defense. You take a –2 circumstance penalty to AC.

**Correction:** Off-guard is a flat -2 circumstance penalty to AC. For our simulator's expected-value math, treat this as `effective_ac = target_ac - 2` when the attacker has any source of off-guard against the target. The plan's circumstance/penalty type tracking can be skipped — we don't need to model penalty stacking rules because we're doing per-attack EV.

**Implementation guidance:** A simple `bool off_guard_to_attacker` parameter on `expected_strike_damage()` is sufficient. Don't build a Condition system that tries to track penalty types and stacking — it's over-engineered for our use case.

### A.5 Commander key ability is Intelligence

**Source:** https://2e.aonprd.com/Classes.aspx?ID=66

> Key Attribute: INTELLIGENCE

**Correction:** Pass-1 plan comment said "CHA for Commander, INT for Inventor". Both Commander and Inventor are INT-key classes. Update the docstring/comment.

### A.6 Damage ability returns a flat int, not a (Ability, multiplier) tuple

**Source:** https://2e.aonprd.com/Rules.aspx?ID=2189

> Melee damage roll = damage die of weapon or unarmed attack + Strength modifier + bonuses + penalties
> Ranged damage roll = damage die of weapon (+ Strength modifier for a thrown weapon or half Strength modifier for a propulsive weapon) + bonuses + penalties

**Correction:** Pass-1 plan's `damage_ability()` returned `(Ability, multiplier)` which conflates two questions. Cleaner:

```python
def damage_ability_mod(character: Character, weapon: Weapon) -> int:
    """Returns the integer damage bonus from ability scores."""
    str_mod = character.abilities.mod(Ability.STR)
    if weapon.is_melee:
        return str_mod
    if "thrown" in weapon.traits:
        return str_mod
    if "propulsive" in weapon.traits:
        # Half Str rounded down if positive, full Str if negative
        return str_mod // 2 if str_mod >= 0 else str_mod
    return 0  # Pure ranged: no ability mod
```

This is the cleanest expression and maps directly to the rule.

---

## Part B: Mechanics Missed by the Pass-1 Plan

These are class features and rules interactions that the simulator must support but weren't in the original plan. Add them.

### B.1 Multiple Attack Penalty does not apply to reactions

**Source:** https://2e.aonprd.com/Rules.aspx?ID=220

> If you use an action with the attack trait more than once on the same turn, your attacks after the first take a penalty called a multiple attack penalty. ... The multiple attack penalty doesn't apply to attacks you make when it isn't your turn (such as attacks made as part of a reaction).

**Implementation:** When evaluating a reaction Strike (granted by Strike Hard, Tactical Takedown's prone setup follow-ups, etc.), the MAP for that Strike is **always 0**, regardless of how many attacks the ally already made on their own turn.

This is a HUGE source of value for Commander tactics — they let allies attack a 4th time per round at full accuracy. The simulator must reflect this advantage.

### B.2 Drilled Reactions (Commander level 1 class feature)

**Source:** https://2e.aonprd.com/Classes.aspx?ID=66 — Drilled Reactions section

> Once per round when you use a tactic, you can grant one ally of your choice benefiting from that tactic an extra reaction. This reaction has to be used for that tactic and is lost if not used.

**Implementation:** Per-round, the commander can pick one ally to receive a "tactic-reserved" extra reaction. Combined with B.1, this means even if an ally has already used their normal reaction (e.g., Shield Block on a previous enemy turn), they can still respond to the Commander's tactic later in the round.

For the simulator: each character has a `reactions_remaining` counter that resets to `1 + bonus_reactions` at start of round. Drilled Reactions adds 1 to one chosen ally per round, restricted to use for the triggering tactic.

### B.3 Reactions per round — every character has 1, Guardians have 2

**Source:** https://2e.aonprd.com/Rules.aspx?ID=2432 (general rule)

> You gain 1 reaction per round.

**Source:** https://2e.aonprd.com/Classes.aspx?ID=67 (Guardian Techniques)

> You always gain a reaction whenever you roll initiative for combat, but you can use it only for reactions from guardian feats or class features.

Plus: at level 7 Guardians get **Reaction Time** which adds a second guardian-only reaction per turn.

**Implementation:** `Character` needs a `bonus_reactions: dict[str, int]` field where the key is the restriction (e.g., "guardian", "tactic-only") and the value is the count. The reaction-tracking logic checks both general and restricted reaction pools when consuming.

### B.4 Bard Composition Cantrip: Courageous Anthem is almost always active

**Source:** https://2e.aonprd.com/Spells.aspx?ID=1763

> Courageous Anthem [one-action] Cantrip. 60-foot emanation. Duration 1 round. You inspire yourself and your allies with words or tunes of encouragement. You and all allies in the area gain a +1 status bonus to attack rolls, damage rolls, and saves against fear effects.

**Implementation:** Dalai will cast Courageous Anthem as 1 of his 3 actions almost every turn from round 1 onward. The simulator should model this as a **scenario assumption**:
- All party members within 60 ft of Dalai gain `+1 status to attack rolls` and `+1 status to damage` while Courageous Anthem is active.
- Default the simulator to "Courageous Anthem is active starting round 2" (round 1 might not have it cast yet depending on initiative).
- Provide a scenario flag to disable this if the user wants to test without it.

This is critical because every party member's expected damage shifts up by ~1 per Strike when Anthem is active. Ignoring it will undervalue every offensive tactic.

**Constraint:** Only one composition active at a time, only one cast per turn (https://2e.aonprd.com/Classes.aspx?ID=32). So Dalai can't have both Courageous Anthem AND Hymn of Healing running.

### B.5 Bard Composition Spell: Hymn of Healing (Dalai's class feat)

**Source:** https://2e.aonprd.com/Spells.aspx?ID=728

> Hymn of Healing [two-actions] verbal. Range 30 feet; Targets you or 1 ally. Duration sustained up to 4 rounds. Your divine singing mends wounds and provides a temporary respite from harm. The target gains fast healing 2. When you Cast the Spell and the first time each round you Sustain the Spell, the target gains 2 temporary Hit Points, which last for 1 round.

**Implementation:** When evaluating "damage taken by party" in defensive tactic comparisons, account for Hymn of Healing if Dalai is sustaining it on a target. fast healing 2 + 2 temp HP per round on one ally is meaningful damage prevention.

### B.6 Guardian features (Rook)

**Source:** https://2e.aonprd.com/Classes.aspx?ID=67

**Taunt** (level 1 base feature):
> Taunt [one-action] Concentrate Guardian. Choose an enemy within 30 feet to be your taunted enemy. If your taunted enemy takes a hostile action that includes at least one of your allies but doesn't include you, they take a –1 circumstance penalty to their attack rolls and DCs for that action, and they also become off-guard until the start of their next turn.

**Intercept Attack** (level 1 base feature, uses guardian-only reaction):
> Trigger An ally within 10 feet of you takes physical damage. You fling yourself in the way of oncoming harm to protect an ally. You can Step, but you must end your movement adjacent to the triggering ally. [Then take the damage in the ally's place.]

**Defensive Advance** (Rook's level 1 class feat per his sheet):
> Source: https://2e.aonprd.com/Feats.aspx?ID=5882
> Defensive Advance [two-actions] Champion Flourish Guardian. With the protection of your shield, you dive into battle! You Raise your Shield and Stride. If you end your movement within melee reach of at least one enemy, you can make a melee Strike against that enemy.

**Implementation:** All three are actions Rook may take during scenario evaluation. Defensive Advance is action-economy compression worth modeling: in 2 actions Rook gets shield AC + movement + Strike, where doing them separately would cost 3 actions.

Intercept Attack uses Rook's bonus guardian-only reaction. The simulator should include it as a `damage_avoided` mechanism when an ally within 10 ft is about to take physical damage.

### B.7 Inventor mortar action sequence and class DC

**Source:** https://2e.aonprd.com/Innovations.aspx?ID=4

> Aim [one-action] unlimited, minimum distance 10 feet
> Load [one-action] (manipulate) 1 time
> Launch [one-action] (attack, manipulate, range increment 120 feet) 2d6 bludgeoning, 10-foot burst, DC 15 basic Reflex

The DC 15 listed is the base item DC. **For an Inventor wielding their innovation**, the save DC equals the **Inventor's class DC** (10 + Int + proficiency + level), not the item's base 15. At level 1 with Int 18 and trained: DC 17.

**Implementation:** `siege_save_dc(operator: Character) -> int` returns the class DC of the operator. The mortar's listed DC 15 is overridden by the operator's class DC.

Mortar damage scaling: https://2e.aonprd.com/Innovations.aspx?ID=4 — "It deals an additional die of damage at 5th level and every 4 levels thereafter." So 2d6 → 3d6 (level 5) → 4d6 (level 9) → 5d6 (level 13) → 6d6 (level 17).

### B.8 Steel Shield mechanics

**Source:** https://2e.aonprd.com/Shields.aspx?ID=3

> Steel Shield. AC Bonus +2; Speed Penalty —; Bulk 1; Hardness 5; HP (BT) 20 (10).

**Source:** https://2e.aonprd.com/Rules.aspx?ID=2180 (Shields rules)

> A shield grants a circumstance bonus to AC, but only when the shield is raised. This requires using the Raise a Shield action. ... If you have access to the Shield Block reaction (from your class or from a feat), you can use it while Raising your Shield to reduce the damage you take by an amount equal to the shield's Hardness. Both you and the shield then take any remaining damage.

**Implementation:** Add a `Shield` dataclass:
```python
@dataclass(frozen=True)
class Shield:
    name: str
    ac_bonus: int
    hardness: int
    hp: int
    speed_penalty: int = 0
```

Character has optional `shield: Shield | None`. AC computation adds the shield bonus IF `shield_raised` is true (track as transient combatant state).

Shield Block reaction reduces incoming damage by `hardness` when shield is raised. Aetregan and Rook both have Steel Shields (per their character sheets) and Shield Block.

**Shields Up! tactic** (https://2e.aonprd.com/Tactics.aspx?ID=12):
> Shields Up! [one-action] Offensive. Signal all squadmates within the aura of your commander's banner; each can immediately Raise a Shield as a reaction.

This becomes a defensive tactic option in the simulator. Value = +2 AC for each squadmate with a shield until their next turn.

### B.9 Shield Block (Aetregan and Rook both have this)

**Source:** https://2e.aonprd.com/Feats.aspx?ID=4823 (Shield Block general feat)

> Shield Block [reaction] General. Trigger While you have your shield raised, you would take damage from a physical attack. ... You snap your shield in place to ward off a blow. Your shield prevents you from taking an amount of damage up to the shield's Hardness; you and the shield each take any remaining damage, possibly breaking or destroying the shield.

**Implementation:** Combine with Shield: when a character with a raised shield + Shield Block reaction available + reaction available takes physical damage, reduce damage by shield's hardness (5 for steel). Costs 1 reaction.

---

## Part C: Architectural Decisions Needed in Light of B

These are the design questions you need to answer in Pass 2 because the new mechanics expose them.

### C.1 Action cost and reaction tracking are first-class concerns now

The Pass-1 plan treated action cost as a `int` field on `TacticDefinition`. That's still right, but the **value of a tactic** must now be evaluated against "what can the commander still do with the remaining actions?" 

For example:
- Strike Hard! costs 2 of 3 actions. Commander has 1 action left for Stride/Plant Banner/etc.
- Gather to Me! costs 1 action. Commander has 2 actions left for Strike + Stride / Two-tactic combo / etc.

A tactic's net value should consider both the tactic's effect AND the opportunity cost of the actions consumed.

**Decide:** Does the simulator evaluate each tactic in isolation (current Pass-1 design) or does it evaluate "best 3-action turn" as a search over (tactic, supplementary actions) combinations?

Recommended: **evaluate best 3-action turn**. Most useful for the user. But add the complexity carefully — it's tractable because there are only ~5-10 supplementary actions worth considering (Strike with own weapon, Stride to reposition, Raise Shield, Plant Banner, second tactic, Sustain a spell).

### C.2 Reaction tracking needs per-combatant state

Each combatant needs:
- `reactions_remaining: int` (default 1, refreshed at start of round)
- `bonus_reactions: dict[str, int]` for restricted reactions (e.g., {"guardian": 1} for Rook)
- `tactic_reaction_grant: TacticName | None` for Drilled Reactions

When a tactic grants an ally a reaction Strike: check if the ally has `reactions_remaining > 0` OR has the Drilled Reactions grant for this tactic. If neither, the tactic doesn't get its full effect.

**Decide:** Does this state live on the `Character` (mutable) or on a separate `CombatantState` wrapper?

Recommendation: separate `CombatantState` wrapper that pairs a `Character` with transient combat state (reactions, conditions, shield raised, position, current HP). Character stays immutable.

### C.3 Composition cantrip handling

Courageous Anthem is functionally a passive party-wide buff that's active most rounds. Two ways to handle:

**Option A:** Scenario-level flag `courageous_anthem_active: bool` that adds +1 status bonus to attack/damage for everyone in the emanation. Simple but doesn't simulate the action cost Dalai pays each turn.

**Option B:** Bard turn explicitly modeled with action choice "cast Courageous Anthem" or "don't". More accurate but requires modeling Dalai's full turn.

Recommendation: **Option A for now** with a comment that this is a simplification. Add Option B in a future iteration if needed.

### C.4 Should Hymn of Healing be in scope?

It's a 2-action focus spell that Dalai might cast instead of Anthem. It changes whether allies get the +1 attack/damage from Anthem.

**Decide:** Model both compositions and let Dalai's "play" be a strategic input, OR fix Anthem as default and treat Hymn as an opt-in scenario configuration.

Recommendation: **fix Anthem as default**, add scenario flag `bard_composition: "anthem" | "hymn" | None`. User can override per scenario if testing a defensive setup.

### C.5 Plant Banner mechanics need their own representation

Plant Banner isn't a tactic — it's a Commander class feat that creates a banner location. The current Pass-1 plan has banner_pos as a tuple but doesn't distinguish "carried banner" vs "planted banner with temp HP aura."

**Decide:** Is the banner state part of the scenario (planted at position X) or part of the commander's per-round actions (this round, did the commander plant the banner)?

Recommendation: scenario-level flag `banner_state: "carried" | "planted_at_<pos>"`. Default to planted at the location user specified. If user wants to model the cost of planting, they specify "carried" and the simulator can evaluate "should the commander plant it this round."

### C.6 Reaction Strike value is now much higher than the Pass-1 plan implied

Because reactions don't carry MAP, a tactic-granted Strike from an ally is **always at MAP 0** even if it's their 4th attack of the round (3 from their own turn + 1 from the tactic). At level 1 with no MAP penalty, this is a meaningful damage swing.

The simulator should clearly show this in the justification text: "Strike Hard grants Rook a 4th attack at MAP 0 (avoiding the -10 he'd normally face for a 3rd attack)."

---

## Part D: What to Verify Against the Prototype

Before submitting the Pass 2 plan, **read the four prototype files** and confirm:

1. Your refined data model can express every character in `characters.py` (Aetregan, Rook, Dalai, Erisen, Minion, Brute) using the new dataclasses without losing information.

2. Your refined model produces the same numbers the prototype produces for these specific cases at level 1:
   - Rook longsword Strike vs AC 15: ~6.8 EV
   - Aetregan whip Strike vs AC 15: low (~2-3 EV — confirm)
   - Mortar at center of 2 minions, both fail save: ~5.6 EV per minion = ~11.2 total
   - Rook AC = 18 (heavy armor + Dex cap, etc. — show the derivation)
   - Erisen mortar save DC = 17

3. Your refined tactic dispatcher produces the same ranking for the original scenario in `my_scenario.py` (Gather to Me wins at +17.3 net value, Strike Hard → Rook at second).

If any of these numbers don't reproduce, flag the discrepancy and explain whether it's because the prototype was wrong or your new model differs.

---

## Output Format

Produce a single markdown document with these sections:

1. **Corrections applied** — confirm each item in Part A is reflected in the refined design
2. **New mechanics integrated** — show how each item in Part B is represented in the data model
3. **Architectural decisions made** — answer each open question in Part C with rationale
4. **Refined data model** — full dataclass sketches for any structures that changed since Pass 1
5. **Refined tactic registry** — show all 8 tactics from the user's Commander folio with corrected `action_cost`, `target_type`, `granted_action`, and modifier fields. The 8 tactics are: Strike Hard!, Gather to Me!, Tactical Takedown, Defensive Retreat, Shields Up!, Reload!, Coordinating Maneuvers (verify name on AoN), Form Up (verify name on AoN). Cite each tactic's AoN URL.
6. **Validation against prototype** — confirm Part D check items pass, or flag discrepancies
7. **Open questions for Pass 3** — anything that emerged during Pass 2 we should resolve before code generation

Cite Archives of Nethys URLs for every mechanical claim. Mark anything you can't verify as `(UNVERIFIED — please check)`.

## What Not to Do

- Don't write code yet. Plans only.
- Don't add features beyond what's in this brief. The simulator scope is unchanged: rank single-round tactic options by net value with proper PF2e math.
- Don't propose a condition-stacking system. A flat `off_guard` boolean and `frightened: int` value field on combatant state is enough.
- Don't redesign anything that worked in Pass 1 — only modify what's called out here.

When you're done, output the plan as a single document. Wait for review before any code is written.
