# Changelog

## [CP6] — 2026-04-25
### Added
- sim/solver.py — full combat solver (solve_combat, CombatSolution, RoundLog, TurnLog)
- STAND evaluator — clears Prone, 1 action cost
- condition_durations field on CombatantSnapshot and EnemySnapshot
- _reset_turn_state() — resets action economy at start of each turn
- _end_of_turn_cleanup() — frightened decrement, per-turn condition expiry
- Condition duration rules for all condition tags
- Top 5 plan evaluation via seed variation (seeds N..N+4)
- Scenario difficulty rating (trivial/easy/medium/hard/very_hard/impossible)
- Cumulative EV scoring with round bonus and survival bonus
- Round-by-round CLI output with HP tracking
- --full-combat CLI flag

### Fixed
- Action economy reset: map_count and actions_remaining now reset each turn
- Dead combatants skipped in solver loop (no empty turn logs)
- Anthem correctly clears at start of Dalai's turn (not round end)
- Taunt correctly clears at start of Rook's turn
- Shield_raised clears at start of actor's next turn

### Regressions
- Strike Hard EV 8.55 (11th consecutive verification)
- simulate_round() single-round path unchanged and backward compatible

## [CP5.3] — 2026-04-25
### Added
- RECALL_KNOWLEDGE evaluator — conditional W/R insight, Society for humanoids
- HIDE evaluator — Stealth vs Perception, Hidden condition, cover proxy
- SNEAK evaluator — half-Speed movement while Hidden, two-branch outcome
- SEEK evaluator — locate Hidden enemies, scores 0.0 when none present
- AID evaluator — next-round discounted bonus, crit success modeled
- weakness/resistance fields on EnemyState and EnemySnapshot
- Scenario parser: weakness_*/resistance_* keys in [enemies] section
- scenarios/checkpoint_2_two_bandits.scenario — 2 enemies, W/R stat blocks
- _has_recalled() helper — controls conditional W/R in STRIKE/MORTAR
- Probability helpers: _d20_success/crit_success/crit_fail_probability

### Fixed
- MORTAR_LAUNCH subtracts friendly fire from score delta (PCs adjacent to enemies)
- STRIKE applies Hidden +2 attack bonus and clears Hidden after attacking
- Confirmed STEP does not clear Hidden (per AoN)

### Regressions
- Strike Hard EV 8.55 (10th consecutive verification) — checkpoint_1 scenario
- New regression target: checkpoint_2_two_bandits scenario

## [CP5.2] — 2026-04-25
### Added
- ANTHEM evaluator (Courageous Anthem, Option B ripple EV across ally strikes)
- SOOTHE evaluator (1d10+4 healing, wound-severity-weighted targeting)
- MORTAR_AIM, MORTAR_LOAD, MORTAR_LAUNCH evaluators (Light Mortar state machine)
- TAUNT evaluator (Guardian class feature, -1 circumstance + off-guard)
- INTERCEPT_ATTACK extended to 15-ft range vs taunted enemy
- 6 new ActionType entries, 4 new Character flags
- `[combatant_state]` scenario file section for pre-set mortar state
- `_effective_status_bonus_attack/damage` helpers for mid-round Anthem
- `conditions_removed` handling in `apply_outcome_to_state`
- Mortar auto-deploy at combat start via `has_light_mortar` flag

### Rules verified
- Courageous Anthem (AoN: Spells — Courageous Anthem)
- Soothe (AoN: Spells — Soothe)
- Light Mortar action order: AIM → LOAD → LAUNCH (AoN: Innovations ID=4)
- Taunt automatic, no check (AoN: Actions ID=3304)
- Intercept Attack range extension with Taunt (AoN: Actions ID=3305)
- Rallying Anthem / Inspire Defense deferred — requires L2 feat

### Regressions
- Strike Hard EV 8.55 (9th consecutive verification)

## [CP5.1.3c] — 2026-04-25
### Added
- 14 action evaluators in `pf2e/actions.py`: END_TURN, RAISE_SHIELD, PLANT_BANNER,
  STRIDE, STEP, STRIKE, TRIP, DISARM, DEMORALIZE, CREATE_A_DIVERSION, FEINT,
  SHIELD_BLOCK, INTERCEPT_ATTACK, ACTIVATE_TACTIC
- `evaluate_action()` dispatcher in `pf2e/actions.py`
- `generate_candidates()` in `sim/candidates.py` for candidate action generation
- `RoundRecommendation` dataclass and `format_recommendation()` in `sim/search.py`
- `run_simulation()` convenience entry point in `sim/search.py`
- `sim/cli.py` and `sim/__main__.py` — CLI entry point with `--scenario`,
  `--seed`, `--debug-search` flags
- `tests/test_evaluators.py` — 46 new evaluator + integration tests
- `tests/test_cli.py` — CLI smoke tests
- `map_count: int` and `conditions: frozenset[str]` fields on `CombatantSnapshot`
- `conditions: frozenset[str]` field on `EnemySnapshot`
- Action economy tracking (MAP + actions_remaining) in beam search loop
- EV-collapse path now applies non-HP state changes (conditions, positions)

### Rules verified
- Feint failure: no immunity (AoN: https://2e.aonprd.com/Skills.aspx?ID=38)
- Disarm crit failure: actor off-guard (AoN: https://2e.aonprd.com/Actions.aspx?ID=2300)
- Flanking: off-guard in Remaster (AoN: https://2e.aonprd.com/Rules.aspx?ID=2361)
- Ever Ready: passive feature, not an evaluator (AoN: https://2e.aonprd.com/Classes.aspx?ID=67)
- Deceptive Tactics does NOT apply to Demoralize (AoN: https://2e.aonprd.com/Feats.aspx?ID=7794)

### Regressions
- Strike Hard EV 8.55 (8th consecutive verification)

## [5.1.3b] - CP5.1.3b: Algorithms

Search engine, state threading, damage pipeline, initiative. The simulator
now has a "brain" that can be driven by mock evaluators; CP5.1.3c wires in
real action evaluators.

### New modules
- `sim/round_state.py` — `CombatantSnapshot`, `EnemySnapshot`, `RoundState`
  with `from_scenario`, `with_pc_update`, `with_enemy_update`.
- `pf2e/damage_pipeline.py` — `resolve_strike_outcome` implementing the
  strict PF2e order: Intercept Attack → Shield Block → Resistance → Temp HP
  → Real HP.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2301)
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2309)
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2321)
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2180)
  (AoN: https://2e.aonprd.com/Actions.aspx?ID=3305)
- `sim/initiative.py` — `roll_initiative` with seeded RNG, partial override,
  enemy-beats-PC tiebreaker, alphabetical same-side.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2423)
- `sim/search.py` — beam search K=50/20/10 depth 3, adversarial enemy
  sub-search K=20/10/5, hybrid state threading with kill/drop branching at
  ≥5% threshold.

### Scoring
- `score_state(state, initial)` implements D11/D12.
- kill_value = max_hp + 10 × num_attacks_per_turn.
- drop_cost = max_hp + 10 × role_multiplier (Dalai 2.0, all others 1.0).
- Temp HP absorption NOT counted as damage_taken (per D24).

### Reactions
- Full search branching per D23 (C2). Shield Block and Intercept Attack
  expand a Strike's outcome set. Timing target: 15s per round.

### Docs
- CHARACTERS.md arithmetic fix (+8 → +7 in 4 spots).
- Checkpoint naming: CP5.1.3b replaces "CP5.1 Pass 3b".
- RULES_CITATIONS.md Initiative URL corrected (ID=2127 → ID=2423).
- D21-D24 added to DECISIONS.md.

## [5.1-3a] - CP5.1.3a: Foundation

Foundation data model for the full-round turn evaluator. No algorithms,
no evaluators — only types, helpers, and data population.

### New types
- Skill enum (16 skills) + SKILL_ABILITY lookup in pf2e/types.py.
- ActionType enum (15 actions) + Action, ActionOutcome, ActionResult
  frozen dataclasses in new pf2e/actions.py.

### Character extensions
- skill_proficiencies, lores, has_plant_banner, has_deceptive_tactics,
  has_lengthy_diversion fields on Character.
- skill_bonus() and lore_bonus() helpers in pf2e/combat_math.py.

### Character data population
- Aetregan: 10 trained skills, 2 lores (Warfare +7, Deity +7),
  feat flags (Deceptive Tactics, Lengthy Diversion).
- Rook: HP 23, 4 trained skills.
- Dalai: HP 17, 6 trained skills, 2 lores.
- Erisen: HP 16, 5 trained skills, 2 lores.

### State extensions
- CombatantState: current_hp, temp_hp, actions_remaining,
  effective_current_hp property.
- EnemyState: max_hp, current_hp, perception_bonus, actions_remaining,
  perception_dc and effective_current_hp properties.

### Scenario parser
- [initiative] section: seed-only or explicit ordering modes.

## [4.5] - Aetregan Reconciliation

### Character corrections
- Cha: 12 -> 10 (ability score correction from Pathbuilder sheet)
- Perception: trained -> expert (Commander gets expert at L1)
  (AoN: https://2e.aonprd.com/Classes.aspx?ID=66)
- Weapon: Whip -> Scorpion Whip (same stats minus nonlethal)
  (AoN: https://2e.aonprd.com/Weapons.aspx?ID=114)

### Folio composition
- Removed Defensive Retreat from FOLIO_TACTICS (not in Aetregan's
  actual folio). Definition and evaluator retained for other commanders.
- Added stub Shields Up! tactic definition. Full evaluator deferred to CP5.
  (AoN: https://2e.aonprd.com/Tactics.aspx?ID=12)

### HP infrastructure
- Added ancestry_hp and class_hp fields to Character (default 0).
- Added max_hp(character) helper: ancestry_hp + (class_hp + Con) x level.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2145)
- Aetregan: ancestry_hp=6, class_hp=8 -> max HP 15 at L1.

### Carried-banner support
- GridSpatialQueries.is_in_banner_aura now handles carried banner:
  aura emanates from commander's position, 30-ft radius.
- Scenario parser accepts planted=false. Position optional when carried.
- Updated checkpoint_1_strike_hard.scenario to planted=false.

## [4.0] - Checkpoint 4: Defensive Value Computation

### Correctness fix
- Planted banner aura expands to 40-ft burst (was hardcoded 30 ft).
  (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)
- GridSpatialQueries.is_in_banner_aura now uses 40 ft when planted,
  30 ft when carried. `banner_planted` is now a required constructor param.

### EnemyState offensive stats
- Added attack_bonus, damage_dice ("NdM" format), damage_bonus,
  num_attacks_per_turn fields. All optional; empty damage_dice = no offense.
- Scenario parser accepts atk=, dmg=, dmg_bonus=, attacks= in [enemies].

### New math helpers (pf2e/combat_math.py)
- plant_banner_temp_hp(level): 4*(1+level//4)
  (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796)
- guardians_armor_resistance(level): 1+level//2
  (AoN: https://2e.aonprd.com/Classes.aspx?ID=67)
- expected_incoming_damage(attacker, target, attack_number): enemy
  Strike EV with MAP, target AC, Guardian's Armor resistance
- expected_enemy_turn_damage(attacker, target): sum across attacks
- temp_hp_ev(temp_hp, expected_damage): min(temp_hp, damage)

### Tactic evaluator updates
- Gather to Me computes defensive EV: temp HP for allies entering
  planted-banner burst + damage prevented by leaving enemy reach.
- Defensive Retreat computes defensive EV: damage prevented by
  allies Stepping out of enemy reach.

### New function: intercept_attack_ev
- Standalone helper for Rook's Intercept Attack (Guardian reaction).
  Not wired into tactic evaluators — Checkpoint 5 will call it.
  (AoN: https://2e.aonprd.com/Actions.aspx?ID=3305)

### TacticResult additions
- damage_prevented_sources: dict[str, float] with canonical keys
  (plant_banner_temp_hp, gather_reposition, retreat_steps, etc.)

## [3.0] - Checkpoint 3: Scenario Loading

### New module: sim/party.py
- Moved factories and equipment constants from tests/fixtures.py.
- Added TOKEN_TO_FACTORY, COMMANDER_TOKEN, SQUADMATE_TOKENS.
- tests/fixtures.py becomes a re-export shim for backward compatibility.

### New module: sim/scenario.py
- Scenario (frozen dataclass) bundling grid, banner, anthem, party, enemies.
- parse_scenario(text) and load_scenario(path) functions.
- ScenarioParseError for all parsing failures.
- Scenario.build_tactic_context() produces a ready-to-evaluate TacticContext
  with GridSpatialQueries wired in.

### New scenario: scenarios/checkpoint_1_strike_hard.scenario
- Canonical end-to-end validation scenario.
- Load + evaluate produces EV 8.55, identical to Checkpoints 1 and 2.

### File format
- Section-based text format (.scenario extension): [meta], [grid],
  [banner], [anthem], [enemies]. Comments via leading #.
- [banner] section authoritative over grid B/* tokens; grid token fallback.
- Commander token ('c') required; squadmate tokens optional.
- Enemy tokens use auto-numbered form (m1, m2, M1).

### Validation
- Missing [grid] -> ScenarioParseError
- Missing commander -> ScenarioParseError
- Enemy token mismatch (grid vs [enemies]) -> ScenarioParseError
- Invalid integer/boolean -> ScenarioParseError

## [2.0] - Checkpoint 2: Grid and Spatial Reasoning

### Foundation refactor
- **EnemyState** moved from `pf2e/tactics.py` to `pf2e/character.py`.
  Re-exported from tactics for backward compatibility.
- **melee_reach_ft(character)** added to `pf2e/combat_math.py`.
  Returns 10 ft if any equipped melee weapon has the reach trait, else 5 ft.
  (AoN: https://2e.aonprd.com/Traits.aspx?ID=684)

### New package: `sim/`
- `sim/grid.py` — Pos alias, GridState dataclass, ASCII parse/render,
  geometry helpers (distance_ft with 5/10 diagonal, chebyshev_squares,
  is_adjacent, is_within_reach with 10-ft exception, squares_in_emanation),
  and BFS pathfinding (shortest_movement_cost).
- `sim/grid_spatial.py` — GridSpatialQueries implementing the
  SpatialQueries Protocol. Precomputes occupied-squares set at
  construction. Banner square is passable (item, not creature).

### Verified PF2e rules
- Grid cell = 5 ft (https://2e.aonprd.com/Rules.aspx?ID=2356)
- Diagonal movement 5/10/5/10 (https://2e.aonprd.com/Rules.aspx?ID=2357)
- Area measurement follows movement rules (https://2e.aonprd.com/Rules.aspx?ID=2384)
- 10-ft reach diagonal exception (https://2e.aonprd.com/Rules.aspx?ID=2379)
- Emanation geometry (https://2e.aonprd.com/Rules.aspx?ID=2387)
- Moving through creature spaces (https://2e.aonprd.com/Rules.aspx?ID=2360)
- Banner 30-ft emanation (https://2e.aonprd.com/Rules.aspx?ID=3421)

### Design decisions
- Pos is a tuple[int, int] type alias, local to sim/. Not propagated
  to pf2e/ to avoid churn.
- BFS uses uniform 5-ft step cost (not strict 5/10 alternation).
  Underestimates long diagonal paths by up to ~15%. Strict 5/10 is
  preserved for point-to-point queries (distance_ft, emanations, aura).
- Movement cannot pass through ANY occupied square (enemies or allies).
  Stricter than PF2e RAW (which allows willing-ally pass-through).
  Chosen to bias toward false negatives in tactical advice.
- GridState holds terrain only. Combatant positions live on
  CombatantState/EnemyState. GridSpatialQueries resolves names to
  positions at construction time.

## [1.0] - Checkpoint 1: Tactic Dispatcher

### Foundation additions
- **Speed on Character and CombatantState**: Character.speed is base
  (ancestry+feats), CombatantState.current_speed is the combat-time
  override for armor penalties. effective_speed(state) returns the
  active value.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)

### Character sheet corrections
- **Aetregan Speed**: 30 ft (Elf base, not 25 as assumed).
  (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=60)
- **Erisen Speed**: 35 ft (Elf 30 + Nimble Elf +5).
  (AoN: https://2e.aonprd.com/Feats.aspx?ID=16)
- **Rook Speed**: Base 25 (Automaton), effective 20 with full plate.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2169)
- **Dalai Speed**: 25 ft (Human base).
  (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=64)

### New module: pf2e/tactics.py
- TacticDefinition, TacticContext, TacticResult, EnemyState,
  SpatialQueries protocol, MockSpatialQueries
- FOLIO_TACTICS registry with all 5 of Aetregan's folio tactics:
  - Strike Hard! (https://2e.aonprd.com/Tactics.aspx?ID=13)
  - Gather to Me! (https://2e.aonprd.com/Tactics.aspx?ID=2)
  - Tactical Takedown (https://2e.aonprd.com/Tactics.aspx?ID=14)
  - Defensive Retreat (https://2e.aonprd.com/Tactics.aspx?ID=1)
  - Mountaineering Training (https://2e.aonprd.com/Tactics.aspx?ID=3)
- Dispatcher: evaluate_tactic() routes by granted_action;
  evaluate_all_prepared() returns results sorted by net_value.
- Evaluators: Strike Hard computes reaction Strike EV at MAP 0;
  Tactical Takedown computes prone probability via d20 enumeration;
  Gather to Me tracks squadmate response counts;
  Defensive Retreat and Mountaineering Training are placeholders.

### Design decisions
- Dispatch via dict of callables keyed by granted_action string.
- SpatialQueries as Protocol; MockSpatialQueries for Checkpoint 1 tests.
  Checkpoint 2 will add real grid-backed implementation.
- TacticResult includes conditions_applied and condition_probabilities
  for Checkpoint 5's turn evaluator to use.
- Tactic modifiers remain dict[str, Any].

## [0.5] - Foundation Cleanup

### Corrections from initial brief
- **Mortar EV per target**: 5.95, not 5.60 as originally stated.
  The boundary case `total <= DC-10` includes equality, so with
  Erisen's mortar (DC 17) vs a Reflex +5 enemy, both rolls 1 AND 2
  produce critical failures (totals 6 and 7, both <= 7).
  Brief originally undercounted to 1 crit fail; correct count is 2.

- **Aetregan Wis**: Corrected from 11 to 12. PF2e Remaster attribute
  boosts increase a modifier by 1 (effectively +2 to score). Score 11
  is not achievable via boosts from 10.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2110)

- **Save bonuses**: Several derivations in the brief were off by 1
  due to incorrect ability modifier assumptions:
  - Aetregan Will: now +6 (Wis 12 -> mod +1, expert +5). Was +5.
  - Aetregan Perception: now +4 (Wis +1, trained +3). Was +3.
  - Dalai Reflex: +5 (Dex 14 -> +2, trained +3). Brief said +6.
  - Dalai Will: +5 (Wis 10 -> +0, expert +5). Brief said +6.

  Derivation from ability scores is the ground truth.

### Foundation design choices
- **Frozen Character, mutable CombatantState**: Character represents
  an immutable build. Per-round combat state (reactions, conditions,
  shield raised, status bonuses) lives on CombatantState wrapper.

- **Trait strings, not enums**: Weapon traits are a frozenset of
  lowercase strings (e.g., "finesse", "agile", "thrown_10").
  Open-ended without enum maintenance burden. Validated implicitly
  by trait-checking properties on Weapon.

- **D20Outcomes enumeration**: All EV calculations go through a
  single `enumerate_d20_outcomes(bonus, dc)` function that counts
  d20 faces by degree of success, with nat 1/20 rules applied.
  This is the load-bearing primitive for both attack EV and save EV.

### Bug fixes (Checkpoint 0.5)
- `Weapon.is_ranged`: now correctly returns True for thrown-trait
  weapons with range increments (javelins, daggers).
  (AoN: https://2e.aonprd.com/Traits.aspx?ID=195)
- `Weapon.is_melee`: now correctly returns True for thrown-melee
  weapons (daggers can be used in melee).
- `attack_ability`: fixed to distinguish pure-ranged weapons from
  thrown-melee weapons used in melee mode. A dagger used in melee
  now correctly follows finesse rules instead of always using Dex.
- Dagger fixture: `range_increment` set to 10 (matching the weapon's
  actual PF2e Range entry) instead of None.
  (AoN: https://2e.aonprd.com/Weapons.aspx?ID=358)
- Aetregan Wis: corrected from 11 to 12.
  (AoN: https://2e.aonprd.com/Rules.aspx?ID=2110)
