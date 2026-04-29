# Current State

Last updated: April 2026, post-CP10.4.2 (AutoState Chassis).

## Test Count

**711 tests passing.**

## Active Checkpoint

**CP10 — Nine-Layer Architecture Rebuild**

CP10.1 (Roll Foundation) is **COMPLETE**.
CP10.2 (Trait System) is **COMPLETE**.
CP10.3 (Modifier Assembly) is **COMPLETE**.
CP10.4.1 (ContestRoll Chassis) is **COMPLETE**.
CP10.4.2 (AutoState Chassis) is **COMPLETE**. CP10.5 is next.

## Killer Regression

**EV 7.65** — Strike Hard, Rook Earthbreaker reaction Strike with Anthem vs Bandit1 AC 15.
Verified 28 times (most recently at CP10.4.2 completion).

Note: EV was 8.55 through CP7.1. Changed to 7.65 in Phase B when Foundry importer
corrected Rook's weapon from Longsword (d8) to Earthbreaker (d6). This is correct per
authoritative Foundry character JSON.

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
