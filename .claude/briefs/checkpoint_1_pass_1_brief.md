# Checkpoint 1 Pass 1: Tactic Representation and Dispatcher — Architectural Plan

## Context

The foundation is complete (97/97 tests passing). All derivation functions for PF2e combat math are implemented and validated. Now we build the layer that turns "what Commander tactic should I use?" into a ranked answer.

This is **Pass 1 of the three-pass loop for Checkpoint 1**. Your job is to produce an architectural plan, not code. After I review it, we'll do Pass 2 (refinement) and then Pass 3 (implementation).

## Standing Rules (apply to every brief)

1. **Verify rules against Archives of Nethys (https://2e.aonprd.com/)** before stating them. Use web search. Cite URLs. If a search fails, mark the claim UNVERIFIED and flag it for review.
2. **Cite AoN URLs** in every docstring for non-trivial mechanics.
3. **Read existing code before proposing changes.** Pull actual files; don't rely on memory. Start by reading `pf2e/combat_math.py`, `pf2e/character.py`, and `CHANGELOG.md` before designing anything.
4. **Surface discrepancies, don't silently fix them.** If the brief's numbers don't match your math, flag it.
5. **Don't expand scope.** This checkpoint is tactic dispatcher only. No grid, no scenario loader, no turn evaluator. New ideas go into "open questions for next checkpoint."
6. **Test what you build** (but in this pass, just describe the test cases you'd write, don't write tests yet).

---

## Your Task: Architectural Plan for Checkpoint 1

Design the tactic representation layer and its dispatcher. Produce a written plan covering the sections below. Do not write implementation code yet.

## Scope

### What's in scope for Checkpoint 1

- `pf2e/tactics.py` — new module with `TacticDefinition` dataclass and a registry of Aetregan's 5 folio tactics
- A `TacticContext` dataclass carrying everything the dispatcher needs to evaluate a tactic
- A `TacticResult` dataclass holding the output (EV, eligibility, justification)
- A dispatcher function `evaluate_tactic(definition, context) -> TacticResult` that routes to per-tactic evaluators based on the tactic's `granted_action` field
- Per-tactic evaluator functions for the 3 currently prepared tactics: Strike Hard!, Gather to Me!, Tactical Takedown
- Registry entries (data only, no evaluators yet) for the other 2 folio tactics: Defensive Retreat, Mountaineering Training
- Plan for how the dispatcher will interact with spatial queries (which Checkpoint 2 will implement)

### What's explicitly NOT in scope

- No `sim/grid.py` — spatial reasoning comes in Checkpoint 2. For now, spatial queries are **mocked** by the context.
- No `sim/scenario.py` — scenario loading comes in Checkpoint 3.
- No turn planning or multi-action enumeration — that's Checkpoint 5.
- No defensive value calculation (Shield Block, Intercept Attack, etc.) — that's Checkpoint 4.
- No implementation of the 2 non-prepared tactics' evaluators — registry entries only.

## What the Plan Must Cover

### 1. Tactic metadata: what a `TacticDefinition` needs to carry

List every field on `TacticDefinition` and justify each one. Consider:

- **Name** — display name for output
- **Action cost** — 1 or 2 Commander actions (integer)
- **Tactic traits** — Offensive, Mobility, Brandish, etc. (how to represent — enum? string set?)
- **Range/source type** — "banner aura", "emanation 30 ft", etc.
- **Target type** — single ally, two allies, all allies in aura, enemy, etc.
- **Granted action** — what the signaled ally does as a reaction (Strike, Stride, Step, Raise Shield, etc.)
- **Prerequisites** — conditions that must be satisfied for the tactic to be usable
- **Modifiers/effects** — tactic-specific parameters (e.g., Tactical Takedown's save-vs-prone)
- **Frequency limits** — if any (e.g., "once per 10 minutes" for some tactics)
- **AoN URL** — citation in the data itself, for future maintenance

Decide: should modifiers be a `dict[str, Any]` (flexible, untyped) or a typed dataclass per granted_action type (safer, more code)? Recommend one and justify.

**Citations required:** For every tactic in the folio, cite the exact AoN URL for that tactic's rules.

### 2. The five folio tactics: exact registry entries

For each of Aetregan's 5 folio tactics, provide:

- The exact AoN URL (verify before including)
- Exact action cost
- Exact target type
- Exact prerequisites  
- Exact modifiers
- A verbatim quote (from AoN) of the mechanical effect so we can sanity-check later

The five tactics:

1. **Strike Hard!** — https://2e.aonprd.com/Tactics.aspx?ID=13
2. **Gather to Me!** — https://2e.aonprd.com/Tactics.aspx?ID=2
3. **Tactical Takedown** — https://2e.aonprd.com/Tactics.aspx?ID=14
4. **Defensive Retreat** — search AoN for the URL
5. **Mountaineering Training** — search AoN for the URL

For Defensive Retreat and Mountaineering Training, search the AoN tactics index and cite the URL you find. If either appears to be a different tactic than what we expect (e.g., renamed), flag it and propose the closest match.

### 3. `TacticContext`: what the dispatcher needs to know

Design the context object passed to every tactic evaluator. At minimum it needs:

- The commander's `CombatantState`
- All squadmates' `CombatantState` with positions
- All enemies' `EnemyTarget` (or a richer Enemy type?) with positions
- Banner state (planted or carried, position)
- A set of **spatial query functions** (mocked for now): things like `is_in_aura(squadmate) -> bool`, `distance_between(a, b) -> int`, `can_reach(squadmate, enemy) -> bool`
- Scenario-level flags (Anthem active?)

Decide: should spatial queries be methods on `TacticContext` itself, or should they be a separate `SpatialQueries` protocol that context holds? This matters for how Checkpoint 2's grid implementation will plug in.

**Open question to address:** how do we mock spatial queries in Checkpoint 1 tests? Two options:

- **Option A:** `TacticContext` carries a dict of pre-computed answers (`in_aura={"Rook": True, "Dalai": True}`, `enemies_in_reach_of={"Rook": ["Bandit1"]}`). Tests populate this dict directly.
- **Option B:** `TacticContext` takes a callable for each query. Tests pass lambda mocks.

Recommend one and justify.

### 4. `TacticResult`: what the dispatcher outputs

Design the result object. At minimum:

- `tactic_name: str`
- `eligible: bool`
- `ineligibility_reason: str` (if not eligible)
- `expected_damage_dealt: float`
- `expected_damage_avoided: float` — placeholder for now; value is 0 at this checkpoint since defensive evaluation is Checkpoint 4
- `action_cost: int` — for comparing tactics in Checkpoint 5's turn planner
- `justification: str` — human-readable explanation of the math
- `details: dict[str, Any]` — optional structured breakdown for formatter use

Decide: should `justification` be a pre-formatted string, or should it be structured data that the formatter in Checkpoint 6 converts to text? Recommend one.

### 5. The dispatcher

Sketch the dispatcher function's structure:

```python
def evaluate_tactic(
    definition: TacticDefinition,
    context: TacticContext,
) -> TacticResult:
    ...
```

Describe the dispatch logic. Options:

- **Switch on `granted_action` string:** Dispatcher has a big if/elif chain routing to per-tactic evaluators.
- **Registry of evaluator callables:** Each `TacticDefinition` holds a reference to its own evaluator function.
- **Evaluator classes:** Each tactic is a class with an `evaluate(context)` method.

Recommend one and justify, considering: how easy is it to add new tactics? How testable is it? How does it interact with the data-driven registry?

### 6. Per-tactic evaluators

For each of the 3 prepared tactics, sketch the evaluator function:

#### Strike Hard! (2 actions, reaction Strike)

- Eligibility: is there at least one squadmate in banner aura who has a reachable enemy?
- Choice: which squadmate + which enemy produces the best EV?
- Math: `expected_strike_damage(ally_state, ally_weapon, enemy_ac, is_reaction=True)`
- Key detail: `is_reaction=True` → MAP 0 regardless of what the ally did on their own turn
- Justification text example: "Rook reaction Strike at +7 (MAP 0) vs Bandit AC 15, EV 6.80"

#### Gather to Me! (1 action, reaction Stride toward aura)

- Eligibility: always eligible (all squadmates signaled)
- Challenge: this tactic's value is mostly **defensive** (allies repositioning out of threats). Since defensive evaluation is Checkpoint 4, the Checkpoint 1 version produces `expected_damage_dealt = 0` and a justification noting "defensive value pending Checkpoint 4."
- For Checkpoint 1, the evaluator just confirms eligibility and sets up the result structure.

#### Tactical Takedown (2 actions, two squadmates Stride + Reflex save for prone)

- Eligibility: at least 2 squadmates in banner aura who can both reach the same enemy with half-Speed Stride
- Choice: which enemy to target (if multiple are reachable by pairs)
- Math: target makes Reflex save vs Aetregan's class DC (17 at level 1). On fail, target is prone (off-guard + -2 attack penalty + costs action to stand).
- Direct damage from the tactic itself: **zero**. The value is in setting up prone for follow-up Strikes.
- Open question: for Checkpoint 1, do we count "expected damage from follow-up Strikes against prone enemy" in the EV? Probably no — that's turn planning territory (Checkpoint 5). For Checkpoint 1, report the save outcome probability and flag it in justification.

Sketch each evaluator's:
- Input validation (check prerequisites against context)
- The core computation
- The justification text format
- How it handles edge cases (no enemies in reach, etc.)

### 7. Mock data for Checkpoint 1 tests

Describe what test scenarios you'd build. Sketch at least:

- **Strike Hard test:** Aetregan (commander) + Rook in aura + Bandit in Rook's melee reach → expect eligible, specific EV
- **Strike Hard ineligible test:** Rook NOT in aura → expect ineligible with reason
- **Gather to Me test:** any scenario → expect eligible, placeholder defensive value
- **Tactical Takedown test:** 2 squadmates + shared reachable enemy → expect eligible, save probability in result
- **Tactical Takedown ineligible test:** only 1 squadmate in aura → expect ineligible

These become the Checkpoint 1 test suite. Sketch the mock data shape (how you populate the mocked spatial query values).

### 8. Integration points with future checkpoints

List how Checkpoint 1's output is consumed by future work:

- **Checkpoint 2 (grid):** will replace the mocked spatial queries with real `GridState` queries
- **Checkpoint 4 (defensive value):** will populate the `expected_damage_avoided` field by computing Intercept Attack / Shield Block / repositioning value
- **Checkpoint 5 (turn evaluator):** will iterate over all tactics, call the dispatcher, and combine results with supplementary action EVs
- **Checkpoint 6 (formatter):** will consume `TacticResult.justification` and `details`

Flag anything in your design that might make these integrations painful.

### 9. Open questions for Pass 2

List any decisions where there are multiple reasonable approaches and you want input before committing. Include at minimum:

- Strike Hard ally/weapon selection: do we pick the best EV combination always, or let the user specify which ally to signal?
- Tactical Takedown target choice: pick highest EV target, or all valid enemy options returned so user can choose?
- How to represent "prone" as an outcome? A new field on TacticResult? A condition to apply to the target?
- How should the dispatcher handle a tactic whose effect is entirely defensive (Gather to Me, Mountaineering Training) when Checkpoint 4's defensive math isn't available yet?
- Should tactic evaluators know about reaction economy (allies with 0 reactions can't respond), or is that Checkpoint 5's concern?

## Output Format

Produce a single markdown document with sections matching the 9 items above. Use code blocks for dataclass sketches and function signatures. Aim for skimmable but thorough.

Cite AoN URLs for every mechanical claim. Mark anything you can't verify as `(UNVERIFIED — please check)`.

When you're done, output the plan as a single document and wait for review. No code yet.

## What Comes After

1. You produce this Pass 1 plan.
2. I review it, flag errors, and write a Pass 2 correction brief.
3. You produce a Pass 2 refined plan.
4. I review again, and if it's ready, I write the Pass 3 implementation brief.
5. You implement the code + tests.
6. We close Checkpoint 1 and move to Checkpoint 2.
