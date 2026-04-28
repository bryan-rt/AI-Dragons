# Current State

Last updated: April 2026, post-CP10.1 (Roll Foundation).

## Test Count

**597 tests passing.**

## Active Checkpoint

**CP10 — Nine-Layer Architecture Rebuild**

CP10.1 (Roll Foundation) is **COMPLETE**. CP10.2 is next.

## Killer Regression

**EV 7.65** — Strike Hard, Rook Earthbreaker reaction Strike with Anthem vs Bandit1 AC 15.
Verified 24 times (most recently at CP10.1 completion).

Note: EV was 8.55 through CP7.1. Changed to 7.65 in Phase B when Foundry importer
corrected Rook's weapon from Longsword (d8) to Earthbreaker (d6). This is correct per
authoritative Foundry character JSON.

## CP10.1 Status — COMPLETE

Created `pf2e/rolls.py` (RollType, FortuneState, flat_check) and
`tests/test_cp10_1_rolls.py` (19 tests). No existing files modified.

578 → 597 tests. EV 7.65 verified (24th).

## Known Bugs (Fixed by CP10)

- **Documentation error resolved (Pass 1.5):** Rook has no immunity tags. Demoralize/Fear behavior is correct.
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
