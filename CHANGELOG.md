# Changelog

## [CP11.7] — 2026-05-01
### Fixed
- **Trip and Disarm scored 0.0 EV** — `_condition_ev("prone")` and `_condition_ev("off_guard")` both returned 0.0 in contest_roll.py. These actions were invisible to the beam search. Trip now scores Stand cost AED (avg_enemy_attack_ev × 0.70 survival discount). Disarm now scores -2 attack penalty EV.
- **Feint/Diversion double-counted** — `DegreeEffect.score_delta` hardcoded values (1.0, 0.5, -0.5) overlapped with `_condition_ev`. Zeroed out; value now computed dynamically.
- **Taunt used hardcoded 5.0 for ally damage** — Replaced with `_avg_ally_damage()` for actual ally weapon stats.

### Added
- **`ActionOutcome.aed_delta`** — structural field for action economy disruption value (float, default 0.0). Accumulated alongside `score_delta` in beam search.
- **`_avg_enemy_attack_ev(state)`** — AED primitive: expected damage of one average enemy attack from actual living enemy stats. The value of forcing one lost action.
- **`_avg_ally_damage(state, actor_name)`** — average damage per hit for living allies, used for off-guard value estimation.
- **`_parse_damage_dice(dice_str)`** — safe parser for "NdM" format with fallback.
- **`_condition_ev` expanded** — now handles `prone` (Stand cost), `off_guard` (+2 ally hits), `disarmed` (-2 enemy penalty). `state` parameter added (optional, with safe fallbacks).
- **`DebugActionEntry.aed_ev`** — separate AED component visible in debug beam JSON output.
- **Taunt evaluator calibrated** — `score_delta=penalty_ev` (enemy penalty), `aed_delta=off_guard_ev` (ally buff).
- 20 new tests (1131 → 1151)
- EV 7.65 verified (48th)

## [CP11.2.1] — 2026-04-30
### Fixed
- **Stride reachability bug** — `_add_stride_candidates` and `_add_sneak_candidates` called `shortest_movement_cost(pos, dest)` which returns cost-to-adjacent-to-dest, not cost-to-dest. Destinations 5ft beyond speed were incorrectly included. Rook was recommended moves he couldn't complete in terrain scenarios.
- **Enemy speed hardcoded** — `_enemy_candidates` used `enemy_speed = 25` for all enemies. Now reads actual speed from `EnemySnapshot.speed`.

### Added
- **`can_reach()`** (`sim/grid.py`) — BFS to destination directly (not adjacency). Used by stride/sneak candidate generation.
- **`EnemyState.speed`** / **`EnemySnapshot.speed`** — `int = 25`. Propagated from NPCData via `_build_enemy_from_sheet`. Flat-stat parser accepts optional `speed=` field.
- **Kiting stride category** — positions within reach weapon range but outside 5ft enemy melee (Aetregan's 10ft Scorpion Whip).
- **Flanking setup stride category** — positions opposite an adjacent ally, validated with `are_flanking()`.
- **Mortar arc stride category** — standoff positions within 120ft of all enemies for Erisen's Light Mortar.
- Stride destination cap raised 20 → 30.
- `tests/test_stride_reach.py` (20 tests), 8 new `can_reach` tests in `test_grid.py`

### Design Notes
- `can_reach` uses uniform 5ft BFS (matches existing pathfinding convention)
- `shortest_movement_cost` unchanged — still correct for "can I reach melee position on target" use case
- EV 7.65 unchanged (47th verification)

## [Phase C] — 2026-04-30
### Added
- **NPCData** (`pf2e/npc_data.py`) — pre-calculated NPC combat stats with override hooks for combat_math.py. Duck-type compatible with Character; PCs unchanged.
- **NPC importer** (`sim/importers/foundry_npc.py`) — `import_foundry_npc()` loads Foundry VTT NPC JSONs. Parses abilities (modifier-only), melee attack totals, spellcasting, skills, vision. Creates synthetic EquippedWeapon for natural attacks (Goblin Dog Jaws).
- **`sheet=` scenario syntax** — `[enemies]` section supports `sheet=goblin-warrior` to load NPC stats from `characters/enemies/<slug>.json` instead of inline flat stats.
- **Goblin Ambush scenario** (`scenarios/goblin_ambush.scenario`) — 4 PCs vs Goblin Warrior + War Chanter + Goblin Dog. End-to-end test for NPC sheet loading.
- **NPC strike chassis** (`pf2e/strike.py`) — `_evaluate_npc_strike()` routes NPC-sheet enemies through unified weapon strike with agile MAP and proper damage derivation.
- 7 `combat_math.py` override hooks: max_hp, attack_bonus, armor_class, save_bonus, perception_bonus, class_dc, spell_attack_bonus, skill_bonus
- `EnemyState.character` + `EnemySnapshot.character` fields (object, default None)
- `tests/test_npc_data.py` (22 tests), `tests/test_npc_importer.py` (28 tests), `tests/test_goblin_ambush.py` (14 tests)

### Design Notes
- Override hooks use `getattr(char, 'npc_X', None)` — zero import coupling between combat_math and NPCData
- NPC JSONs store modifiers only; synthetic AbilityScores use `mod * 2 + 10`
- Proficiency back-calculation avoided entirely; pre-calculated totals used via hooks
- Goblin Scuttle, Goblin Pox, Goblin Song deferred (no chassis support)
- EV 7.65 unchanged (46th verification)

## [CP11.7.0 patch] — 2026-04-30
### Fixed
- **Verbose interleave** — verbose detail now appears under each individual action instead of as a block after all action labels. Changed `verbose_text: str` to `verbose_lines: list[str]` on `RoundRecommendation` and `TurnLog`. Formatters interleave each action's verbose block immediately after its label.

## [CP11.3 patch] — 2026-04-30
### Changed
- **Initiative locking** — `solve_combat` rolls initiative once from `scenario.initiative_seed` (fallback to `seed` param). Removed `num_plans` parameter and 5-seed loop. `is_optimal=True` always set.
- **Early exit** — `simulate_round` breaks when all enemies dead mid-round. PCs no longer take no-op turns after last enemy killed.
- **MAP completeness** — `MORTAR_LAUNCH` added to `_ATTACK_TRAIT_TYPES`. `CAST_SPELL` conditionally increments MAP for `ATTACK_ROLL` pattern spells only (Needle Darts yes, Force Barrage/Fear no).

### Design Notes
- `--seed` CLI flag repurposed as initiative fallback for scenarios without `[initiative] seed`
- EV 7.65 unchanged (42nd verification)

## [CP11.7.0] — 2026-04-30
### Added
- `--verbose` CLI flag — shows per-action probability breakdown (MAP, attack bonus, target AC, hit/miss/crit probabilities, EV, HP delta) for all combatants including enemies
- `sim/verbose.py` — `format_verbose_turn`, `format_verbose_action`, action-type formatters for Strike, Stride, Skill, Spell, Tactic, Anthem
- `tests/test_verbose.py` — 18 new tests (3 _hp_delta, 3 _clamp, 1 empty, 3 TurnPlan fields, 6 output content, 1 full-combat, 1 regression)

### Changed
- `sim/search.py` — `SearchConfig.verbose`, `_BeamEntry.action_results/intermediate_states`, `TurnPlan.action_results/intermediate_states`, `RoundRecommendation.verbose_text`
- `sim/solver.py` — `TurnLog.verbose_text`, `solve_combat` accepts `config` parameter, verbose text computed in `_run_single_combat`
- `sim/cli.py` — `--verbose` argument, threads `SearchConfig` to both run paths

### Design Notes
- Zero behavior change — pure presentation layer, EV 7.65 unchanged
- Verbose data stored on winning beam entry only (zero overhead when disabled)
- All verbose output lines guaranteed <= 80 characters
- Works with both `--full-combat` and single-round mode, alongside `--debug-beam`

## [CP11.3] — 2026-04-30
### Fixed
- **Enemy MAP** — enemies now apply Multiple Attack Penalty to strikes (was +7/+7/+7, now +7/+2/-3 for standard weapons). Previously all enemy strikes used raw `attack_bonus` regardless of attacks taken, inflating enemy damage ~30-40% per turn.

### Added
- `sim/round_state.py` — `EnemySnapshot.map_count` field (default 0)
- `tests/test_enemy_map.py` — 15 new tests (4 MAP penalty, 3 map_count, 2 reset, 3 integration, 3 regression)

### Changed
- `pf2e/strike.py` — `evaluate_enemy_strike` applies `map_penalty(map_count + 1, agile=False)`
- `sim/search.py` — `_update_action_economy` increments enemy `map_count` on attack-trait actions
- `sim/solver.py` — `_reset_turn_state` clears enemy `map_count` to 0

### Design Notes
- EV 7.65 killer regression UNCHANGED — it tests tactic EV (PC damage output), not enemy damage
- Agile enemy weapons deferred — no current L1 enemies have agile weapons
- Enemy adversarial sub-search gets MAP automatically via `_update_action_economy`

## [CP11.1] — 2026-04-30
### Added
- `--debug-beam PATH` CLI flag — writes structured JSON capturing every beam search evaluation depth-by-depth
- `sim/search.py` — `DebugActionEntry`, `DebugSequenceEntry`, `DebugTurnLog` dataclasses + `_debug_serialize()` for JSON output
- `tests/test_debug_beam.py` — 20 new tests (6 presence, 5 depth data, 3 winner matching, 3 JSON serialization, 1 no-debug regression, 2 regression)

### Changed
- `sim/search.py` — `beam_search_turn`, `adversarial_enemy_turn`, `simulate_round`, `run_simulation` all accept optional `debug_sink` parameter
- `sim/solver.py` — `solve_combat`, `_run_single_combat` thread `debug_rounds` for full-combat debug output
- `sim/cli.py` — `--debug-beam PATH` argument; writes JSON after simulation completes

### Fixed
- `actor_type`: use `actor_name in state.enemies` check instead of `negate_score` proxy
- `condition_ev`: store `action_ev_delta` (this action only), not cumulative `new_action_ev`
- `survivors_into_next`: added to all three depth dicts in `_debug_serialize` (depth 1→len(d2), depth 2→len(d3), depth 3→None)

### Design Notes
- Zero behavior change when `--debug-beam` is absent; debug_sink is write-only during search
- Depth 1: all evaluated candidates; Depths 2-3: top-K survivors only
- Full combat: nested round structure with `round_number`
- JSON output via `_debug_serialize` — manual conversion, no `dataclasses.asdict`

## [CP10.9] — 2026-04-29
### Added
- `pf2e/rolls.py` — `FlatCheckOutcomes` dataclass + `flat_check_degrees(dc)` for 4-degree flat checks
- `pf2e/actions.py` — `ActionType.FIRST_AID` + `evaluate_first_aid()` (2 actions, Medicine vs DC 15)
- `tests/test_dying.py` — 33 new tests (4 flat_check_degrees, 3 data model, 5 0HP→Dying, 5 recovery, 5 solver integration, 5 First Aid, 2 candidates, 4 regression)

### Changed
- `sim/round_state.py` — `CombatantSnapshot` gains `dying`, `wounded`, `doomed` fields (all default 0)
- `sim/search.py` — `apply_outcome_to_state` detects PC dropping to 0HP → applies Dying (1 + wounded + doomed)
- `sim/solver.py` — `_is_dead` checks `dying >= 4` for PCs; `_all_pcs_dead` checks all dying 4; dying PCs get recovery check turn instead of beam search; `_process_recovery_check` (EV-folded 4-degree flat check)
- `sim/candidates.py` — FIRST_AID candidates generated when ally is dying
- `tests/test_evaluators.py` — FIRST_AID added to dispatcher expected set

### Design Notes
- Recovery check: DC = 10 + dying, 4-degree flat check (no nat 20/1), EV-folded
- Crit dying (+1 on crit hit) deferred — always use base formula (1 + wounded + doomed)
- Unconscious condition deferred — recovered PCs (dying=0, hp=1) act immediately
- Enemies die at 0HP (no dying condition per PF2e rules for non-heroic creatures)
- First Aid costs 2 actions per AoN

## [CP10.8] — 2026-04-29
### Added
- `pf2e/damage_pipeline.py` — `_parse_persistent_tags()`, `merge_persistent_tag()` (take-higher stacking), `apply_persistent_damage()` (direct HP, bypasses pipeline), `attempt_recovery()` (DC 15 flat check)
- `tests/test_persistent_damage.py` — 26 new tests (3 parsing, 6 damage application, 3 recovery, 3 stacking, 3 end-of-turn ordering, 4 Needle Darts crit, 4 regression)
- `pf2e/spells.py` — `SpellDefinition.crit_persistent_bleed` field; Needle Darts set to 1

### Changed
- `pf2e/conditions.py` — `process_end_of_turn` now applies persistent damage → recovery → frightened (correct end-of-turn order per AoN)
- `pf2e/strike.py` — `evaluate_spell_attack_roll` adds persistent bleed to crit outcomes when `defn.crit_persistent_bleed > 0`
- `sim/search.py` — `apply_outcome_to_state` uses `merge_persistent_tag` for take-higher stacking rule

### Design Notes
- Persistent damage applies at END of turn (not start — brief was corrected)
- Recovery: DC 15 flat check = 30% chance, uses `random.random()` (non-deterministic, seeded RNG deferred)
- Same-type persistent damage takes higher value, different types coexist
- Persistent damage bypasses Shield Block, Intercept Attack, and Guardian's Armor resistance
- Splash damage deferred (no L1 party weapons have splash)

## [CP10.7] — 2026-04-29
### Added
- `pf2e/detection.py` — Three-layer detection system: `LightLevel`, `VisionType`, `DetectionState`, `LightSource`, `compute_light_level()`, `perceived_light_level()`, `compute_detection_state()`
- `tests/test_detection.py` — 38 new tests (3 enums, 4 light level, 6 perceived, 6 detection state, 6 hide eligibility, 1 hidden EV fix, 3 character vision, 3 RoundState lighting, 3 scenario parsing, 3 regression)

### Fixed
- **Hide eligibility** — replaced broken adjacency proxy with RAW-correct cover+concealment check (AoN: Actions.aspx?ID=62)
- **`_hidden_defensive_value`** — fixed 0.45 → 0.50 (DC 11 flat check = 10/20 faces)

### Changed
- `pf2e/character.py` — added `vision_type: VisionType` field (default NORMAL)
- `sim/importers/foundry.py` — sets vision_type from ancestry (Elf→LOW_LIGHT, Automaton→DARKVISION)
- `sim/round_state.py` — `RoundState` gains `ambient_light: LightLevel`, `light_sources: tuple[LightSource, ...]`
- `sim/scenario.py` — `Scenario` gains lighting fields + `_parse_lighting()` for `[lighting]` section
- `pf2e/actions.py` — `evaluate_hide` uses `_has_cover_or_concealment()` (cover from walls OR concealment from dim/dark light)
- `tests/test_evaluators.py` — updated 4 Hide tests for correct cover/concealment requirements

### Design Notes
- Light measured at DEFENDER's position, perceived through ATTACKER's vision type
- Low-light: dim→bright. Darkvision: dark→dim, dim→bright
- Enemy vision hardcoded NORMAL (all L1 enemies are human bandits)
- Concealed computed on-demand from detection state, not stored in frozenset
- Scenarios without [lighting] default to BRIGHT ambient, no sources

## [CP10.6] — 2026-04-29
### Added
- `sim/grid.py` — `are_flanking()` (dot-product geometry), `CoverLevel` IntEnum, `_bresenham_line()`, `compute_cover_level()` (wall-based cover detection)
- `tests/test_spatial.py` — 29 new tests (8 flanking geometry, 5 is_flanking reach, 5 cover, 4 effective_target_ac, 4 strike integration, 3 regression)
- `scenarios/checkpoint_4_terrain_camp.scenario` — terrain test scenario with river, bridge, wagons, campfire

### Changed
- `pf2e/strike.py` — `is_flanking()` implemented (was stub returning False); checks ally reach + dot-product geometry. `effective_target_ac()` adds `cover_bonus` parameter. `evaluate_pc_weapon_strike()` and `evaluate_spell_attack_roll()` compute cover via runtime import from sim.grid.

### Design Notes
- Flanking uses dot-product <= 0 (angle >= 90°); known approximation for perpendicular positions
- Both flankers must threaten target (within melee reach) per RAW
- Enemy flanking of PCs deferred; enemy strike still uses `armor_class(target)`
- Cover: Bresenham line excludes endpoints; wall on interior path = STANDARD (+2 circ AC)
- No EV impact on killer regression (no flanking or walls in default scenario)

## [CP10.5] — 2026-04-29
### Added
- `pf2e/conditions.py` — Condition state machine: `ConditionDef`, `CONDITION_REGISTRY` (11 entries), `process_end_of_turn()` (frightened decrement)
- `tests/test_conditions.py` — 28 new tests (5 registry, 8 end-of-turn, 7 conditions_removed fix, 2 simulate_round, 3 integration, 3 regression)

### Fixed
- **conditions_removed bug** in `sim/search.py` — `apply_outcome_to_state` now updates bool fields (prone, off_guard, shield_raised) and int fields (frightened) when removing conditions, not just the frozenset. Stand now properly clears `prone: bool`.
- **PC frightened end-of-turn** — old `_end_of_turn_cleanup` operated on frozenset (empty for PCs); new `process_end_of_turn` correctly reads the `frightened: int` field.

### Changed
- `sim/solver.py` — `_end_of_turn_cleanup` delegates to `process_end_of_turn` from conditions.py
- `sim/search.py` — `simulate_round` now calls `process_end_of_turn` after each turn (consistent with full solver)
- `tests/test_solver.py` — Updated 2 existing tests for correct PC frightened tracking (int field, not frozenset)

### Design Notes
- Dual tracking (bool fields + frozenset) preserved intentionally — unification deferred to post-CP10
- PCs: frightened as int field; enemies: frightened as frozenset tag "frightened_N"
- Registry is metadata-only (no behavior dispatch) — evaluators still read fields directly

## [CP10.4.6] — 2026-04-29
### Added
- `pf2e/movement.py` — Movement chassis: `evaluate_stride()`, `evaluate_step()`, `evaluate_sneak()`, `evaluate_crawl()` (new action)
- `tests/test_movement.py` — 20 new tests (2 stride, 2 step, 4 crawl, 4 sneak, 3 parity, 2 candidates, 3 regression)
- `ActionType.CRAWL` — prone-only 5ft movement (AoN: Actions.aspx?ID=76)

### Changed
- `pf2e/actions.py` — CRAWL enum entry + `_wire_movement()` late-binding for STRIDE, STEP, SNEAK, CRAWL
- `sim/candidates.py` — `_add_crawl_candidates()` generates adjacent squares when actor is prone
- `tests/test_evaluators.py` — CRAWL added to dispatcher expected set

### Design Notes
- Crawl is exactly 5ft (not half speed) per AoN, requires Speed >= 10
- `_d20_success_probability` duplicated in movement.py (3 lines) to avoid import coupling
- Old evaluators preserved in actions.py for parity testing
- Enemy crawl candidates deferred (no enemy goes prone in current scenarios)
- Balance and Tumble Through deferred to CP10.6 (need difficult terrain / path-blocking)

## [CP10.4.5] — 2026-04-29
### Added
- `pf2e/save_condition.py` — SaveCondition chassis: `_enemy_avg_damage()`, `condition_ev()`, `evaluate_condition_spell()` — data-driven from `SpellDefinition.condition_by_degree`
- `tests/test_save_condition.py` — 23 new tests (3 avg_damage, 5 condition_ev, 8 evaluate_condition_spell, 4 parity, 3 regression)

### Changed
- `pf2e/actions.py` — `evaluate_spell()` SAVE_OR_CONDITION branch delegates to `evaluate_condition_spell()` from save_condition.py

### Design Notes
- Old `_evaluate_condition_spell` preserved in actions.py for parity testing
- `_enemy_avg_damage` uses `split("d", 1)` — fixes old flee_ev bug that ignores dice count for multi-dice targets. No parity impact on Bandit1 "1d8"
- Degree prefix matching (longest-first) merges multiple `condition_by_degree` entries per degree into one ActionOutcome
- Incapacitation trait degree-shift deferred — Fear lacks the trait

## [CP10.4.4] — 2026-04-29
### Added
- `pf2e/save_damage.py` — BasicSave damage chassis: `basic_save_ev()`, `aoe_enemy_ev()`, `aoe_friendly_fire_ev()`, `evaluate_save_damage_spell()`
- `tests/test_save_damage.py` — 25 new tests (5 basic_save_ev math, 4 aoe_enemy_ev, 3 aoe_ff_ev, 5 save_damage_spell, 5 mortar delegation, 3 regression)

### Changed
- `pf2e/actions.py` — `evaluate_mortar_launch()` delegates math to `aoe_enemy_ev`/`aoe_friendly_fire_ev` from save_damage.py; `evaluate_spell()` SAVE_FOR_DAMAGE branch delegates to `evaluate_save_damage_spell()`

### Design Notes
- Old `_evaluate_save_damage_spell` preserved in actions.py for parity testing
- MORTAR_AIM/MORTAR_LOAD chain credit unchanged (still uses `expected_aoe_damage` from combat_math)
- `mortar.save_type` used throughout instead of hardcoded `SaveType.REFLEX`
- Basic save fractions: crit_success=0, success=½, failure=full, crit_failure=×2

## [CP10.4.1] — 2026-04-28
### Added
- `pf2e/contest_roll.py` — ContestRollDef + DegreeEffect frozen dataclasses, CONTEST_ROLL_REGISTRY (5 entries), `_condition_ev()` helper, `evaluate_contest_roll()` generic chassis
- `tests/test_contest_roll.py` — 30 new tests (5 data, 4 condition EV, 6 eligibility, 8 outcomes, 6 parity, 1 regression)

### Changed
- `pf2e/actions.py` — dispatcher late-wires Trip, Disarm, Demoralize, Create a Diversion, Feint to `evaluate_contest_roll()` via `_wire_contest_roll()`

### Design Notes
- Old evaluators preserved in actions.py (not deleted) for reference and parity testing
- CaD collapses crit degrees: `crit_success=None` merges into success, `crit_failure=None` merges into failure
- Demoralize crit_failure deviation from RAW: actor gets frightened_1 (preserved from existing behavior)
- `_condition_ev()` handles frightened_N dynamically; off_guard/prone/disarmed return 0.0 (fixed EV in DegreeEffect.score_delta)
- Geometry helpers duplicated from actions.py to avoid circular import

### Deferred to CP10.4.2+
- Remaining chassis: AutoStateChange, Strike, BasicSave, NonBasicSave, Movement
- Flourish enforcement in beam search
- Trait-based immunity for enemies (EnemySnapshot lacks immunity_tags)

## [CP10.3] — 2026-04-28
### Added
- `pf2e/modifiers.py` — BonusType enum (5 types), BonusTracker class with PF2e stacking rules
- `tests/test_modifiers.py` — 30 new tests (16 BonusTracker unit, 11 migration parity, 2 enum, 1 regression)

### Changed
- `pf2e/combat_math.py` — migrated 7 derivation functions to use BonusTracker:
  - `armor_class()` — shield as CIRCUMSTANCE bonus, off-guard as CIRCUMSTANCE penalty, frightened as STATUS
  - `attack_bonus()` — potency as ITEM, MAP as UNTYPED, frightened as STATUS penalty, anthem as STATUS bonus
  - `save_bonus()`, `perception_bonus()`, `spell_attack_bonus()`, `skill_bonus()`, `lore_bonus()`

### Design Notes
- Typed bonuses (CIRCUMSTANCE, STATUS, ITEM): highest bonus + worst penalty per type
- UNTYPED and PROFICIENCY: all values accumulate
- Shield (+2 circ) and off-guard (-2 circ) correctly both apply (net 0) — bonus/penalty independence
- Anthem (+1 status) and frightened (-1 status) correctly both apply — same independence
- class_dc() and siege_save_dc() deliberately NOT migrated (DCs, not checks)

### Deferred to CP10.4+
- Cover and flanking as new bonus sources (CP10.6)
- Condition-driven modifier injection (CP10.5)
- Full action-level BonusTracker (currently function-scoped)

## [CP10.2] — 2026-04-28
### Added
- `pf2e/traits.py` — TraitCategory enum, TraitDef dataclass, TRAIT_REGISTRY (9 slugs)
- `is_immune(action_traits, target_immunity_tags)` — trait-based immunity gate
- `has_trait(action_traits, category)` — trait category lookup
- `Character.immunity_tags: frozenset[str]` — per-character immunity tags (default empty)
- `CombatantSnapshot.used_flourish_this_turn: bool` — flourish tracking infrastructure
- `tests/test_traits.py` — 30 new tests

### Design Notes
- Fear is DESCRIPTOR, not IMMUNITY — immunity flows through emotion trait (AoN: Traits/345)
- Rook `immunity_tags=frozenset()` — Automaton Constructed Body waives construct immunities (AoN: Ancestries/48)
- Unknown trait slugs (finesse, agile, reach) silently skipped in is_immune/has_trait
- Flourish tracking is data-only infrastructure; enforcement deferred to CP10.4

### Deferred to CP10.4
- Flourish enforcement in beam search
- Trait-driven evaluator wiring (contest roll, strike chassis)
- Open/press prerequisite checks

## [CP5.4] — 2026-04-26
### Added
- `pf2e/spells.py` — SpellDefinition dataclass, SpellPattern enum, SPELL_REGISTRY
- Spell chassis evaluator: 4 pattern helpers (auto-hit, condition, attack roll, save damage)
- `CAST_SPELL` ActionType with candidate generation and range filtering
- `DamageType.FORCE` added to `pf2e/types.py`
- `spell_attack_bonus()` in `pf2e/combat_math.py`
- `Character.known_spells` field (slug → rank mapping)
- Importer populates known_spells from Foundry spell items in SPELL_REGISTRY
- Fear (rank 1, 2 actions, Will save → frightened condition)
- Force Barrage (rank 1, 1-3 actions, auto-hit, 1d4+1 force/missile)
- Needle Darts (cantrip, 2 actions, spell attack vs AC, 3d4 piercing)
- `tests/test_spells.py` — 26 new tests

### Changed
- Dalai now casts Force Barrage in combat instead of Create a Diversion spam
- Beam search generates CAST_SPELL candidates for known spells with range filtering
- CLI output labels spells: "Cast Force Barrage vs Bandit2"

### AoN Corrections (from Pass 1 research)
- Fear: 2 actions (brief said 1) — AoN ID=1524
- Needle Darts: spell attack roll, not save; 3d4, not 2d4; cantrip — AoN ID=1375
- Force Barrage: range 120 ft (brief said 60) — AoN ID=1536

### Phase C deferred
- Spell slot tracking (Dalai has 2 rank-1 slots at L1)
- Needle Darts persistent bleed on crit
- Force Barrage missile splitting across targets
- Heightening at higher ranks

### Regressions
- EV 7.65 (16th verification)

## [Phase B+.2] — 2026-04-26
### Added
- `pf2e/effects/__init__.py` — placeholder for future handler registry
- Unmodeled effects warning in session init (`_check_unmodeled_effects()`)
- D29 revised: handler priority based on content inspection, not kind counts
- D30: handler registry deferred until first handler needed

### Analysis
- All 26 combat-kind Rule Elements classified by content inspection:
  - 17 already handled by importer/engine
  - 6 non-combat (safe to skip)
  - 3 genuinely unmodeled but non-blocking at L1
- Only Assurance (SubstituteRoll) flagged in unmodeled effects warning
- Extended `tools/re_analysis_report.md` with detailed classification

### Regressions
- EV 7.65 (15th verification — no engine changes)

## [Phase B+.1] — 2026-04-26
### Added
- `sim/catalog/session_cache.py` — session-scoped SQLite cache for Rule Elements
- `sim/catalog/github_fetcher.py` — GitHub fetcher (v14-dev branch, flat paths only)
- `sim/catalog/session_init.py` — two-phase session initializer (local + GitHub)
- `tools/analyze_rule_elements.py` — Rule Element analysis and report generator
- `--init-session`, `--characters`, `--cache` CLI flags
- D29: Handler priority order (ActiveEffectLike → AdjustModifier → FlatModifier
  → Strike → SubstituteRoll → Aura → Resistance)

### Architecture
- Local-first: character JSONs are primary Rule Element source (no network needed)
- GitHub supplement: bestiary/flat-path items fetched on demand
- 115 unique items cached from 4 characters (36 with Rule Elements)
- 92 total Rule Elements across 15 distinct kinds
- 28.3% combat-relevant (26 of 92), 71.7% creation-time/utility (66 of 92)

### Regressions
- EV 7.65 (14th verification — no engine changes)

## [Phase B] — 2026-04-26

### Added
- `sim/importers/foundry.py` — Foundry VTT pf2e actor JSON importer
- `sim/importers/__init__.py`
- `characters/fvtt-aetregan.json`, `fvtt-rook.json`, `fvtt-dalai.json`, `fvtt-erisen.json`
- `WeaponGroup.AXE` added to `pf2e/types.py`
- `tests/test_foundry_importer.py` — 34 new tests

### Changed
- `sim/party.py` factories now call `import_foundry_actor()` for all four characters
- Aetregan: WIS 10, CHA 12 (was WIS 12, CHA 10 — alternate ancestry boosts, JSON authoritative)
- Aetregan: Deception now trained (was untrained — JSON authoritative)
- Aetregan: Nature now untrained (was trained — JSON authoritative)
- Aetregan: Deity Lore removed (not in Foundry export)
- Rook: Primary weapon Earthbreaker d6 bludgeoning (was Longsword d8 slashing)
- Rook: 4 weapons imported (Earthbreaker, Light Hammer, Barricade Buster, Bottled Lightning)
- Rook: Perception trained (was expert — Foundry Guardian class item)
- Rook: ancestry_hp 8 / class_hp 12 (was 10/10 — same total HP 23)
- Rook: Skills now Diplomacy, Crafting, Survival, Medicine (was Athletics, Intimidation, Society, Crafting)
- Dalai: Rapier Pistol d4 piercing replaces Rapier d6 piercing
- Dalai: has_soothe=False (Soothe not in Foundry spell repertoire)
- Dalai: has Buckler shield
- Erisen: Dueling Pistol d6 piercing replaces Dagger d4 piercing
- Erisen: Leather Armor AC+1 (was Studded Leather AC+2)
- Erisen: Reflex trained / Will expert (was Reflex expert / Will trained)
- **Strike Hard EV: 8.55 → 7.65** (Rook Earthbreaker d6 vs old Longsword d8)

### Known Phase B+ deferred items (flagged in code comments)
- Combination weapon dual-mode (Dalai's Rapier Pistol ranged mode)
- Two-hand damage die upgrade (Rook's Earthbreaker d6→d10)
- Gun traits: concussive, fatal (Erisen's Dueling Pistol, Barricade Buster)
- class_dc_rank sourced from catalog (currently hard-coded TRAINED)

## [CP7] — 2026-04-25
### Fixed
- Survival bonus underweighted: added flat 15 per surviving PC + 0.5 × remaining HP.
  All-4-alive now scores 23.5 points higher than 3-alive (was only 8.5).
- Scenario 2 anthem_active=false: Dalai must cast Anthem as an action.
- Taunt/Raise Shield score 0 at round start: now use threat-weighted EV
  (all living enemies, not just adjacent).
- Missing score_delta on Create a Diversion, Demoralize, Feint, Raise Shield.
- Recall Knowledge now party-wide: checks best damage type across all PCs.

### Verified
- Hidden bonus does NOT leak into reaction Strikes (Strike Hard! correctly
  uses squadmate stats, not Commander stats).
- Strike Hard EV 8.55 (12th consecutive verification).

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
