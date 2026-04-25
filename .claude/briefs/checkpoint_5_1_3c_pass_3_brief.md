# CP5.1 Pass 3c — Pass 3 Brief: Implementation

## Before You Start

Read these files in full before writing a single line of code:

```
pf2e/actions.py
pf2e/combat_math.py
pf2e/damage_pipeline.py
pf2e/tactics.py
pf2e/character.py
pf2e/types.py
sim/round_state.py
sim/search.py
sim/scenario.py
sim/grid_spatial.py
sim/grid.py
sim/initiative.py
tests/test_actions.py
tests/test_search.py
tests/test_round_state.py
```

Do not assume any interface from the briefs. The code is the truth. If something
contradicts this brief, flag it before proceeding.

---

## Implementation Order

Follow this order strictly. Do not skip steps or reorder.

---

### Step 1: Add blocker fields to snapshots

In `sim/round_state.py`, add two fields to `CombatantSnapshot` and one to `EnemySnapshot`.

**CombatantSnapshot** — add at the end of the dataclass:

```python
map_count: int = 0
# Number of attack-trait actions taken this turn (Strike, Trip, Disarm).
# Resets to 0 at the start of the actor's turn in beam_search_turn.
# Reactive Strikes always use map_count=0 regardless of this value.

conditions: frozenset[str] = frozenset()
# General-purpose condition/immunity tags.
# Does NOT replace existing boolean fields (off_guard, prone, shield_raised, frightened).
# Used only for immunity tracking and new conditions added in CP5.1.3c:
#   "demoralize_immune", "diversion_immune"
```

**EnemySnapshot** — add at the end of the dataclass:

```python
conditions: frozenset[str] = frozenset()
# Same purpose as CombatantSnapshot.conditions.
```

Update `from_combatant_state()` to include `map_count=0, conditions=frozenset()`.
Update `from_enemy_state()` to include `conditions=frozenset()`.

### Step 2: Update apply_outcome_to_state for conditions

In `sim/search.py`, extend the `apply_outcome_to_state` function (or equivalent)
to handle the new `conditions` frozenset. After the existing hardcoded condition
handling (off_guard, prone, shield_raised, frightened), add:

```python
# For any condition string not handled by a hardcoded field, union it into
# the conditions frozenset of the target combatant.
HARDCODED_CONDITIONS = {"off_guard", "prone", "shield_raised"} | {
    c for c in conds if c.startswith("frightened_")
}
for c in conds:
    if c not in HARDCODED_CONDITIONS:
        if target_is_pc:
            snap = result.pcs[target_name]
            result = result.with_pc_update(
                target_name, conditions=snap.conditions | {c}
            )
        else:
            snap = result.enemies[target_name]
            result = result.with_enemy_update(
                target_name, conditions=snap.conditions | {c}
            )
```

Confirm the exact method names (`with_pc_update`, `with_enemy_update`, etc.) by
reading `sim/round_state.py` before writing this code.

### Step 3: Verify Ever Ready initialization

Read `sim/initiative.py` and confirm that `CombatantSnapshot` is constructed with
`reactions_available=1` for all combatants (the default). No code change is expected.

Add a comment in the initialization code near Guardian snapshot construction:

```python
# reactions_available defaults to 1. For Guardians, the Ever Ready class feature
# guarantees this reaction is available from initiative roll (not just from their
# first turn). This default already satisfies that requirement.
# (AoN: https://2e.aonprd.com/Classes.aspx?ID=67)
```

If the initialization does NOT set `reactions_available=1` correctly for Guardians,
flag it and fix before continuing.

### Step 4: Implement 14 evaluators in pf2e/actions.py

Each evaluator has this signature:

```python
def evaluate_<name>(
    action: Action,
    state: RoundState,
    spatial: SpatialQueries | None = None,
) -> ActionResult:
```

Implement them in this order (simple to complex):

#### 4-A: END_TURN

Always eligible. One outcome: `probability=1.0, score_delta=0.0`,
`state_delta={"actions_remaining": 0}`.

#### 4-B: PLANT_BANNER

Eligible iff `actor.character.has_plant_banner`. Aetregan does not have this at L1.

```python
return ActionResult(
    action=action, eligible=False,
    ineligibility_reason="Plant Banner feat not present"
)
```

(AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)

#### 4-C: RAISE_SHIELD

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)

Eligible iff:
- Actor has a shield (`actor.character.equipment.shield is not None`)
- `"shield_raised"` not in actor's conditions (use the boolean field, not the
  frozenset — check which field tracks this by reading the snapshot definition)

Score delta — danger-weighted EV:

```python
def _raise_shield_ev(actor_snap, state, spatial):
    danger = 0.0
    for enemy in state.enemies.values():
        if not enemy.alive:
            continue
        num_reachable_pcs = max(1, _count_pcs_in_enemy_reach(enemy, state, spatial))
        p_targets_actor = 1.0 / num_reachable_pcs
        dmg = expected_enemy_turn_damage(enemy, actor_snap)
        danger += dmg * p_targets_actor
    return danger * 0.10  # +2 AC reduces hit probability by ~10% (1 face on d20)
    # (AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)
    # Flagged as CP6 calibration target.
```

`expected_enemy_turn_damage` already exists in `pf2e/combat_math.py`. Confirm its
exact signature before calling it.

One outcome: `probability=1.0, score_delta=shield_ev, state_delta={"shield_raised": True}`.

#### 4-D: STEP

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2321)

Eligible always (no terrain check needed for CP5.1.3c — assume valid).

Candidate destinations: the 8 squares adjacent to actor's current position that
are within the grid and not occupied by another creature.

One `ActionOutcome` per candidate: `probability=1.0, score_delta=0.0`,
`state_delta={"actor_position": dest}`.

#### 4-E: STRIDE

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)

Eligible always. Uses `_stride_candidate_destinations()` (see below).

One `ActionOutcome` per candidate destination.

**Private helper:**

```python
def _stride_candidate_destinations(
    actor_snap: CombatantSnapshot,
    state: RoundState,
    spatial: SpatialQueries,
    bfs_cache: dict,   # mutable, keyed by (pos, grid_id) — passed in, not stored
) -> list[Pos]:
```

Five categories (deduplicated, max ~20 total):

1. **Aggressive** — nearest reachable square within weapon reach of each living
   enemy. Limit: top 2 enemies by `expected_strike_damage`.
2. **Flanking** — squares placing actor directly opposite an ally already adjacent
   to an enemy (off-guard via flanking).
   (AoN: https://2e.aonprd.com/Rules.aspx?ID=2361)
   Limit: top 2.
3. **Banner reposition** — squares maximizing allies within 30-ft banner aura.
   Only if `actor.character.has_commander_banner`. Limit: top 2.
4. **Defensive withdrawal** — square maximizing distance from nearest enemy.
   Only if `actor_snap.current_hp / actor.character.max_hp < 0.5` or no adjacent
   allies. Limit: top 1.
5. **Adjacent to wounded ally** — squares adjacent to any ally with
   `current_hp / max_hp < 0.5`. Limit: top 2 by wound severity.

BFS cache: `bfs_cache[(actor_pos, id(spatial))] -> set[Pos]`. Populate on first
access per actor position. Pass the cache dict into `generate_candidates()` and
thread it through to `_stride_candidate_destinations()`. Do not store it anywhere
persistent.

#### 4-F: STRIKE

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2322)
(AoN MAP: https://2e.aonprd.com/Rules.aspx?ID=220)

Eligible iff a living enemy is within weapon reach.

Get current MAP from `actor_snap.map_count`:
```python
from pf2e.combat_math import map_penalty
penalty = map_penalty(actor_snap.map_count, weapon.is_agile)
```

Call `resolve_strike()` from `pf2e/damage_pipeline.py`. Confirm its exact signature.

Returns 3 `ActionOutcome` branches (miss, hit, crit):
- `probability` from `resolve_strike()` outcome distribution
- `score_delta` = outcome damage contribution
- `state_delta` = `{"enemy_hp_delta": damage, "map_count": actor_snap.map_count + 1}`

Kill branching (D14): If P(crit) × average_crit_damage >= 5% chance of reducing
enemy to 0 HP, generate explicit "kill" and "no-kill" branches. Use D12 formula:
`kill_value = enemy.max_hp + 10 * enemy.num_attacks_per_turn`. Otherwise collapse
to EV.

#### 4-G: TRIP

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2309)
(AoN Prone: https://2e.aonprd.com/Conditions.aspx?ID=88)

Eligible iff target is within melee reach (any Athletics rank including untrained).

Uses MAP. Compute: `athletics_bonus = skill_bonus(actor.character, Skill.ATHLETICS)`.

```python
outcomes = enumerate_d20_outcomes(athletics_bonus - map_penalty, reflex_dc)
```

Outcomes:
- Crit success (2+ above DC): Prone applied to enemy + -2 attack penalty
- Success (meets DC): Prone applied to enemy
- Failure: no effect
- Crit failure (10+ below DC): actor becomes Prone

Prone value approximation: -2 to enemy attacks (reduces expected enemy damage) + +2
to ally attacks against prone enemy if adjacent (increases expected ally damage).
Use flat multiplier against remaining expected attacks. Flag in docstring as CP6
calibration target.

`state_delta` for enemy Prone: `{"target_conditions_applied": ["prone"]}`.
`state_delta` for actor Prone (crit fail): `{"actor_conditions_applied": ["prone"]}`.

Map count increments by 1 (Trip has the attack trait).

#### 4-H: DISARM

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2300)

Eligible iff target is within melee reach.

Same Athletics vs. Reflex DC pattern as Trip. Uses MAP. Map count increments by 1.

Outcomes:
- Crit success: target drops held item (enemy loses weapon — flag as CP6 for full
  modeling; for CP5.1.3c, apply -2 attack penalty as approximation)
- Success: -2 circumstance penalty to target's attacks until retrieved
- Failure: no effect
- Crit failure: actor becomes off-guard until start of actor's next turn

Score delta: EV of -2 to enemy attack rolls × expected remaining enemy attacks this
round.

#### 4-I: DEMORALIZE

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2304)
(AoN Frightened: https://2e.aonprd.com/Conditions.aspx?ID=42)

Eligible iff:
- `"demoralize_immune"` not in `enemy_snap.conditions`
- Target within 30 ft
- Line of sight (for CP5.1.3c: assume LoS if within 30 ft — flag as simplification)

**Deceptive Tactics does NOT apply to Demoralize.** Always use Intimidation.

Bonus: `skill_bonus(actor.character, Skill.INTIMIDATION)`.

Outcomes:
- Crit success: Frightened 2
- Success: Frightened 1
- Failure: `"demoralize_immune"` added to `enemy_snap.conditions`
- Crit failure: `"demoralize_immune"` added + actor Frightened 1

Frightened score delta: EV of reduced enemy attack/save rolls × remaining attacks.
Frightened N reduces all rolls by N. Decays by 1 per round end.

#### 4-J: CREATE_A_DIVERSION

(AoN: https://2e.aonprd.com/Skills.aspx?ID=38)

Eligible iff `"diversion_immune"` not in `enemy_snap.conditions`.

Bonus (Deceptive Tactics applies):
```python
if actor.character.has_deceptive_tactics:
    bonus = lore_bonus(actor.character, "Warfare")
else:
    bonus = skill_bonus(actor.character, Skill.DECEPTION)
```

(AoN: https://2e.aonprd.com/Feats.aspx?ID=7794)

Check vs. each target enemy's `perception_dc`.

Outcomes:
- Success: off-guard against actor until end of actor's next turn
- Failure: `"diversion_immune"` added to `enemy_snap.conditions`

Score delta: EV of off-guard bonus against remaining attacks this turn only. The
next-turn carry-over is real but out of single-round scoring scope. Flag in
docstring as an underestimate and CP6 calibration target.

#### 4-K: FEINT

(AoN: https://2e.aonprd.com/Skills.aspx?ID=38)

Eligible iff:
- Target within melee reach
- `actor_snap.actions_remaining >= 2`

No immunity check — Feint has no immunity on failure.

Bonus (Deceptive Tactics applies, same as CREATE_A_DIVERSION).

Check vs. target's `perception_dc`.

Outcomes:
- Crit success: off-guard until start of actor's next turn
- Success: off-guard against actor's next attack this turn only
- Failure: no effect
- Crit failure: actor is off-guard against target's melee attacks until end of
  actor's next turn

Score delta: EV of off-guard bonus × expected hit probability on the next Strike.

#### 4-L: SHIELD_BLOCK (reaction)

(AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)
(AoN Steel Shield hardness 5: https://2e.aonprd.com/Shields.aspx?ID=3)

C1 greedy policy. Fires during damage resolution inside the damage pipeline when:
- `"shield_raised"` in actor conditions
- Incoming damage > shield hardness (5 for steel shield)

Not search-branched. Returns an `ActionResult` representing the policy decision.

Score delta: `min(incoming_damage, hardness)` of damage prevented.

Note: Shield breakage is out of scope for CP5.1.3c. Flag in docstring.

#### 4-M: INTERCEPT_ATTACK (reaction)

(AoN: https://2e.aonprd.com/Actions.aspx?ID=3305)

Guardian-only. C1 greedy policy. Fires when:
- `actor.character.character_class == "Guardian"`
- `actor_snap.reactions_available >= 1`
- An ally within 10 ft is taking physical damage

C1 policy decision: Intercept iff
`ally_snap.current_hp / ally.max_hp < guardian_snap.current_hp / guardian.max_hp`.

Use existing `intercept_attack_ev()` from `pf2e/combat_math.py` for score delta.
Confirm its signature before calling.

#### 4-N: ACTIVATE_TACTIC

Commander-specific. Eligible iff:
- `actor.character.has_commander_banner`
- At least one prepared tactic has eligible squadmates in the banner aura
- `actor_snap.actions_remaining >= tactic.action_cost`

Wraps `evaluate_tactic()` from `pf2e/tactics.py`. Do not reimplement tactic math.

```python
def evaluate_activate_tactic(action, state, spatial):
    tactic_name = action.parameters["tactic_name"]
    tactic_ctx = _build_tactic_context(state, spatial)
    result = evaluate_tactic(tactic_name, tactic_ctx)
    if not result.eligible:
        return ActionResult(action=action, eligible=False,
                           ineligibility_reason=result.justification)
    return ActionResult(
        action=action,
        eligible=True,
        outcomes=[ActionOutcome(
            probability=1.0,
            score_delta=result.expected_value,
            state_delta={"actions_remaining":
                         actor_snap.actions_remaining - tactic.action_cost},
            description=result.justification,
        )]
    )
```

Tactic action costs:
- Strike Hard!: 2 actions
- Gather to Me!: 1 action
- Tactical Takedown: 2 actions

`_build_tactic_context(state, spatial) -> TacticContext` — bridge function that
constructs a `TacticContext` from the current `RoundState`. Confirm what
`TacticContext` requires by reading `pf2e/tactics.py`.

### Step 5: Implement evaluate_action() dispatcher

At the end of `pf2e/actions.py`, add:

```python
_ACTION_EVALUATORS: dict[ActionType, Callable] = {
    ActionType.END_TURN:             evaluate_end_turn,
    ActionType.RAISE_SHIELD:         evaluate_raise_shield,
    ActionType.PLANT_BANNER:         evaluate_plant_banner,
    ActionType.STRIDE:               evaluate_stride,
    ActionType.STEP:                 evaluate_step,
    ActionType.STRIKE:               evaluate_strike,
    ActionType.TRIP:                 evaluate_trip,
    ActionType.DISARM:               evaluate_disarm,
    ActionType.DEMORALIZE:           evaluate_demoralize,
    ActionType.CREATE_A_DIVERSION:   evaluate_create_a_diversion,
    ActionType.FEINT:                evaluate_feint,
    ActionType.SHIELD_BLOCK:         evaluate_shield_block,
    ActionType.INTERCEPT_ATTACK:     evaluate_intercept_attack,
    ActionType.ACTIVATE_TACTIC:      evaluate_activate_tactic,
}

def evaluate_action(
    action: Action,
    state: RoundState,
    spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Dispatch to the appropriate evaluator based on action.type.

    (AoN: see individual evaluators for rule citations)
    """
    evaluator = _ACTION_EVALUATORS.get(action.type)
    if evaluator is None:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason=f"No evaluator registered for {action.type}"
        )
    return evaluator(action, state, spatial)
```

### Step 6: Implement generate_candidates()

New function in `pf2e/actions.py` (or `sim/candidates.py` — choose based on
layering; note that candidate generation needs grid/spatial knowledge, which may
push it into `sim/`):

```python
def generate_candidates(
    state: RoundState,
    actor_name: str,
    spatial: SpatialQueries | None = None,
    bfs_cache: dict | None = None,
) -> list[Action]:
    """Generate all legal parameterized actions for actor_name in state.

    Checks eligibility before generating parameterized variants:
    - STRIKE: one Action per (weapon, target) pair within reach
    - STRIDE: one Action per candidate destination from 5-category heuristic
    - STEP: one Action per adjacent square
    - ACTIVATE_TACTIC: one Action per prepared tactic with sufficient actions
    - All others: one Action each (eligibility checked in evaluator)
    """
```

If `generate_candidates` needs spatial queries (it does, for STRIDE and STEP), it
belongs in `sim/` to avoid a layering violation (pf2e/ must not import from sim/).
Check the layering rules in ARCHITECTURE.md before placing this function.

### Step 7: Wire into simulate_round()

In `sim/search.py`, update `simulate_round()` to use the real `evaluate_action`
and `generate_candidates` callables instead of stubs.

Confirm the existing injection points by reading `sim/search.py`. Do not change
the beam search algorithm itself — only swap in the real callables.

Pass the BFS cache dict into `generate_candidates` at call time:
```python
bfs_cache = {}  # reset per beam_search_turn call
candidates = generate_candidates(state, actor_name, spatial, bfs_cache)
```

### Step 8: Create CLI entry point

**sim/cli.py** (under 80 lines):

```python
import argparse
import logging
from sim.scenario import load_scenario
from sim.search import simulate_round, format_recommendation

def main():
    parser = argparse.ArgumentParser(description="PF2e Tactical Simulator")
    parser.add_argument("--scenario", required=True, help="Path to .scenario file")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--debug-search", action="store_true",
                        help="Dump beam state per depth to stderr")
    args = parser.parse_args()

    if args.debug_search:
        logging.getLogger("sim.search").setLevel(logging.DEBUG)

    scenario = load_scenario(args.scenario)
    recommendations = simulate_round(scenario, seed=args.seed,
                                     debug=args.debug_search)
    for rec in recommendations:
        print(format_recommendation(rec))

if __name__ == "__main__":
    main()
```

**sim/__main__.py**:

```python
from sim.cli import main
main()
```

### Step 9: Implement RoundRecommendation and formatter

In `sim/search.py`, add:

```python
@dataclass
class RoundRecommendation:
    actor_name: str
    actions: list[str]                                # human-readable
    expected_score: float
    top_alternatives: list[tuple[list[str], float]]   # top 3
    reasoning: str                                    # 1-2 sentences

def format_recommendation(rec: RoundRecommendation) -> str:
    lines = [f"=== Recommendation for {rec.actor_name} ==="]
    lines.append(f"Best plan (EV {rec.expected_score:.2f}):")
    for i, action in enumerate(rec.actions, 1):
        lines.append(f"  {i}. {action}")
    if rec.top_alternatives:
        lines.append("\nAlternatives:")
        for alt_actions, alt_score in rec.top_alternatives:
            lines.append(f"  {' / '.join(alt_actions)}  (EV {alt_score:.2f})")
    lines.append(f"\nReasoning: {rec.reasoning}")
    return "\n".join(lines)
```

Add `--debug-search` logging in `beam_search_turn()`:

```python
logger = logging.getLogger("sim.search")

# At each depth:
if logger.isEnabledFor(logging.DEBUG):
    logger.debug(f"[SEARCH] Depth {depth}: {len(candidates)} candidates")
    for i, (score, plan) in enumerate(top_k[:5], 1):
        logger.debug(f"  #{i}  score={score:.2f}  actions={plan.action_labels}")
```

---

## Step 10: Write Tests

New test file: `tests/test_evaluators.py`

Write the following tests. Each test must be self-contained (no shared mutable state).

```python
# Helpers: build minimal RoundState with Aetregan + Bandit1 for most tests.
# Use make_aetregan(), make_rook() from sim/party.py.
# Use MockSpatialQueries for spatial.
```

### Group A: Snapshot blocker fields

```python
def test_combatant_snapshot_has_map_count():
    snap = CombatantSnapshot.from_combatant_state(make_rook_combat_state())
    assert snap.map_count == 0

def test_combatant_snapshot_has_conditions():
    snap = CombatantSnapshot.from_combatant_state(make_rook_combat_state())
    assert snap.conditions == frozenset()

def test_enemy_snapshot_has_conditions():
    enemy = EnemyState(...)  # minimal enemy
    snap = EnemySnapshot.from_enemy_state(enemy)
    assert snap.conditions == frozenset()
```

### Group B: Per-evaluator tests

For each evaluator, at minimum:

| Test | What to assert |
|---|---|
| `test_end_turn_always_eligible` | `result.eligible == True`, `score_delta == 0` |
| `test_plant_banner_ineligible_aetregan` | `eligible == False` |
| `test_raise_shield_eligible_with_shield` | eligible, score_delta > 0 |
| `test_raise_shield_ineligible_without_shield` | `eligible == False` |
| `test_raise_shield_ineligible_if_already_raised` | `eligible == False` |
| `test_step_only_adjacent_squares` | all destinations within 5 ft |
| `test_stride_respects_speed` | no destination beyond actor speed |
| `test_stride_aggressive_category` | candidate adjacent to enemy |
| `test_stride_defensive_category` | generated only when HP < 50% |
| `test_stride_banner_category_commander_only` | generated for Aetregan, not Rook |
| `test_stride_wounded_ally_category` | generated when ally below 50% HP |
| `test_strike_map0_no_penalty` | bonus used without MAP penalty |
| `test_strike_map1_minus5` | bonus reduced by 5 |
| `test_strike_map2_minus10` | bonus reduced by 10 |
| `test_strike_agile_map1_minus4` | agile weapon uses -4 not -5 |
| `test_strike_kill_branch_at_5pct` | two branches when P(kill) >= 5% |
| `test_trip_success_applies_prone` | prone in state_delta |
| `test_trip_crit_fail_actor_prone` | actor prone in state_delta |
| `test_trip_ineligible_out_of_reach` | `eligible == False` |
| `test_disarm_success_applies_penalty` | -2 attack penalty in state_delta |
| `test_disarm_crit_fail_actor_off_guard` | actor off-guard in state_delta |
| `test_demoralize_success_applies_frightened` | frightened_1 in state_delta |
| `test_demoralize_failure_sets_immune` | `"demoralize_immune"` in conditions |
| `test_demoralize_ineligible_when_immune` | `eligible == False` |
| `test_demoralize_no_deceptive_tactics` | uses Intimidation not Warfare Lore |
| `test_create_diversion_deceptive_tactics_aetregan` | uses Warfare Lore bonus |
| `test_create_diversion_failure_sets_immune` | `"diversion_immune"` in conditions |
| `test_create_diversion_ineligible_when_immune` | `eligible == False` |
| `test_feint_deceptive_tactics_aetregan` | uses Warfare Lore bonus |
| `test_feint_melee_only` | ineligible when target out of melee reach |
| `test_feint_requires_2_actions` | ineligible when `actions_remaining < 2` |
| `test_feint_no_immunity_on_failure` | no immunity tag added on failure |
| `test_shield_block_reduces_by_hardness` | damage reduced by 5 |
| `test_shield_block_ineligible_without_raised_shield` | `eligible == False` |
| `test_intercept_attack_guardian_only` | ineligible for non-Guardian |
| `test_intercept_attack_ally_in_range` | eligible when ally within 10 ft |
| `test_activate_tactic_strike_hard_ev` | score_delta matches evaluate_tactic() EV |
| `test_activate_tactic_insufficient_actions` | ineligible when actions_remaining < 2 |
| `test_activate_tactic_no_eligible_squadmates` | ineligible when no squadmates in aura |
```

### Group C: Regression and integration

```python
def test_strike_hard_ev_8_55_from_disk():
    """8th verification of the killer regression. Must not change."""
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    ctx = scenario.build_tactic_context()
    result = evaluate_tactic("strike_hard", ctx)
    assert abs(result.expected_value - 8.55) < 0.01

def test_full_round_from_scenario():
    """End-to-end: load → simulate_round() → RoundRecommendation."""
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    recommendations = simulate_round(scenario, seed=42)
    assert recommendations is not None
    assert len(recommendations) > 0
    aetregan_rec = next(
        r for r in recommendations if r.actor_name == "Aetregan"
    )
    assert aetregan_rec.expected_score > 0
```

New test file: `tests/test_cli.py`

```python
def test_cli_scenario_flag(tmp_path, capsys):
    """CLI runs without error and produces output."""
    from sim.cli import main
    import sys
    sys.argv = ["sim", "--scenario",
                "scenarios/checkpoint_1_strike_hard.scenario", "--seed", "42"]
    main()
    out = capsys.readouterr().out
    assert "Recommendation" in out

def test_cli_debug_search_flag(tmp_path, capsys):
    """--debug-search produces debug output to stderr."""
    from sim.cli import main
    import sys, logging
    sys.argv = ["sim", "--scenario",
                "scenarios/checkpoint_1_strike_hard.scenario",
                "--seed", "42", "--debug-search"]
    main()
    # Debug goes to logger; just verify no exception raised and output exists
    out = capsys.readouterr().out
    assert len(out) > 0
```

---

## Step 11: Run Full Regression

```bash
pytest tests/ -v
```

All 315 existing tests must pass. New tests should bring the total to approximately
361 (315 + 46). If the count is within 355–375, that is acceptable.

If any existing test fails, investigate before modifying it. The code is likely
wrong, not the test.

---

## Step 12: Verify Killer Regression

Confirm `test_strike_hard_ev_8_55_from_disk` passes. This is the 8th consecutive
verification. If EV has changed from 8.55, stop and investigate before continuing.

---

## Step 13: Update CHANGELOG.md

Add the following section:

```markdown
## [CP5.1.3c] — {date}
### Added
- 14 action evaluators in `pf2e/actions.py`: END_TURN, RAISE_SHIELD, PLANT_BANNER,
  STRIDE, STEP, STRIKE, TRIP, DISARM, DEMORALIZE, CREATE_A_DIVERSION, FEINT,
  SHIELD_BLOCK, INTERCEPT_ATTACK, ACTIVATE_TACTIC
- `evaluate_action()` dispatcher in `pf2e/actions.py`
- `generate_candidates()` function for candidate generation
- `RoundRecommendation` dataclass and `format_recommendation()` in `sim/search.py`
- `sim/cli.py` and `sim/__main__.py` — CLI entry point with `--scenario`,
  `--seed`, `--debug-search` flags
- `tests/test_evaluators.py` — 44 new evaluator tests
- `tests/test_integration.py` — end-to-end scenario test
- `tests/test_cli.py` — CLI smoke tests
- `map_count: int` and `conditions: frozenset[str]` fields on `CombatantSnapshot`
- `conditions: frozenset[str]` field on `EnemySnapshot`
- Ever Ready (Guardian) initialization comment in `sim/initiative.py`

### Rules verified
- Feint failure: no immunity (AoN: https://2e.aonprd.com/Skills.aspx?ID=38)
- Disarm crit failure: actor off-guard (AoN: https://2e.aonprd.com/Actions.aspx?ID=2300)
- Flanking: off-guard in Remaster (AoN: https://2e.aonprd.com/Rules.aspx?ID=2361)
- Ever Ready: passive feature, not an evaluator (AoN: https://2e.aonprd.com/Classes.aspx?ID=67)

### Regressions
- Strike Hard EV 8.55 (8th consecutive verification)
```

---

## Step 14: Update current_state.md

Update `.claude/context/current_state.md`:

```markdown
## Current State

**Checkpoint:** CP5.1.3c complete
**Tests:** ~361 passing
**Last commit:** {commit hash}
**Killer regression:** Strike Hard EV 8.55 (8th verification)

**Modules added this checkpoint:**
- `pf2e/actions.py` — 14 evaluators + dispatcher
- `sim/cli.py`, `sim/__main__.py` — CLI entry point
- `tests/test_evaluators.py`, `tests/test_integration.py`, `tests/test_cli.py`

**Next checkpoint:** CP5.2 — Class features (Dalai Anthem, Erisen Mortar, Rook Taunt)

**Known simplifications (CP6 calibration targets):**
- RAISE_SHIELD danger estimation: Σ enemy_damage × P(targets_actor) × 0.10
- STRIDE flanking: no LoS check
- CREATE_A_DIVERSION: next-turn off-guard carry-over not scored
- DISARM crit success: approximated as -2 penalty (item drop not modeled)
- SHIELD_BLOCK: shield breakage not modeled
```

---

## Common Pitfalls

1. **Layering violation:** `generate_candidates` needs spatial queries. If it lives
   in `pf2e/`, it cannot import from `sim/`. Place it in `sim/` if it needs
   `SpatialQueries` from `sim/grid_spatial.py`. Check ARCHITECTURE.md.

2. **MAP for reactions:** Reactive Strikes (INTERCEPT_ATTACK triggering a Strike)
   use `map_count=0` regardless of the actor's current MAP. Do not use
   `actor_snap.map_count` for reactions.

3. **frozenset union semantics:** `frozenset | {c}` creates a new frozenset. Do not
   mutate in place — `CombatantSnapshot` fields are effectively immutable via the
   `with_pc_update()` pattern.

4. **evaluate_tactic() interface:** Confirm what `TacticContext` requires before
   writing `_build_tactic_context()`. The context needs spatial queries, party
   state, and enemy state. Read `pf2e/tactics.py` carefully.

5. **Existing boolean conditions:** `off_guard`, `prone`, `shield_raised`, and
   `frightened` remain as hardcoded boolean/int fields. Do NOT migrate them to the
   `conditions` frozenset. The frozenset is additive, not a replacement.

6. **Test isolation:** Each test must build its own `RoundState`. Do not share
   mutable state between tests.

7. **BFS cache scope:** The BFS cache dict must not persist across beam search
   calls. Create it fresh at the start of each `beam_search_turn()` invocation.

---

## Validation Checklist

Before committing, confirm all of the following:

- [ ] `map_count` field present on `CombatantSnapshot`, defaults to 0
- [ ] `conditions` frozenset present on `CombatantSnapshot` and `EnemySnapshot`
- [ ] `apply_outcome_to_state` correctly unions new condition strings
- [ ] Ever Ready comment added in `sim/initiative.py`
- [ ] All 14 evaluators implemented in `pf2e/actions.py`
- [ ] `evaluate_action()` dispatcher registered for all 14 `ActionType` values
- [ ] EVER_READY is NOT in the dispatcher (removed from evaluator list)
- [ ] `generate_candidates()` implemented and wired into `simulate_round()`
- [ ] BFS cache scoped to single `beam_search_turn()` call
- [ ] `sim/cli.py` exists, `--scenario`, `--seed`, `--debug-search` flags work
- [ ] `sim/__main__.py` exists, `python -m sim --scenario ... ` runs
- [ ] `RoundRecommendation` dataclass defined
- [ ] `format_recommendation()` produces readable output
- [ ] `--debug-search` produces beam state in logging output (stderr)
- [ ] `tests/test_evaluators.py` exists with 44+ tests
- [ ] `tests/test_integration.py` exists with at least 1 test
- [ ] `tests/test_cli.py` exists with 2 tests
- [ ] `pytest tests/ -v` passes all ~361 tests
- [ ] `test_strike_hard_ev_8_55_from_disk` passes (8th verification)
- [ ] `CHANGELOG.md` updated
- [ ] `.claude/context/current_state.md` updated with new test count and commit hash
- [ ] Commit pushed