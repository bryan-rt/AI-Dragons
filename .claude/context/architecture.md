# Architecture

## Layering Rules

Two Python packages, strict unidirectional dependency:

```
sim/   (simulator layer)
  ↓ imports
pf2e/  (rules engine)
```

**pf2e/ must not import from sim/.** This is non-negotiable. pf2e/ is a pure rules engine that could theoretically be extracted into a standalone library. sim/ builds on top.

**Tests import from both packages freely.**

---

## CP10: Nine-Layer Architecture (Current Rebuild)

As of CP10, the engine is being rebuilt around a nine-layer system. Each layer is a distinct checkpoint with its own module. Every layer from CP10.2 onward depends on earlier layers. All 578 existing tests must pass at every sub-checkpoint.

```
Layer 1: Roll Foundation      pf2e/rolls.py          ← CP10.1 NEXT
Layer 2: Trait System         pf2e/traits.py          ← CP10.2
Layer 3: Modifier Assembly    pf2e/modifiers.py       ← CP10.3
Layer 4: Chassis (×6)         pf2e/contest_roll.py    ← CP10.4.1
                              pf2e/auto_state.py      ← CP10.4.2
                              pf2e/strike.py          ← CP10.4.3
                              pf2e/save_damage.py     ← CP10.4.4
                              pf2e/save_condition.py  ← CP10.4.5
                              pf2e/movement.py        ← CP10.4.6
Layer 5: Condition State      pf2e/conditions.py      ← CP10.5
Layer 6: Spatial/Positional   extend sim/grid*.py     ← CP10.6
Layer 7: Detection/Visibility pf2e/detection.py       ← CP10.7
Layer 8: Damage Resolution    extend damage_pipeline  ← CP10.8
Layer 9: Death/Dying          extend round_state      ← CP10.9
```

### Two-Layer Chassis Design

Every action definition carries both layers simultaneously:

```
Layer 1 (Traits): cross-cutting rules
  traits: frozenset[str]
  → attack    : MAP increments, Reactive Strike trigger
  → manipulate: Reactive Strike trigger, grabbed flat check
  → flourish  : one per round limit
  → open      : requires map_count == 0
  → press     : requires map_count > 0
  → mental    : constructs/undead immune
  → emotion   : constructs immune
  → incap     : degree shift vs higher level targets
  → auditory  : deaf targets immune
  → visual    : blind targets immune

Layer 2 (Chassis): computation type
  → ContestRoll  : skill roll vs target DC → four degree effects
  → AutoState    : deterministic state change, no roll
  → Strike       : attack roll vs AC → damage
  → BasicSave    : save → damage fractions (0/half/full/double)
  → NonBasicSave : save → condition by degree
  → Movement     : position change with optional embedded check
```

Evaluation pipeline: trait-driven eligibility → chassis-driven eligibility → chassis math → trait post-processing.

---

## Package: pf2e/ (Current State + CP10 Additions)

### pf2e/types.py
Core enums and value types. Zero dependencies on other pf2e/ modules.
- `Ability`, `ProficiencyRank`, `WeaponCategory`, `WeaponGroup`, `DamageType`, `SaveType`, `Skill` enums
- `SKILL_ABILITY` lookup dict

### pf2e/abilities.py
`AbilityScores` dataclass. `mod()` and `score()` methods. Immutable.

### pf2e/proficiency.py
`proficiency_bonus(rank, level)` — 0 for untrained, rank.value + level otherwise.

### pf2e/equipment.py
Equipment data types. All frozen: `Weapon`, `WeaponRunes`, `EquippedWeapon`, `ArmorData`, `Shield`.

### pf2e/character.py
- `Character` — frozen dataclass, immutable build
- `CombatantState` — mutable per-round state
- `EnemyState` — mutable enemy state

### pf2e/combat_math.py
Core rules engine. All derivation functions.
- `D20Outcomes` dataclass, `enumerate_d20_outcomes(bonus, dc)` — load-bearing primitive
- Attack math, save math, AC, speed, HP, MAP, mortar/AoE, defensive math
- `skill_bonus()`, `lore_bonus()`, `spell_attack_bonus()`

### pf2e/tactics.py
Commander tactic system. Five evaluators, folio/prepared dicts.

### pf2e/actions.py
`ActionType` enum (extended through CP5.4). All current action evaluators. Will be refactored into chassis modules in CP10.4.

### pf2e/spells.py
`SpellDefinition`, `SpellPattern` enum, `SPELL_REGISTRY`. Fear, Force Barrage, Needle Darts.

### pf2e/damage_pipeline.py
Strict PF2e damage resolution order. `resolve_strike_outcome()`. Resolution chain: Intercept Attack → Shield Block → Resistance → Temp HP → Real HP.

### pf2e/effects/__init__.py
Placeholder module. Handler registry deferred until first handler needed (D30).

### pf2e/rolls.py ← NEW CP10.1
- `RollType` enum: `STANDARD | FLAT`
- `FortuneState` enum: `NORMAL | FORTUNE | MISFORTUNE | CANCELLED`
- `flat_check(dc: int) -> float` — P(d20 ≥ dc), no modifiers ever, clamped [0.0, 1.0]
- `FortuneState.combine(has_fortune, has_misfortune)` helper

### pf2e/traits.py ← NEW CP10.2
- `TraitDef`, `MechanicalCategory` enum, `TRAIT_DEFINITIONS` registry
- `check_trait_immunity(action_traits, target_immunity_tags) -> bool`
- Flourish/Open/Press checking helpers

### pf2e/modifiers.py ← NEW CP10.3
- `BonusType` enum: `CIRCUMSTANCE | STATUS | ITEM | PROFICIENCY | UNTYPED`
- `BonusTracker` class: same-type bonuses → highest only; untyped penalties → all stack

### pf2e/contest_roll.py ← NEW CP10.4.1
- `ContestRollDef`, `CONTEST_ROLL_REGISTRY`
- `evaluate_contest_roll()` — single evaluator for all contest-roll actions

### pf2e/auto_state.py ← NEW CP10.4.2
- `AutoStateChangeDef`, `AUTOSTATE_REGISTRY`
- `evaluate_auto_state()` — single evaluator

### pf2e/strike.py ← NEW CP10.4.3
Unified strike evaluator for PC strikes, spell attack rolls, enemy strikes, ranged strikes.

### pf2e/save_damage.py ← NEW CP10.4.4
Unified basic-save damage evaluator (single-target and AoE).

### pf2e/save_condition.py ← NEW CP10.4.5
Non-basic save → condition by degree. Incapacitation degree-shift.

### pf2e/movement.py ← NEW CP10.4.6
Unified movement evaluator. Crawl, Balance, Tumble Through.

### pf2e/conditions.py ← NEW CP10.5
Full condition taxonomy. Override hierarchy. Turn-based processing.

### pf2e/detection.py ← NEW CP10.7
Four-state detection: OBSERVED | CONCEALED | HIDDEN | UNDETECTED | UNNOTICED.

---

## Package: sim/

### sim/grid.py
Grid geometry. `Pos`, `GridState`, `distance_ft` (5/10 diagonal), `chebyshev_squares`, `is_adjacent`, `is_within_reach`, `squares_in_emanation`, `shortest_movement_cost` (BFS), `parse_map`, `render_map`. Will gain `are_flanking()` in CP10.6.

### sim/grid_spatial.py
`GridSpatialQueries` implementing `SpatialQueries` Protocol. Handles carried/planted banner. Will gain cover and flanking queries in CP10.6.

### sim/party.py
Canonical character factories. `TOKEN_TO_FACTORY`, weapon/armor constants. Factories now delegate to Foundry importer.

### sim/scenario.py
`Scenario` frozen dataclass. `load_scenario()`, `parse_scenario()`. `build_tactic_context()`.

### sim/round_state.py
`CombatantSnapshot` (frozen, ~20 fields), `EnemySnapshot` (frozen), `RoundState` with shallow-clone branching. Will gain `dying`, `wounded`, `doomed` in CP10.9.

### sim/search.py
Beam search K=50/20/10 depth 3. Adversarial enemy sub-search K=20/10/5. `score_state()`, `simulate_round()`, `RoundRecommendation`, `format_recommendation()`, `run_simulation()`.

### sim/candidates.py
`generate_candidates(state, actor_name)` — action candidate generation per character.

### sim/solver.py
Full combat solver. `solve_combat()`, `CombatSolution`, `RoundLog`, `TurnLog`.

### sim/initiative.py
`roll_initiative()` — seeded isolated RNG, partial override, enemy-beats-PC tiebreaker.

### sim/importers/foundry.py
Foundry actor JSON importer. Populates `Character` from `characters/fvtt-*.json` exports.

### sim/catalog/
Session cache and GitHub fetcher for Rule Element analysis. Not in hot path.

### sim/cli.py + sim/__main__.py
CLI entry point. `python -m sim --scenario X --seed 42 --debug-search`.

---

## Directory: scenarios/
Text files in `.scenario` format. `checkpoint_1_strike_hard.scenario` — canonical regression scenario (EV 7.65).

## Directory: characters/
Foundry JSON exports: `fvtt-aetregan.json`, `fvtt-rook.json`, `fvtt-dalai.json`, `fvtt-erisen.json`. Authoritative character data.

## Directory: tests/
Tests mirror production structure. `tests/fixtures.py` is a backward-compat shim re-exporting from `sim/party.py`.

---

## Design Principles

### Derive, don't store
Every combat number computed from character + state. No pre-baked values except max HP and static equipment stats.

### Frozen build, mutable state
`Character` is immutable. `CombatantSnapshot` is mutable per-round state.

### Protocol-based spatial queries
`SpatialQueries` Protocol with `MockSpatialQueries` (tests) and `GridSpatialQueries` (real grid).

### Standard library + pytest only
No third-party dependencies in production code.

### Outcome buckets
Each Strike is `{miss, hit, crit}` with explicit probabilities. Not full PMF.

### Hybrid state threading
Kill/drop events branch the search tree. Everything else collapses to EV.

### CP10 addition: Two-layer chassis
Traits handle cross-cutting rules (MAP, immunity, flourish). Chassis handles computation type. Neither layer knows about the other's concerns.

---

## Layering Violations to Watch For

- `pf2e/` importing from `sim/` — never.
- Traits knowing about chassis computation — never.
- Chassis knowing about specific characters by name — never (takes `Character` or `CombatantSnapshot`).
- `tests/fixtures.py` adding new logic — it's a shim, new logic goes in `sim/party.py`.
- Characters knowing about grids — no. Position lives on `CombatantSnapshot`.
- Combat math functions receiving character names — no. They take `Character` or `CombatantState`, never a `str`.
