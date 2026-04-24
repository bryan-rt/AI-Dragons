# Checkpoint 1 Pass 2: Corrections and Clarifications

## Context

Your Pass 1 architectural plan is strong. The data model, dispatcher design, mocking strategy, and integration points are all approved as-is. This Pass 2 brief addresses a small number of specific issues before we move to Pass 3 (implementation).

**Do NOT rewrite the whole plan.** Apply the corrections below and output a compact updated plan that reflects them. Unchanged sections can be summarized as "unchanged from Pass 1."

**Standing rules apply** (verify against AoN, cite URLs, surface discrepancies, don't expand scope, read existing code before changing it).

---

## Corrections to Apply

### C.1 Fetch Defensive Retreat and Mountaineering Training URLs from AoN

Pass 1 marked these as UNVERIFIED without fully resolving them. Go back to AoN and resolve both:

1. **Fetch the Tactics index page**: https://2e.aonprd.com/Tactics.aspx
   - This page lists all Commander tactics in one place with names, action costs, traits, and IDs. From this, you can identify the exact IDs for Defensive Retreat and Mountaineering Training.

2. **For Defensive Retreat**, confirm:
   - Exact AoN URL (https://2e.aonprd.com/Tactics.aspx?ID=N where N is the specific ID)
   - Action cost (likely 2 actions based on earlier research)
   - Exact mechanical text (verbatim quote)

3. **For Mountaineering Training**, confirm:
   - Exact AoN URL (likely ID=3 but verify)
   - Action cost (you speculated 1 action; confirm from the page)
   - Exact mechanical text (verbatim quote)

If the Tactics index page doesn't have enough detail, fetch each tactic's individual page. Update the registry entries in Section 2 with verified data. Remove UNVERIFIED tags once confirmed.

### C.2 Fix the Prone condition URL

Pass 1 cited `https://2e.aonprd.com/Conditions.aspx?ID=31` as UNVERIFIED. The correct URL is:

**https://2e.aonprd.com/Conditions.aspx?ID=88**

Verified text: "You're lying on the ground. You are off-guard and take a –2 circumstance penalty to attack rolls. The only move actions you can use while you're prone are Crawl and Stand. Standing up ends the prone condition."

Update the Tactical Takedown evaluator docstring with the correct URL. Remove the UNVERIFIED tag.

### C.3 Confirm Tactical Takedown crit-fail behavior

Pass 1 marked this as UNVERIFIED: "check if there's a crit fail effect beyond normal prone."

Re-read the tactic text: "that enemy must succeed at a Reflex save against your class DC or fall prone."

PF2e's standard save convention (https://2e.aonprd.com/Rules.aspx?ID=2195) treats crit failure the same as failure unless the effect explicitly specifies a worse outcome. Tactical Takedown does not. Therefore: **crit fail = fail = prone**. No enhanced effect on crit fail.

Verify this interpretation against AoN's general save rules and update the evaluator's treatment. For EV computation purposes, prone probability = (failure + crit_failure) / 20.

### C.4 Fix the 60% / 55% inconsistency in Section 6.3

Pass 1's Section 6.3 has two different numbers for the Tactical Takedown prone probability against a Reflex +5 target vs DC 17:

- Justification example: "60% chance prone"
- Mid-paragraph verification: "fail+crit fail = 11/20 = 55%"

55% is correct. With save +5 vs DC 17:
- Crit fail: rolls 1 and 2 (totals 6 and 7, both ≤ DC−10 = 7) → 2 faces
- Fail: rolls 3–11 (totals 8–16, all < DC 17) → 9 faces
- Success: rolls 12–19 (totals 17–24) → 8 faces
- Crit success: roll 20 upgraded from success → 1 face
- Total prone = (2 + 9) / 20 = 11/20 = **55%**

Update the example justification text to use 55%. Match it to the d20 enumeration your code will actually compute.

### C.5 Approve Speed as a Character field

Your Pass 1 open question 9.6 correctly identified that Speed is missing. Approved resolution:

- **Add `speed: int = 25` to `Character`** (frozen). This is base speed from ancestry/class.
- **Add `current_speed: int | None = None` to `CombatantState`** (optional override). Defaults to None, meaning "use character.speed." When conditions modify speed (slowed, hampered, armor speed penalty applied), the CombatantState's current_speed holds the modified value.
- Add a helper: `def effective_speed(state: CombatantState) -> int` that returns `state.current_speed if state.current_speed is not None else state.character.speed`.

Update fixtures:
- Rook: base speed 25, but wearing full plate (−10 speed penalty) AND Str 18 meets the Str threshold (reduces penalty by 5). Final speed at combat: 20 ft. Set `make_rook()` to produce a Character with `speed=25` and note that CombatantState wrappers can set `current_speed=20` to reflect the armor. For Checkpoint 1 mocked tests, we can just set `current_speed=20` on Rook's state.
- Aetregan, Dalai: base 25.
- Erisen: base 30 (Elf Nimble Elf ancestry feat grants +5 Speed). **Verify this assumption against AoN** before setting — if Erisen doesn't actually have Nimble Elf, use 25.

Update the Tactical Takedown evaluator to use `effective_speed()` divided by 2 for the half-Speed Stride distance check.

(AoN: Speed rules — https://2e.aonprd.com/Rules.aspx?ID=2153. Verify and cite.)

### C.6 Flesh out Gather to Me's "who actually benefits" tracking

Pass 1's Section 6.2 is too terse. Expand it:

When evaluating Gather to Me!, iterate all squadmates and count:
- `will_respond`: squadmates with `reactions_available > 0` OR who can receive the Drilled Reactions grant
- `cannot_respond`: squadmates with 0 reactions and no Drilled Reactions grant available

The justification should quantify this:
> "Gather to Me! → 3 of 4 squadmates Stride toward banner aura as reactions (1 action). Erisen is out of reactions; defensive value for 3 squadmates pending Checkpoint 4."

If 0 squadmates can respond, the tactic is effectively wasted even though it's technically eligible. Mark it eligible but with a justification noting "0 of N squadmates can respond."

Expected damage dealt remains 0 (no Strikes involved). Expected damage avoided remains 0 (Checkpoint 4 territory). But the justification now conveys actual utility.

### C.7 Minor: add `conditions_applied` field to TacticResult

Your Pass 1 open question 9.3 recommended this field. Add it to the Pass 2 plan:

```python
@dataclass(frozen=True)
class TacticResult:
    ...
    # Conditions that the tactic applies to enemies if it succeeds.
    # Format: {"Bandit1": ["prone"], "Bandit2": ["off_guard"]}
    # Populated for Checkpoint 5 (turn evaluator) to use when computing
    # follow-up action EV. For Checkpoint 1, this is informational.
    conditions_applied: dict[str, list[str]] = field(default_factory=dict)
```

For Tactical Takedown: if the save probability produces any prone outcome, populate this with `{enemy_name: ["prone"]}`. Note that the *probability* of the condition being applied is separate — you can also include a `condition_probabilities: dict[str, dict[str, float]]` field:

```python
condition_probabilities: dict[str, dict[str, float]] = field(default_factory=dict)
# Example: {"Bandit1": {"prone": 0.55}}
```

This lets Checkpoint 5's turn evaluator compute probability-weighted follow-up EV correctly. Strike Hard and Gather to Me won't populate these fields. Tactical Takedown will.

### C.8 Mountaineering Training: confirm it's actually useful to include

Pass 1 listed Mountaineering Training as a passive buff with "situational value not computed." Fair. But re-read the actual text from AoN:

> "Your instructions make it easier for you and your allies to scale dangerous surfaces. Signal all squadmates; until the end of your next turn, you and each ally gain a climb Speed of 20 feet."

For the Outlaws of Alkenstar campaign, climbing comes up rarely. The simulator should include this tactic in the registry for data-model completeness, but the evaluator returns `eligible=True, expected_damage_dealt=0, expected_damage_avoided=0` and the justification says "No vertical terrain in scenario; no value computed."

Optional: accept a scenario flag like `has_vertical_terrain: bool = False` and if True, return some placeholder positive value. Probably not worth implementing in Checkpoint 1. Mark it as an "open question for later checkpoints" if the feature ever matters.

---

## Confirmed as-is from Pass 1

The following decisions are approved and don't need revisiting:

- TacticDefinition field structure (name, aon_url, action_cost, traits as frozenset, range_type, target_type, granted_action, modifiers as dict, prerequisites as tuple)
- Dispatch via dict of evaluator callables keyed by granted_action
- SpatialQueries as a Protocol, with MockSpatialQueries as a pre-computed data class for testing
- TacticContext shape (commander, squadmates, enemies, banner state, spatial queries, scenario flags)
- TacticResult as frozen dataclass with pre-formatted justification strings + structured fields
- The 5 folio tactics as entries in FOLIO_TACTICS with the 3 prepared ones in PREPARED_TACTICS
- Strike Hard, Gather to Me, Tactical Takedown evaluator structures (with the C.6 enhancement for Gather to Me)
- Defensive Retreat and Mountaineering Training as placeholder evaluators
- Mock data structure for the 8 test cases in Section 7
- The Speed addition (C.5) is the only foundation change; everything else in `pf2e/` stays unchanged

---

## Output Format

Produce a compact Pass 2 plan document with these sections:

1. **Corrections applied** — brief confirmation of each C.1–C.8 item with updated values (URLs, text, numbers)
2. **Updated Section 2** — the 5 tactic registry entries with verified URLs and confirmed action costs
3. **Updated Section 4** — TacticResult with the new `conditions_applied` and `condition_probabilities` fields
4. **Updated Section 6.2** — Gather to Me evaluator with the "who responds" logic
5. **Updated Section 6.3** — Tactical Takedown with correct prone URL, 55% probability, and condition probability population
6. **New Section 10: Foundation changes** — lists the Speed addition to Character and CombatantState, with updated fixture notes
7. **Anything unchanged from Pass 1** — just say "unchanged" with a one-line summary

Aim for 2-3 pages. This is a surgical update, not a new plan.

Cite AoN URLs for every mechanical claim. Any remaining UNVERIFIED items should be flagged explicitly as blockers for Pass 3.

When you're done, output the Pass 2 plan as a single document. Wait for review before any code is written.

---

## What Happens Next

1. You produce this Pass 2 plan.
2. I review and confirm (or flag anything I missed).
3. We move directly to Pass 3 implementation.
4. Code lands with tests passing, and we close Checkpoint 1.
