# Checkpoint 5.1.3b Pass 2: Algorithms — Refinement

## Meta

- **Checkpoint:** CP5.1.3b
- **Pass:** 2 (refinement — **still no code**)
- **Predecessor:** CP5.1.3b Pass 1 plan at `.claude/briefs/checkpoint_5_1_3b_pass_1_plan.md`
- **Successor:** CP5.1.3b Pass 3 (implementation)

Save this brief to `.claude/briefs/checkpoint_5_1_3b_pass_2_brief.md`.

## Your deliverable for this pass

An updated plan document saved to `.claude/briefs/checkpoint_5_1_3b_pass_2_plan.md`. This is **not a full rewrite**. It is a compact diff-style document that:

1. Applies every correction listed below to the Pass 1 plan
2. Ratifies the Pass 1 decisions explicitly where this brief says "ratified"
3. Adds concrete field lists, function signatures, and test expectations where Pass 1 left them abstract
4. Closes all 10 open questions from Pass 1 Section 12
5. Flags any new blocker that arises from applying these corrections

**Still no production code. No test files. No tests run.** Plan document only. When I sign off on Pass 2, I write Pass 3 and the CLI agent implements.

## Context to reload

Re-read these before refining:
1. `.claude/briefs/checkpoint_5_1_3b_pass_1_plan.md` — the plan we're refining
2. `.claude/project_reference/DECISIONS.md` — D11-D18 are binding; also note the Non-Decisions section (reaction-policy optimality deferred to CP6)
3. `pf2e/character.py` — especially every field on `CombatantState` and `EnemyState`, for the snapshot corrections below

You do **not** need to redo AoN research except where explicitly flagged.

---

## Part A — Ratifications

Pass 1's recommendations on these questions stand. Include a one-line "Ratified: [short reasoning from Pass 1]" in the Pass 2 plan for each:

1. **RoundState shape: Option B (frozen snapshots).** Ratified.
2. **Scoring symmetry: (b) inline accumulation in search loop.** Ratified.
3. **Beam search stub approach: callable injection with mock evaluators for 3b tests.** Ratified.
4. **Enemy recursion: single-best-response, no sub-sub-searches.** Ratified.
5. **Initiative tiebreaker: enemies precede PCs; alphabetical for same-side ties.** Ratified.
6. **Initiative override: partial (unlisted combatants roll normally).** Ratified.
7. **Damage pipeline order: Intercept → Shield Block → Resistance → Temp HP → Real HP.** Ratified.
8. **CLI `--debug-search` flag: defer to CP5.1.3c.** Ratified.
9. **Temp HP in damage_taken scoring: NOT counted.** Ratified.
10. **Shield Block relative to Resistance: BEFORE.** Ratified. The Pass 2 plan should add one paragraph explicitly calling this an *interpretive choice* (both reductions apply at the same logical "damage reduces HP" step; we chose Shield Block first because it reduces the damage number before intrinsic resistance operates on the remainder). Cite the same AoN sources Pass 1 used.

Also ratified interpretive call from Pass 2 review:

11. **kill_value as bonus on top of damage_dealt (not a replacement).** The scoring formula from Pass 1 Section 3 stands: `score = Σ kill_score + Σ drop_score + damage_dealt − 0.5 × damage_taken`, where `kill_score` fires on threshold crossing and `damage_dealt` counts all damage. A full kill is rewarded for both the damage AND the kill bonus.

12. **Enemy sub-search beam widening: (20, 10, 5).** Pass 1 already proposed this in `SearchConfig.enemy_beam_widths`. Ratified — mirrors PC widening pattern, diverse first-candidate protection at negligible cost.

---

## Part B — Blocker corrections (must apply)

These are errors or omissions in Pass 1 that would cause Pass 3 to fail. Apply each.

### B1. CombatantSnapshot missing fields

Pass 1's `CombatantSnapshot` is incomplete. The existing `CombatantState` has fields that tactic evaluators and combat math functions already read. Every one must be captured or the search will produce wrong numbers the moment we swap in snapshots.

Add to `CombatantSnapshot`:

- `current_speed: int | None` — Rook's full plate applies -10 via `make_rook_combat_state()` setting this to 20. `effective_speed()` in combat_math reads it. Missing → half-Speed Stride calculations silently wrong.
- `status_bonus_attack: int` — Anthem's +1 to attack. Used in `attack_bonus()`.
- `status_bonus_damage: int` — Anthem's +1 to damage. Used in `damage_avg()`.

The Pass 2 plan's `CombatantSnapshot` should have the full field set:

```python
@dataclass(frozen=True)
class CombatantSnapshot:
    name: str
    character: Character          # shared, immutable
    position: tuple[int, int]
    current_hp: int               # concrete, not None
    temp_hp: int
    current_speed: int | None
    reactions_available: int
    guardian_reactions_available: int
    drilled_reaction_available: bool
    shield_raised: bool
    off_guard: bool
    frightened: int
    prone: bool
    actions_remaining: int
    status_bonus_attack: int
    status_bonus_damage: int
```

Note that `character` stays in the snapshot — it's a shared reference to the immutable Character, and it carries the build data (abilities, proficiencies, equipped weapons, speed baseline, feat flags).

### B2. EnemySnapshot missing `saves`

Pass 1's `EnemySnapshot` has no `saves` field. Tactical Takedown's evaluator reads `enemy.saves[SaveType.REFLEX]`. Every existing tactic that triggers a save breaks without this.

Add:

```python
saves: dict[SaveType, int]
```

The full `EnemySnapshot` field set should be:

```python
@dataclass(frozen=True)
class EnemySnapshot:
    name: str
    position: tuple[int, int]
    current_hp: int
    max_hp: int
    ac: int
    saves: dict[SaveType, int]
    attack_bonus: int
    damage_dice: str
    damage_bonus: int
    num_attacks_per_turn: int
    perception_bonus: int
    off_guard: bool
    prone: bool
    actions_remaining: int
```

Note: dicts are mutable and don't compose with frozen semantics perfectly. For this snapshot, document a convention: "Dict fields are immutable-by-convention — don't mutate after construction. Use `dataclasses.replace()` with a new dict to modify." This matches the pattern already used in `Character.skill_proficiencies`.

### B3. Default role_multiplier

Pass 1's `_ROLE_MULTIPLIERS` dict lists Dalai Alpaca only. Rook, Aetregan, Erisen's `drop_cost` would be undefined.

Specify:

```python
_ROLE_MULTIPLIERS: dict[str, float] = {"Dalai Alpaca": 2.0}
_DEFAULT_ROLE_MULTIPLIER: float = 1.0

def role_multiplier(pc_name: str) -> float:
    return _ROLE_MULTIPLIERS.get(pc_name, _DEFAULT_ROLE_MULTIPLIER)
```

All PCs without an explicit entry use 1.0.

### B4. Initiative RNG must be isolated

Pass 1's initiative pseudocode says `random.randint(1, 20)`. That touches the global `random` module — tests that run after initiative rolling would get non-deterministic behavior.

Specify:

```python
def roll_initiative(
    pcs: list[CombatantSnapshot],
    enemies: list[EnemySnapshot],
    seed: int,
    explicit: dict[str, int] | None = None,
) -> list[str]:
    rng = random.Random(seed)
    # ... use rng.randint, NOT random.randint
```

This is how all tests should be written too — never touch the module-level RNG.

### B5. Kill/drop branching — collapse-to-two-worlds, not per-outcome

Pass 1 Section 4 describes branching per crossing outcome. If Hit (0.5) and Crit (0.1) both cross the kill threshold on a low-HP enemy, Pass 1's rule produces three branches (Miss / Kill-via-Hit / Kill-via-Crit). The Kill-via-Hit and Kill-via-Crit worlds are identical for the rest of the search — enemy is dead in both.

Correct rule for Pass 2:

> For each action outcome, compute whether it causes a kill or drop threshold crossing. Collect all crossing outcomes' probabilities into a single `P(event)`. If `P(event) >= 0.05`, spawn exactly two child states:
> - **Event world:** target HP = 0, probability = P(event). All crossing outcomes collapse into this branch with their joint probability.
> - **No-event world:** target HP updated by EV of non-crossing outcomes, probability = 1 - P(event).
> If `P(event) < 0.05`, no branching; all outcomes fold into EV-updated state.

Also clarify: "collapse into EV" for non-crossing outcomes means averaging HP changes weighted by outcome probability, renormalized within the no-event world.

Add a worked example to the Pass 2 plan:
- Enemy at 5 HP. Strike with outcomes: {miss 0.4, hit 0.5 deals 8, crit 0.1 deals 16}.
- Hit and Crit both cross (post-HP = -3 or -11). P(event) = 0.6.
- Event world: enemy HP = 0, probability 0.6.
- No-event world: enemy HP = 5 (miss dealt no damage, was the only non-crossing outcome), probability 0.4.

### B6. Kill/drop branching — explicitly branch-per-target, not branch-per-action

Worth making explicit: if a single action (say, a mortar AoE) could kill *multiple* enemies each independently, the branching is 2^N where N is the number of targets with >=5% kill probability. For CP5.1.3b this is a theoretical worry (no multi-target actions are wired in until CP5.1.3c/CP5.2), but the branching logic should handle it correctly when CP5.2's mortar ships.

Specify: for multi-target outcomes, compute P(event) per-target, and spawn one branch per distinct "alive/dead vector" with >=5% joint probability. Prune branches whose joint probability falls below the 0.1% pruning threshold (D13).

---

## Part C — Interpretive call ratification: reactions as full search-branching (C2)

Pass 1 left reactions ambiguous — it mentioned them in the damage pipeline and as ActionType values. Pass 2 resolves this with **C2 (full integration)**. This is a material architecture decision; the Pass 2 plan must spell it out cleanly.

### The model

Reactions are first-class Actions the search considers. Each eligible enemy Strike creates a reaction decision point in the search tree:

- If Rook (Guardian) is within 10 ft of the target and has `guardian_reactions_available > 0`, the search branches on: **Intercept** (redirect, consume reaction) vs **Don't Intercept** (original target takes the hit).
- If the target has a shield raised and `reactions_available > 0`, the search branches on: **Shield Block** (absorb up to hardness, consume reaction, shield takes damage) vs **Don't Block** (target takes full damage).
- Both reactions can trigger on the same Strike. Intercept first (retarget), then Shield Block on the redirected target.

### Branching factor concern

A typical round with 2 enemies x 2 attacks x Rook-eligible creates up to 4 reaction decision points. Each doubles the sub-tree. In worst case, reactions alone cause 2^4 = 16 branches on top of the 3-action turn branching. The Pass 2 plan must acknowledge this and require Pass 3 to:

- **Add a timing target:** Pass 3 must specify that `simulate_round()` on the canonical Strike Hard scenario completes in **under 15 seconds** on the CLI agent's machine. Pass 3 implementation must include a pytest marker or explicit timing assertion. If implementation misses the target, the escape hatch in B below applies.
- **Log branch count per search.** Pass 3 adds logging at INFO level: "simulate_round: total branches explored, max simultaneous beam size."

### Escape hatch

If Pass 3 implementation reveals reaction branching explodes unacceptably (timing target missed, or test suite slow enough to hurt iteration speed), the fallback is **C1 commit-based reactions**: search commits reactions via "Ready" actions, damage pipeline fires on commitment. This is a smaller diff than rewriting damage pipeline, so the fallback is tractable.

Pass 2 plan notes this escape hatch as a Pass 3 contingency, not a default.

### Damage pipeline signature update

`resolve_strike_outcome` from Pass 1 Section 8 needs an additional parameter to receive reaction decisions:

```python
@dataclass(frozen=True)
class ReactionChoices:
    intercept_by: str | None = None    # name of interceptor, or None
    shield_block_by: str | None = None # name of blocker, or None

def resolve_strike_outcome(
    damage: float,
    target_name: str,
    state: RoundState,
    reactions: ReactionChoices,
    is_physical: bool = True,
) -> StrikeResolution:
    ...
```

The search tree, at a reaction decision point, constructs two (or four, if both reactions eligible) `ReactionChoices` variants and calls `resolve_strike_outcome` for each. Each result becomes a separate `ActionOutcome` in the enemy's Strike `ActionResult`.

### Enumerating reaction decision points

Pass 2 must specify *where* in the search logic reaction branching is triggered. Proposed location:

- In `adversarial_enemy_turn()`, when the enemy's candidate action includes a Strike against a specific PC target, check:
  - Is any PC with `guardian_reactions_available > 0` within 10 ft of the target and able to Step to become adjacent? If yes -> Intercept is a branchable choice.
  - Does the target have `shield_raised=True` and `reactions_available > 0`? If yes -> Shield Block is a branchable choice.
- The Strike's ActionOutcome set expands: instead of {miss, hit, crit} at 3 outcomes, it becomes {miss, hit x reaction_combinations, crit x reaction_combinations} — potentially up to 12 outcomes per Strike.

Specify: the outcome-pruning threshold (0.1%) applies to these reaction-expanded outcomes. Low-probability reaction-combos get pruned naturally.

---

## Part D — Minor clarifications

### D1. GridState sharing

Explicitly note: `GridState` is not frozen but is treated as immutable post-construction. All RoundState branches share the same `GridState` reference. No copying.

### D2. AoN URL verification for initiative

Pass 1 cites `https://2e.aonprd.com/Rules.aspx?ID=2423` for "Step 1: Roll Initiative". Existing `RULES_CITATIONS.md` cites `https://2e.aonprd.com/Rules.aspx?ID=2127` for Initiative. Pass 2 must:

1. `web_fetch` both URLs
2. Determine which is the canonical initiative rule page (the encounter-mode initiative rules)
3. Cite the correct one in the Pass 2 plan
4. Note any discrepancy for `RULES_CITATIONS.md` to be updated in Pass 3

### D3. Shield Block interpretive choice paragraph

Per Part A ratification 10, Pass 2 plan adds one paragraph noting Shield Block before Resistance is an interpretive choice, with reasoning. Keep it to 3-4 sentences.

---

## Part E — Test expectations (concretize)

Pass 1 gave rough test counts. Pass 2 sharpens these into specific test classes and counts:

### `tests/test_round_state.py` (~10 tests)

- `TestRoundStateConstruction` (3 tests): from_scenario produces correct snapshot shapes; initiative_order correctly ordered; grid shared reference
- `TestSnapshotImmutability` (3 tests): frozen dataclass raises on mutation; dict-field mutation convention documented via test; dataclasses.replace produces new instance
- `TestBranching` (4 tests): with_pc_update returns new instance with one changed entry; other PCs unchanged (reference equality); original state unchanged; branch_probability carries through

### `tests/test_search.py` (~20 tests)

- `TestBeamSearch` (6 tests): selects highest-score sequence with mock evaluator; beam widths respected per depth; pruning fires below 0.1%; widening at root produces diverse first-action candidates
- `TestKillDropBranching` (5 tests): >=5% threshold crossing spawns exactly 2 children; <5% folds into EV; multi-target multi-branch; no-kill world HP updated to EV; event-world HP = 0
- `TestReactionBranching` (4 tests): Intercept decision point branches; Shield Block decision point branches; both-reactions quad-branch; ineligible reactions don't branch
- `TestAdversarialEnemy` (3 tests): enemy search sign-flips score correctly; uses (20,10,5) beam; no recursive sub-search
- `TestSimulateRound` (2 tests): runs PCs and enemies in initiative order with mocks; final state has all turns applied

### `tests/test_initiative.py` (~8 tests)

- `TestRolling` (3 tests): seeded deterministic; Perception bonus applied; uses isolated RNG not global
- `TestOverrides` (2 tests): full explicit override; partial override — unlisted roll normally
- `TestTiebreakers` (3 tests): enemies beat PCs on tie; alphabetical same-side PC; alphabetical same-side enemy

### `tests/test_damage_pipeline.py` (~15 tests)

- `TestResolveStrikeBasic` (3 tests): hit damage; crit doubles; miss is zero
- `TestShieldBlock` (3 tests): absorbs up to hardness; shield takes damage; consumes general reaction
- `TestIntercept` (3 tests): redirects to interceptor; consumes guardian reaction; Rook's Guardian's Armor applies to intercepted damage
- `TestResistance` (2 tests): Guardian's Armor reduces remaining damage; physical-only restriction honored
- `TestTempHP` (2 tests): temp HP absorbed first; remaining hits real HP
- `TestFullPipeline` (2 tests): all steps in order: intercept + shield block + resistance + temp HP + real HP

Target: 53 tests. Allows ~7 test slack while remaining within the 40-60 range (255 -> 308).

### Killer regression

`tests/test_scenario.py::TestKillerValidation::test_strike_hard_from_disk` must still assert EV 8.55 and pass unchanged. Pass 2 plan notes this as non-negotiable.

---

## Part F — Remaining questions for Pass 3 brief to finalize

These don't need Pass 2 answers; they're Pass 3 implementation details that I'll decide in the Pass 3 brief. Pass 2 plan should just list them:

1. Exact BFS cost function for Intercept Attack Step eligibility (reuse existing `can_reach_with_stride` with 5-ft budget)
2. Precise output format for `RoundRecommendation` (deferred to CP5.1.3c anyway)
3. Whether `SearchConfig.seed` or `RoundState` carries the RNG state for within-search randomness (probably config, for reproducibility)
4. Whether reaction decision points are represented as explicit "reaction nodes" in the search tree or as outcome-multiplication on the triggering Strike's ActionResult

---

## What to do when you finish

1. Save the refined plan to `.claude/briefs/checkpoint_5_1_3b_pass_2_plan.md`.
2. Do **not** modify any other file.
3. Do **not** run pytest.
4. Do **not** commit.
5. Print a short summary: (a) list of ratified decisions, (b) list of blocker fixes applied, (c) acknowledgment of C2 reaction model with branching-factor concern, (d) any new `(UNVERIFIED — please check)` tags.

If you encounter a design decision that this brief does not cover, flag it for Pass 3 resolution — do not invent new architecture in Pass 2.
