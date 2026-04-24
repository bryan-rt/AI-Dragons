# Roadmap

Status at time of last update: CP5.1.3a complete (255 tests). CP4.6 and CP4.7 restructuring/methodology work complete. CP5.1.3b pending brief.

Update this document whenever a checkpoint ships or a major decision shifts the plan.

## Completed Checkpoints

### CP0 — Foundation Types (pre-history)
Initial data model: `Character`, `CombatantState`, `AbilityScores`, enums for ability/proficiency/save types. Establishes the "derive, don't store" philosophy.

### CP0.5 — Foundation Cleanup
Bug fixes and rule corrections caught during foundation review. Key corrections:
- Aetregan Wis 11 → 12 (attribute boosts are +2, not +1)
- Mortar EV 5.95 (not 5.60; boundary ≤ includes equality)
- Various save bonuses corrected by ability-mod derivation
- Weapon classification fixes (is_ranged includes thrown weapons)
- Dagger range_increment=10 (matching actual PF2e stats)

### CP1 — Tactic Dispatcher
Implementation: 97 → 123 tests.
- `pf2e/tactics.py` with `TacticDefinition`, `TacticContext`, `TacticResult`
- `SpatialQueries` Protocol, `MockSpatialQueries` for tests
- Five folio tactics defined: Strike Hard!, Gather to Me!, Tactical Takedown, Defensive Retreat, Mountaineering Training
- Dispatcher via `evaluate_tactic()` and `evaluate_all_prepared()`
- Killer test: Strike Hard EV 8.55 established

### CP2 — Grid and Spatial Reasoning
Implementation: 123 → 171 tests.
- `sim/grid.py`: `Pos`, `GridState`, `parse_map`, `render_map`, `distance_ft` (5/10 diagonal)
- `sim/grid_spatial.py`: `GridSpatialQueries` implementing `SpatialQueries`
- BFS pathfinding via `shortest_movement_cost`
- Banner is an item (passable square), not a creature
- 10-ft reach Chebyshev special case (whip can hit diagonal 2 squares)
- Killer swap test: same EV 8.55 from Mock and Real spatial queries

### CP3 — Scenario Loading
Implementation: 171 → 181 tests.
- `sim/scenario.py`: `Scenario` dataclass, `parse_scenario`, `load_scenario`
- `sim/party.py`: factories and tokens moved from tests/fixtures.py (backwards-compat shim retained)
- File format: sections-based text with [meta], [grid], [banner], [anthem], [enemies]
- Canonical scenario: `scenarios/checkpoint_1_strike_hard.scenario`
- Killer validation: load from disk → Strike Hard EV 8.55

### CP4 — Defensive Value Computation
Implementation: 181 → 199 tests.
- Correctness fix: Planted banner aura expands 30-ft → 40-ft per Plant Banner feat
- `GridSpatialQueries.__init__` now requires `banner_planted: bool` (no default)
- `EnemyState` extended with offensive stats: `attack_bonus`, `damage_dice`, `damage_bonus`, `num_attacks_per_turn`
- New math helpers in `combat_math.py`: `plant_banner_temp_hp`, `guardians_armor_resistance`, `expected_incoming_damage`, `expected_enemy_turn_damage`, `temp_hp_ev`
- `TacticResult.damage_prevented_sources` dict with canonical keys
- Gather to Me and Defensive Retreat now compute defensive EV
- `intercept_attack_ev()` standalone helper (not yet wired into tactic evaluators; CP5 will call it)

### CP4.5 — Aetregan Reconciliation
Implementation: 199 → 207 tests.
- Reconciled `make_aetregan()` against actual Pathbuilder JSON:
  - Cha 12 → 10
  - Perception trained → expert (+6, not +4)
  - Weapon: Whip → Scorpion Whip (lethal, no nonlethal trait)
- HP infrastructure: `Character.ancestry_hp`, `Character.class_hp`, `max_hp()` helper
- Aetregan HP: 15 (Elf 6 + Commander 8 + Con 1)
- Folio composition: removed `defensive_retreat` from `FOLIO_TACTICS`, added `shields_up` as stub (evaluator returns ineligible)
- Carried banner support: `GridSpatialQueries.is_in_banner_aura` now handles `banner_planted=False` — aura follows commander at 30-ft radius
- Scenario parser accepts `planted = false`
- Canonical scenario updated to `planted = false` (Aetregan doesn't have Plant Banner at L1)
- Strike Hard EV 8.55 regression preserved

### CP5.1.3a — Foundation
Implementation: 207 → 255 tests.
- `Skill` enum (16 skills) and `SKILL_ABILITY` lookup in `pf2e/types.py`
- `Character` extensions: `skill_proficiencies`, `lores`, feat-presence flags
- `skill_bonus()` and `lore_bonus()` helpers in `pf2e/combat_math.py`
- Aetregan full skill data from JSON (10 trained, 6 untrained, 2 lores)
- Squadmate HP and skill grounded defaults (Rook 23, Dalai 17, Erisen 16)
- `ActionType` enum (15 types), `Action`, `ActionOutcome`, `ActionResult` in new `pf2e/actions.py`
- `CombatantState` HP tracking: `current_hp`, `temp_hp`, `actions_remaining`
- `EnemyState` extensions: `max_hp`, `current_hp`, `perception_bonus`, `perception_dc`
- Scenario parser `[initiative]` section support

### CP4.6 — Repo Restructuring
255 tests preserved (no code changes).
- `CLAUDE.md` at repo root for CLI agent context
- `.claude/context/` for agent-facing reference docs
- `.claude/project_reference/` as version-controlled mirror of Claude Project knowledge
- `.claude/briefs/` scaffolding for historical brief archive
- `characters/` directory with aetregan.json canonical data
- Removed `project_restructure_docs/` staging directory

### CP4.7 — Methodology Hardening
255 tests preserved (no code changes).
- Fixed `characters/README.md` content bug from CP4.6
- Populated `.claude/briefs/` scaffolding
- Added "Core Engineering Philosophy" section to `PROJECT_INSTRUCTIONS.md`
- Structural three-pass methodology in `PROJECT_INSTRUCTIONS.md` mirrors `CLAUDE.md`
- Logging and diagnostic output conventions added to `conventions.md`

## In Progress

CP5.1.3b — Algorithms (pending brief).

## Pending Checkpoints

### CP5.1.3b — Algorithms
- `RoundState` with shallow-clone + frozenset conditions
- Hybrid state threading: EV-collapse by default, branching at kill/drop crossings with 5% threshold
- `sim/search.py`: beam search K=50/20/10 depth 3
- Adversarial enemy sub-search (K=20, depth 3)
- Scoring function: `kill_value = max_hp + 10 × num_attacks`, `drop_cost = max_hp + 10 × role_multiplier` (Dalai = 2x)
- Initiative rolling from Perception, seeded
- Damage pipeline in `pf2e/damage_pipeline.py` (strict PF2e resolution order)

### CP5.1.3c — Actions
Fifteen action evaluators:
1. STRIDE (with 5-category destination heuristic + "adjacent to wounded ally")
2. STEP
3. STRIKE
4. TRIP
5. DISARM
6. RAISE_SHIELD
7. SHIELD_BLOCK (reaction)
8. PLANT_BANNER (stub for Aetregan; evaluator ineligible at L1)
9. ACTIVATE_TACTIC (wraps existing `evaluate_tactic()`)
10. DEMORALIZE
11. CREATE_A_DIVERSION (uses Warfare Lore for Aetregan via Deceptive Tactics)
12. FEINT (same)
13. INTERCEPT_ATTACK (reaction, Guardian-specific)
14. EVER_READY (Guardian reaction refresh)
15. END_TURN

Plus:
- `--debug-search` CLI flag that dumps beam state per depth
- Output formatter for `RoundRecommendation`
- End-to-end integration test: load scenario → run full round → produce recommendation
- Strike Hard EV 8.55 regression (7th verification)

### CP5.2 — Class Features
- Dalai: Courageous Anthem, Soothe spell, Inspire Defense composition
- Erisen: Light Mortar siege action, Overdrive Inventor feature
- Rook: Taunt, Intercept Attack full evaluator, Ever Ready refresh
- Healing actions
- Composition/cantrip/spell action types

### CP5.3 — General Skill Actions
- Aid action (pre-declare + roll + bonus)
- Recall Knowledge (per-skill variants)
- Seek, Hide, Sneak
- More skill feat variants

### CP6 — Multi-Round and Refinements
- Multi-round simulation ("run 3 rounds")
- Expectimax enemy search (top-3 plans)
- Full optimal reaction timing
- Scoring weight calibration from CP7 feedback

### CP7 — Validation Sweep
- Validate against original Python prototype's recommendations
- Sanity checks across Outlaws of Alkenstar AP scenarios
- Tune anything that feels wrong

### CP8 — L5 Forward Compatibility
- Character advancement (L2, L3, L4, L5)
- Feat progression at each level
- Class DC scaling
- Aetregan's planned L2 Plant Banner upgrade (flips `has_plant_banner=True`, scenarios can set `planted=true`)

### CP9 — Real AP Scenarios
- Encode actual Outlaws of Alkenstar encounters
- Produce recommendations for Bryan's upcoming sessions
- "Done" milestone for the simulator

## Post-Simulator Phases (Speculative)

Not committed. Evaluate after CP9 ships.

### Phase B — Pathbuilder Importer
JSON parser that reads Pathbuilder's export format, produces `Character` objects. Unknown feats flagged but character still usable. ~1-2 weekends.

### Phase B+ — Effects Catalog
Structured catalog mapping feat/feature/item names to mechanical effects. Agent-assisted AoN scraping to populate. Grows incrementally as real usage exposes gaps.

### Phase C — Tactica: Alkenstar (scenario game)
50 handcrafted scenarios grouped by tactical lesson. Terminal UI for play. Scoring against engine's optimal solutions.

### Phase D — Web App
React + TypeScript + Vite frontend, FastAPI backend exposing the Python engine. User accounts, character storage, scenario library, leaderboards. 3-6 months of real work.

### Phase E — Content and Community
Ongoing scenario additions, class support, community scenario editor, potential Paizo partnership.
