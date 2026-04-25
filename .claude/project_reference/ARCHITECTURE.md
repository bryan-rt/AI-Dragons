# Architecture

## Layering Rules

Two Python packages, strict unidirectional dependency:

```
sim/   (simulator layer)
  ↓ imports
pf2e/  (rules engine)
```

**pf2e/ must not import from sim/.** This is non-negotiable. pf2e/ is a pure rules engine that could theoretically be extracted into a standalone library. sim/ builds on top.

**Tests import from both packages freely.** Tests are allowed to know about both layers.

## Package: pf2e/

Pure Pathfinder 2e Remaster rules. No knowledge of grids, scenarios, simulation, or games. Numbers are derived from underlying character data, never pre-baked.

### pf2e/types.py
Core enums and value types. No logic, no dependencies on other pf2e/ modules.
- `Ability` enum (STR, DEX, CON, INT, WIS, CHA)
- `ProficiencyRank` enum (UNTRAINED=0, TRAINED=2, EXPERT=4, MASTER=6, LEGENDARY=8)
- `WeaponCategory`, `WeaponGroup`, `DamageType`, `SaveType` enums
- `Skill` enum (16 standard skills — added CP5.1 3a)
- `SKILL_ABILITY` lookup dict mapping skill to its key ability

### pf2e/abilities.py
`AbilityScores` dataclass with `mod()` and `score()` methods. Immutable.

### pf2e/proficiency.py
`proficiency_bonus(rank, level)` — returns 0 for untrained, rank.value + level otherwise.

### pf2e/equipment.py
Equipment data types. All frozen:
- `Weapon` — intrinsic properties (no wielder, no runes)
- `WeaponRunes` — potency, striking, property runes
- `EquippedWeapon` — Weapon + Runes pairing
- `ArmorData` — AC bonus, dex cap, penalties
- `Shield` — AC bonus, hardness, HP

### pf2e/character.py
- `Character` — frozen dataclass, immutable build
- `CombatantState` — mutable per-round state wrapping a Character
- `EnemyState` — mutable enemy state (separate from CombatantState; enemies have different data)

### pf2e/combat_math.py
All derivation functions. This is the core rules engine.
- `enumerate_d20_outcomes(bonus, dc)` — the load-bearing primitive
- `D20Outcomes` dataclass (crit_success, success, failure, crit_failure counts summing to 20)
- Attack math: `attack_ability`, `attack_bonus`, `damage_ability_mod`, `damage_avg`, `expected_strike_damage`
- Saves: `save_bonus`, `class_dc`, `perception_bonus`, `skill_bonus`, `lore_bonus`
- AC: `armor_class`
- Speed: `effective_speed`
- Helpers: `die_average`, `melee_reach_ft`, `map_penalty`, `max_hp`
- Siege/AoE: `SiegeWeapon`, `EnemyTarget`, `expected_aoe_damage`, `siege_save_dc`
- Defensive math (CP4): `plant_banner_temp_hp`, `guardians_armor_resistance`, `temp_hp_ev`, `expected_incoming_damage`, `expected_enemy_turn_damage`

### pf2e/tactics.py
Commander tactic system.
- `TacticDefinition` — frozen declarative description
- `TacticContext` — everything an evaluator needs at call time
- `TacticResult` — evaluator output (EV, conditions, justification, etc.)
- `SpatialQueries` Protocol — abstract spatial interface
- `MockSpatialQueries` — test double
- Five tactic constants: `STRIKE_HARD`, `GATHER_TO_ME`, `TACTICAL_TAKEDOWN`, `DEFENSIVE_RETREAT`, `MOUNTAINEERING_TRAINING`, `SHIELDS_UP`
- `FOLIO_TACTICS` dict (5 entries — Defensive Retreat replaced with Shields Up! in CP4.5)
- `PREPARED_TACTICS` tuple (3 entries)
- Five evaluators: `_evaluate_reaction_strike`, `_evaluate_reaction_stride`, `_evaluate_stride_half`, `_evaluate_free_step`, `_evaluate_passive_buff`, `_evaluate_reaction_raise_shield` (stub)
- `intercept_attack_ev()` — standalone helper for Guardian reaction (not wired into tactic dispatcher)

### pf2e/actions.py (added CP5.1 3a)
- `ActionType` enum (15 types)
- `Action` — frozen instance of an action type with parameters
- `ActionOutcome` — one probability-weighted branch of an action's outcome tree
- `ActionResult` — evaluator output: eligibility + list of outcomes

### pf2e/damage_pipeline.py (added CP5.1.3b)
Strict PF2e damage resolution order. Key function: `resolve_strike_outcome()`. Resolution chain: Intercept Attack → Shield Block → Resistance → Temp HP → Real HP.

## Package: sim/

Simulation layer. Knows about grids, scenarios, search algorithms. Depends on pf2e/ for all rules questions.

### sim/grid.py
Grid geometry. No dependency on pf2e/.
- `Pos = tuple[int, int]` type alias
- `GridState` — terrain only (walls, dimensions)
- `distance_ft` (5/10 diagonal alternation)
- `chebyshev_squares`, `is_adjacent`, `is_within_reach` (with 10-ft reach Chebyshev special case)
- `squares_in_emanation` — area geometry
- `shortest_movement_cost` — BFS pathfinding (uniform 5-ft step cost simplification)
- `parse_map`, `render_map` — ASCII grid I/O

### sim/grid_spatial.py
Real `SpatialQueries` implementation backed by `GridState` + combatant positions.
- `GridSpatialQueries` class implementing `SpatialQueries` Protocol
- Handles carried banner (aura follows commander) and planted banner (aura fixed at planted position)
- Precomputes occupied squares for BFS
- Banner square is passable (item, not creature)

### sim/party.py
Canonical character factories and equipment constants.
- `TOKEN_TO_FACTORY` mapping grid tokens (c, g, b, i) to factory functions
- `COMMANDER_TOKEN`, `SQUADMATE_TOKENS`
- Character factories: `make_aetregan`, `make_rook`, `make_dalai`, `make_erisen`
- `make_rook_combat_state()` applies full plate speed penalty
- Weapon constants: `WHIP`, `SCORPION_WHIP`, `LONGSWORD`, `RAPIER`, `JAVELIN`, `DAGGER`
- Armor constants: `SUBTERFUGE_SUIT`, `FULL_PLATE`, `LEATHER_ARMOR`, `STUDDED_LEATHER`
- Shield: `STEEL_SHIELD`

### sim/scenario.py
Scenario file loading.
- `Scenario` frozen dataclass
- `ScenarioParseError`
- `load_scenario(path)`, `parse_scenario(text)`
- `Scenario.build_tactic_context()` — ready-to-evaluate TacticContext with GridSpatialQueries wired in
- File format: `[meta]`, `[grid]`, `[banner]`, `[anthem]`, `[enemies]`, `[initiative]` sections

### sim/round_state.py (added CP5.1.3b)
- `CombatantSnapshot` (16 fields, frozen) — PC per-round state
- `EnemySnapshot` (14 fields, frozen) — enemy per-round state
- `RoundState` (frozen) with `from_scenario`, `with_pc_update`, `with_enemy_update` — shallow-clone branching via `dataclasses.replace()`

### sim/search.py (added CP5.1.3b)
- `SearchConfig` dataclass
- `beam_search_turn()` — per-character beam search K=50/20/10 depth 3
- `adversarial_enemy_turn()` — enemy sub-search K=20/10/5 with sign-flipped scoring
- `simulate_round()` — full-round evaluation
- `score_state`, `ScoreBreakdown`, `TurnPlan`

### sim/initiative.py (added CP5.1.3b)
`roll_initiative()` — seeded isolated RNG over Perception + d20, partial override support, enemy-beats-PC tiebreaker, alphabetical same-side.

## Directory: scenarios/

Text files in the `.scenario` format. Version-controlled. Examples:
- `checkpoint_1_strike_hard.scenario` — canonical validation scenario; killer regression test uses this

## Directory: characters/

Character JSON data. Canonical storage for party members.
- `aetregan.json` — Pathbuilder JSON export (authoritative)
- `rook.json`, `dalai.json`, `erisen.json` — grounded defaults, may be reconciled with Pathbuilder JSONs later

When CP5.1.4 (Pathbuilder importer mini-checkpoint) ships, `sim/party.py` factories become thin wrappers reading these JSONs.

## Directory: tests/

Tests mirror production structure. Test file `test_X.py` tests `X.py`.
- `tests/fixtures.py` — re-exports canonical party from `sim/party.py` (backward-compat shim)
- `tests/conftest.py` (if needed) — pytest configuration

## Design Principles (the "why")

### Derive, don't store
Every combat number (AC, attack bonus, save DC, class DC, skill bonus) is computed from character build + transient state. No pre-baked values. Exception: max HP and static equipment stats.

**Why:** Correctness. When state changes (off-guard applied, shield raised), the next call re-derives with the new state. No staleness bugs.

### Frozen build, mutable state
`Character` is frozen (immutable build data). `CombatantState` is mutable (per-round transient state).

**Why:** Clear separation of "what the character is" vs "what's happening to them right now." A single character can participate in multiple combat states simultaneously (hypotheticals in search trees).

### Protocol-based spatial queries
`SpatialQueries` is a Protocol. `MockSpatialQueries` for tests, `GridSpatialQueries` for real grids.

**Why:** Tactics evaluation is independent of grid implementation. Can test tactics logic without grid setup. Can also swap grid implementations later (e.g., a 3D grid for vertical combat) without touching tactics.

### Standard library + pytest only
No third-party dependencies in production code.

**Why:** Easy to deploy, no version conflicts, no rug-pulls from upstream maintainers. This project will be around for years; minimize external failure surface.

### Outcome buckets for damage distributions
Not full damage PMFs, not Gaussian approximation. Each Strike is {miss, hit, crit} with explicit probabilities.

**Why:** Captures the variance that matters (does this crit change a kill outcome?) at tractable compute cost. Full PMF is 5-10x more expensive for small accuracy gains. Gaussian is wrong at tails where P(kill) lives.

### Hybrid state threading
Kill/drop events branch the search tree (correct for the discontinuities that actually change subsequent action space). Everything else collapses to EV (fast).

**Why:** The tree stays small (~4-16 branches per search node instead of 10^6). Accuracy preserved where it matters. See CP5.1 Pass 2 for full reasoning.

## Phase B / Phase B+ Extension Points

Three planned expansions of this architecture have already been accounted for in the current design. Each is documented here so that when its checkpoint activates, the agent knows what to touch and what to leave alone.

### CP5.1.4 — Pathbuilder importer (Phase B)
`Character` instances will be JSON-loaded instead of factory-built. No internal changes to `Character`, `CombatantState`, or any derivation function. The importer lives in a new `sim/importers/pathbuilder.py` module, and `sim/party.py` factory functions become thin wrappers around it reading from `characters/<name>.json`. Feat flags (`has_plant_banner`, `has_deceptive_tactics`) remain hard-coded booleans — the importer just sets them from known feat names in the JSON. See D28 for the move from post-CP9 to post-CP5.1.3c.

### Phase B+ — Catalog-driven effects
Effect resolution migrates from hard-coded `has_X` flags to registry-driven catalog queries. The refactor is bounded to the ~5–10 sites that currently check flags. The catalog (SQLite file at `pf2e/data/catalog.sqlite` per D26) is generated by a `tools/build_catalog.py` script reading the Foundry VTT pf2e source (D25). Effect handlers live in a Python registry (e.g., `pf2e/effects/registry.py`), keyed by `effect_kind` — not stored in data rows (D27). Post-CP9.

### Phase B-adjacent — EnemyState unification
`EnemyState` should merge into `CombatantState` once the bestiary importer lands. Today they're separate because enemies were quick stubs in CP4 — adequate for the scenarios we've built, but they can't participate in auras or conditions the way PCs do. Unifying them enables symmetric treatment in adversarial sub-search and future bestiary imports. Flagged in DECISIONS.md non-decisions; not urgent.

## Layering Violations to Watch For

- `pf2e/` importing from `sim/` — never. Refactor.
- `tests/fixtures.py` adding new logic — it's a shim. New logic goes in `sim/party.py`.
- Characters knowing about grids — no. Position lives on `CombatantState`, not `Character`.
- Combat math functions knowing about specific characters by name — no. They take `Character` or `CombatantState`, never care what name is on it.
