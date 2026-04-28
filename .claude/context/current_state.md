# Current State

Last updated: April 2026, post-CP7.2 + CP10 architecture planning.

## Test Count

**578 tests passing.**

## Active Checkpoint

**CP10 — Nine-Layer Architecture Rebuild**

CP10.1 (Roll Foundation) is the next sub-checkpoint. Pass 1 brief is written. Pass 2 is pending.

## Killer Regression

**EV 7.65** — Strike Hard, Rook Earthbreaker reaction Strike with Anthem vs Bandit1 AC 15.
Verified 23 times (most recently at CP7.2 completion).

Note: EV was 8.55 through CP7.1. Changed to 7.65 in Phase B when Foundry importer
corrected Rook's weapon from Longsword (d8) to Earthbreaker (d6). This is correct per
authoritative Foundry character JSON.

## CP10.1 Status

- Pass 1 brief: **WRITTEN** (full spec in `.claude/context/cp10_architecture.md`)
- Pass 2: **PENDING** — resolve 4 open questions, then produce Pass 2 brief for CLI agent
- Pass 3 (CLI agent implementation): not started

**Open questions for Pass 2 (from cp10_architecture.md):**
1. Count of hardcoded flat check fractions in `actions.py` (CLI agent reports before implementation)
2. Confirm D34: `D20Outcomes` stays in `combat_math.py` through CP10.3
3. Fortune distribution math location — recommend `rolls.py`, confirm
4. Whether to encode nat-1/nat-20 rule explicitly on `RollType.STANDARD` now or defer

## Files to Create in CP10.1

```
pf2e/rolls.py              (new — ~55 lines)
tests/test_cp10_1_rolls.py (new — ~80 lines)
```

**No existing files modified in CP10.1.**

## Expected Test Count After CP10.1

578 → ~597-600 tests

## Known Bugs (Fixed by CP10)

- **Rook Demoralize/Fear:** Engine offers and evaluates these against Rook (Automaton) as if
  they work. Automaton has mental/emotion immunity. Fix is CP10.2.
- **Flourish not tracked:** Beam can recommend 2 Flourish actions/turn. Fix is CP10.2.
- **Cover+Raise Shield stacking:** Both give +2 circumstance AC; correct is highest only = +2.
  Fix is CP10.3.

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
tests/test_cp10_1_rolls.py      — Roll foundation (to be created in CP10.1)
```
