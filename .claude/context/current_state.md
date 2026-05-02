# Current State

Last updated: May 2026, post-CP11.2.2.1 (Zero-Distance Stride Fix).

## Test Count

**1186 tests passing.**

## Active Checkpoint

**CP10 — Nine-Layer Architecture Rebuild — COMPLETE**

CP10.1 (Roll Foundation) is **COMPLETE**.
CP10.2 (Trait System) is **COMPLETE**.
CP10.3 (Modifier Assembly) is **COMPLETE**.
CP10.4.1 (ContestRoll Chassis) is **COMPLETE**.
CP10.4.2 (AutoState Chassis) is **COMPLETE**.
CP10.4.3 (Strike Chassis) is **COMPLETE**.
CP10.4.4 (SaveDamage Chassis) is **COMPLETE**.
CP10.4.5 (SaveCondition Chassis) is **COMPLETE**.
CP10.4.6 (Movement Chassis) is **COMPLETE**.
CP10.5 (Condition State Machine) is **COMPLETE**.
CP10.6 (Spatial/Positional) is **COMPLETE**.
CP10.7 (Detection/Visibility) is **COMPLETE**.
CP10.8 (Damage Resolution) is **COMPLETE**.
CP10.9 (Death/Dying System) is **COMPLETE**.

## Killer Regression

**EV 7.65** — Strike Hard, Rook Earthbreaker reaction Strike with Anthem vs Bandit1 AC 15.
Verified 52 times (most recently at CP11.2.2.1 — zero-distance stride fix).

## CP11.2.2.1 Status — COMPLETE

Fixed zero-distance stride bug: _enemy_candidates and _add_tactical_stride_categories
emitted strides where target_position == enemy.position. Guard at emission loop and
early-continue in scan loops. PC version already safe (BFS filter at line 808).

1182 → 1186 tests. EV 7.65 verified (52nd).

## CP11.2.3 Status — COMPLETE

Shared `_add_tactical_stride_categories()` function with 5 new categories (A–E),
called by both PC and NPC stride generation. Faction helpers `_opponents()`,
`_allies()`, `_combatant_speed()`, `_snap_max_hp()`, `_opponent_threat_score()`.

Categories: A=cover (cap 4), B=chokepoint ≤3 approach (cap 3), C=threat escape (cap 3),
D=defensive withdrawal (HP gate removed), E=Reactive Strike (dormant).
`has_reactive_strike: bool = False` added to Character + NPCData.

Lookahead categories F/G/H deferred to CP11.2.4.
1166 → 1182 tests. EV 7.65 verified (51st).

## CP11.2.2 Status — COMPLETE

Improved enemy decision quality: priority-based targeting (wounded, off-guard,
Guardian avoidance), reach-aware strikes, caster standoff positioning, flanking
setup. Fixed F1: caster-only enemies (damage_dice="", known_spells set) were
returning [END_TURN].

Key helpers: _enemy_target_priority, _enemy_melee_reach, _enemy_preferred_range,
_best_adjacent_dest. Stride categories: best-target approach, caster standoff
(tiered 15→10→5ft fallback), flanking setup via are_flanking.

1155 → 1166 tests. EV 7.65 verified (50th).

## CP11.7.1 Status — COMPLETE

Fixed faction routing in AED helpers. `_avg_enemy_attack_ev` → `_avg_opposing_attack_ev(state, actor_name)`
with two-branch routing (PC vs NPC actor). `_avg_ally_damage` NPC branch reads `state.enemies`.
`_condition_ev` threads `actor_name` for correct faction. `disarmed` uses `getattr` for type safety.

1151 → 1155 tests. EV 7.65 verified (49th).

## CP11.7 Status — COMPLETE

Added `aed_delta: float = 0.0` to `ActionOutcome` — action economy disruption
as a first-class scoring dimension. Critical bug fix: Trip and Disarm scored 0.0 EV
because `_condition_ev` returned 0.0 for prone/off_guard/disarmed.

Key additions:
- `_avg_enemy_attack_ev(state)` — AED primitive from actual enemy stats
- `_avg_ally_damage(state, actor_name)` — off-guard value from actual ally stats
- `_condition_ev` expanded: prone (Stand cost × 0.70), off_guard (10% × ally dmg), disarmed
- Feint/Diversion `DegreeEffect.score_delta` hardcodes → 0.0 (now computed dynamically)
- Taunt calibrated: `score_delta=penalty_ev`, `aed_delta=off_guard_ev`
- `DebugActionEntry.aed_ev` field for debug beam output

1131 → 1151 tests. EV 7.65 verified (48th).

Note: EV was 8.55 through CP7.1. Changed to 7.65 in Phase B when Foundry importer
corrected Rook's weapon from Longsword (d8) to Earthbreaker (d6). This is correct per
authoritative Foundry character JSON.

## CP10.9 Status — COMPLETE

Added `flat_check_degrees()` to rolls.py. Added `dying`, `wounded`, `doomed`
to CombatantSnapshot. Implemented 0HP→Dying transition in apply_outcome_to_state.
Added `_process_recovery_check` (EV-folded 4-degree flat check) and dying PC
turn handling in solver.py. Added FIRST_AID ActionType + evaluator (2 actions,
Medicine vs DC 15). Generated FIRST_AID candidates for dying allies.

Key: dying >= 4 = dead; enemies die at 0HP (no dying). Recovery check DC =
10 + dying. Crit dying and Unconscious condition deferred.

939 → 972 tests. EV 7.65 verified (37th).

## CP10.8 Status — COMPLETE

Extended `pf2e/damage_pipeline.py` with persistent damage: tag parsing,
apply_persistent_damage (direct HP bypass), attempt_recovery (DC 15 flat
check), merge_persistent_tag (take-higher stacking). Extended
`pf2e/conditions.py` process_end_of_turn with persistent damage → recovery
→ frightened order. Added crit_persistent_bleed to SpellDefinition (Needle
Darts = 1). Wired stacking in search.py apply_outcome_to_state.

Key: persistent damage at END of turn (not start). Recovery uses
random.random() (non-deterministic, seeded RNG deferred to CP10.9).

913 → 939 tests. EV 7.65 verified (36th).

## CP10.7 Status — COMPLETE

Created `pf2e/detection.py` (LightLevel, VisionType, DetectionState, LightSource,
compute_light_level, perceived_light_level, compute_detection_state) and
`tests/test_detection.py` (38 tests). Added `vision_type` to Character, lighting
fields to RoundState/Scenario, `[lighting]` parser to scenario.py. Fixed
evaluate_hide to use RAW cover+concealment check. Fixed `_hidden_defensive_value`
0.45→0.50.

Key: Foundry importer sets Elf→LOW_LIGHT, Automaton→DARKVISION. Enemy vision
hardcoded NORMAL. Concealed computed on-demand, not stored in frozenset.

875 → 913 tests. EV 7.65 verified (35th).

## CP10.6 Status — COMPLETE

Added `are_flanking()` (dot-product geometry), `CoverLevel`, `compute_cover_level()`
to `sim/grid.py`. Implemented `is_flanking()` in `pf2e/strike.py` (was stub),
added `cover_bonus` to `effective_target_ac()`, wired cover into PC weapon strikes
and spell attack rolls. Created `tests/test_spatial.py` (29 tests) and
`scenarios/checkpoint_4_terrain_camp.scenario`.

Key: flanking requires both geometric opposition AND ally melee reach. Enemy
flanking deferred. Cover uses Bresenham line through walls. No EV impact on
default scenario (no flanking or walls).

846 → 875 tests. EV 7.65 verified (34th).

## CP10.5 Status — COMPLETE

Created `pf2e/conditions.py` (ConditionDef, CONDITION_REGISTRY, process_end_of_turn)
and `tests/test_conditions.py` (28 tests). Fixed conditions_removed bug in
`sim/search.py` (bool fields now cleared). Delegated solver.py _end_of_turn_cleanup.
Wired simulate_round end-of-turn processing.

Key fixes: (1) conditions_removed now updates prone/off_guard/shield_raised bool
fields, not just frozenset. (2) PC frightened decrement reads int field directly
instead of searching frozenset (which was always empty for PCs).

818 → 846 tests. EV 7.65 verified (33rd).

## CP10.4.6 Status — COMPLETE

Created `pf2e/movement.py` (evaluate_stride, evaluate_step, evaluate_sneak,
evaluate_crawl) and `tests/test_movement.py` (20 tests). Modified
`pf2e/actions.py` (CRAWL enum + _wire_movement), `sim/candidates.py`
(_add_crawl_candidates), `tests/test_evaluators.py` (expected set).

Key changes: Crawl is 5ft flat (not half speed) per AoN. Candidates use
Step-like adjacency pattern. Enemy crawl candidates deferred. Balance and
Tumble Through deferred to CP10.6.

798 → 818 tests. EV 7.65 verified (32nd).

## CP10.4.5 Status — COMPLETE

Created `pf2e/save_condition.py` (_enemy_avg_damage, condition_ev,
evaluate_condition_spell) and `tests/test_save_condition.py` (23 tests).
Modified `pf2e/actions.py` (spell SAVE_OR_CONDITION branch delegation).

Key changes: data-driven degree dispatch from `condition_by_degree` field.
Prefix matching (longest-first) merges multiple entries per degree. Old
evaluator preserved. `_enemy_avg_damage` fixes multi-dice bug in flee_ev.

775 → 798 tests. EV 7.65 verified (31st).

## CP10.4.4 Status — COMPLETE

Created `pf2e/save_damage.py` (basic_save_ev, aoe_enemy_ev, aoe_friendly_fire_ev,
evaluate_save_damage_spell) and `tests/test_save_damage.py` (25 tests). Modified
`pf2e/actions.py` (mortar delegation + spell SAVE_FOR_DAMAGE branch).

Key changes: mortar math delegated to save_damage.py functions. Old evaluators
preserved in actions.py. MORTAR_AIM/LOAD chain credit unchanged. basic_save_ev
uses defender-perspective outcomes (crit_fail=2×, fail=1×, success=0.5×, crit_success=0).

750 → 775 tests. EV 7.65 verified (30th).

## CP10.4.3 Status — COMPLETE

Created `pf2e/strike.py` (is_flanking stub, effective_target_ac, build_strike_outcomes,
_strike_hidden_ev, evaluate_pc_weapon_strike, evaluate_enemy_strike,
evaluate_spell_attack_roll) and `tests/test_strike.py` (39 tests). Modified
`pf2e/actions.py` (`_wire_strike()` dispatch + spell ATTACK_ROLL delegation).

Key changes: geometry helpers duplicated (same pattern as contest_roll.py to avoid
circular imports). `_strike_hidden_ev` corrected from 0.45 to 0.50 (DC 11 = 10/20).
Anthem simplification uses `state.anthem_active` delta directly. Old evaluators
preserved in actions.py.

711 → 750 tests. EV 7.65 verified (29th).

## CP10.4.2 Status — COMPLETE

Created `pf2e/auto_state.py` (AutoStateDef, AUTO_STATE_REGISTRY with 4 entries,
_compute_ev(), _has_condition(), evaluate_auto_state()) and `tests/test_auto_state.py`
(24 tests). Modified `pf2e/actions.py` (2 new ActionTypes + `_wire_auto_state()`),
`sim/candidates.py` (DROP_PRONE, TAKE_COVER generation), `tests/test_evaluators.py`
(dispatcher expected set).

Key design note: `_has_condition()` bridges bool fields (prone, shield_raised) on
CombatantSnapshot to the registry's string-based requires_conditions tuples.

687 → 711 tests. EV 7.65 verified (28th).

## CP10.4.1 Status — COMPLETE

Created `pf2e/contest_roll.py` (ContestRollDef, DegreeEffect, CONTEST_ROLL_REGISTRY
with 5 entries, _condition_ev(), evaluate_contest_roll()) and
`tests/test_contest_roll.py` (30 tests). Modified `pf2e/actions.py` to delegate
5 action types via late-binding `_wire_contest_roll()`.

657 → 687 tests. EV 7.65 verified (27th).

## CP10.3 Status — COMPLETE

Created `pf2e/modifiers.py` (BonusType enum, BonusTracker class) and
`tests/test_modifiers.py` (30 tests).

Migrated 7 functions in `pf2e/combat_math.py` to use BonusTracker:
- `armor_class()` — shield=CIRC, off-guard=CIRC penalty, frightened=STATUS
- `attack_bonus()` — potency=ITEM, MAP=UNTYPED, frightened=STATUS, anthem=STATUS
- `save_bonus()`, `perception_bonus()`, `spell_attack_bonus()`, `skill_bonus()`, `lore_bonus()`

627 → 657 tests. EV 7.65 verified (26th).

## CP10.2 Status — COMPLETE

Created `pf2e/traits.py` (TraitCategory, TraitDef, TRAIT_REGISTRY with 9 slugs,
is_immune(), has_trait()) and `tests/test_traits.py` (30 tests).

Modified files:
- `pf2e/character.py` — added `immunity_tags: frozenset[str]` field
- `sim/round_state.py` — added `used_flourish_this_turn: bool` to CombatantSnapshot
- `sim/solver.py` — added `used_flourish_this_turn=False` to `_reset_turn_state()`

597 → 627 tests. EV 7.65 verified (25th).

## CP10.1 Status — COMPLETE

Created `pf2e/rolls.py` (RollType, FortuneState, flat_check) and
`tests/test_cp10_1_rolls.py` (19 tests). No existing files modified.

578 → 597 tests. EV 7.65 verified (24th).

## Known Bugs (Fixed by CP10)

- **Documentation error resolved (Pass 1.5):** Rook has no immunity tags. Demoralize/Fear behavior is correct.
- **~~Flourish not tracked~~ (CP10.2 data infrastructure):** `used_flourish_this_turn` field added. Enforcement in beam search deferred to CP10.4.
- **~~Cover+Raise Shield stacking~~ (CP10.3):** BonusTracker now enforces highest-only for same-type circumstance bonuses.

## Current Beam Search Parameters

K=50/20/10 at depth 1/2/3. Unchanged through all of CP10 (D37).

## Character Corrections (from Phase B Foundry importer)

These were corrected from the prior Pathbuilder-assumed values:
- **Rook primary weapon:** Earthbreaker d6 bludgeoning (was Longsword d8 slashing)
- **Aetregan:** WIS 10, CHA 12 (was WIS 12, CHA 10 — alternate ancestry boosts, JSON authoritative)
- **Aetregan:** Deception now trained (was untrained)
- **Aetregan:** Deity Lore removed (not in Foundry export)
- **Dalai:** Rapier Pistol d4 piercing (was Rapier d6 piercing)
- **Erisen:** Dueling Pistol d6 piercing (was Dagger d4 piercing); Leather Armor (was Studded Leather)

## Key Test Files

```
tests/test_combat_math.py       — D20Outcomes, derivation functions
tests/test_tactics.py           — Tactic evaluators, EV 7.65 regression
tests/test_grid.py              — Grid geometry
tests/test_scenario.py          — Scenario loading, killer validation
tests/test_search.py            — Beam search, full-round evaluation
tests/test_evaluators.py        — Action evaluators
tests/test_spells.py            — Spell chassis
tests/test_foundry_importer.py  — Phase B importer
tests/test_cp7_1_tactical.py    — Tactical reasoning fixes
tests/test_cp7_2_hand_state.py  — Hand state, spell slots
tests/test_cp10_1_rolls.py      — Roll foundation
tests/test_traits.py            — Trait system (CP10.2)
```
