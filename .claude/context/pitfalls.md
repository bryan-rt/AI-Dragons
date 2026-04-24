# Pitfalls

Accumulated gotchas from all checkpoints. Read this before starting work on any brief.

## PF2e Rule Pitfalls

### Attribute boost math
Attribute boosts add **+2 to score or +1 to modifier**, never +1 to score. Starting from 10, a single boost yields 12 (mod +1). Score 11 is not achievable via boosts. *Caught: CP0.5.*

### Mortar EV — boundary inclusion
Save outcomes use `total ≤ DC-10` for crit failure. The ≤ includes equality. For DC 17 vs +5 save, totals 6 AND 7 both crit-fail (rolls 1 and 2). *Caught: CP0.5.*

### Banner aura expansion when planted
Commander's base banner is 30-ft emanation. Plant Banner feat expands to 40-ft burst. Don't hardcode 30. *Caught: CP4.*

### Carried vs planted banner center
Carried banner aura is centered on the commander (follows them around). Planted banner aura is centered on the planted position (fixed). Getting this backward breaks aura checks. *Caught: CP4.5.*

### Scorpion Whip vs Whip
Aetregan uses Scorpion Whip (lethal). Same stats as Whip except the nonlethal trait is absent. *Caught: CP4.5.*

### Commander Perception is expert at L1
Not trained. Aetregan's Perception is +6 (Wis +1 + expert +5), not +4. *Caught: CP4.5.*

### 10-ft reach Chebyshev exception
A weapon with 10-ft reach (e.g., whip) can hit a target 2 diagonal squares away (Chebyshev 2), even though strict 5/10 diagonal math says that's 15 ft. This is a rules-level exception for weapon reach, NOT a general "within 10 ft" rule. Intercept Attack's 10-ft trigger uses strict `distance_ft`, not Chebyshev. *Caught: CP2.*

### Frightened affects AC, not damage
Frightened is a status penalty on *checks and DCs*. AC is a DC, so it's reduced. Damage rolls are not checks, so they're unaffected. *Caught: CP0.5.*

### Reactions bypass MAP
Reaction Strikes are always MAP 0, regardless of how many attacks have been made this turn. *Caught: CP1.*

### Enemies can be "harmless" for damage purposes
An `EnemyState` with `damage_dice=""` is a sentinel for "no modeled offense." Defensive EV computations early-return 0 for such enemies. Don't treat empty damage_dice as an error. *Caught: CP4.*

## Python / Code Pitfalls

### Mutable defaults in dataclass fields
Use `field(default_factory=dict)`, never `= {}`. The latter shares state across instances. *Standard Python gotcha.*

### Frozen dataclass with mutable dict field
Frozen prevents reassigning the field, not mutating the dict inside. Convention: don't mutate these after construction. Use `dataclasses.replace()` for updates.

### `None` vs `0` sentinels
`CombatantState.current_hp = None` means "at max HP" (compute from character). `current_hp = 0` means "at 0 HP" (dropped). They are not interchangeable. Use the `effective_current_hp` property to get a concrete int.

### Derived properties, not stored fields
`EnemyState.perception_dc` is a `@property` returning `10 + self.perception_bonus`. Don't try to construct `EnemyState(perception_dc=13)` — it will fail. Use `perception_bonus=3` instead.

### Dict ordering matters for test reproducibility
Python 3.7+ dicts are ordered by insertion. If tests compare against expected dicts, insertion order matters. Typically not an issue, but if you see flaky tests involving dict comparison, check this.

### Circular imports on dataclass hints
Don't put `from sim.X import Y` at top of `pf2e/Z.py`. If you need a type hint for an object that lives in `sim/`, use `TYPE_CHECKING` guard:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sim.grid import GridState
```

Then use `"GridState"` as string-quoted type hint.

## Testing Pitfalls

### Test count assertions
Each Pass 3 brief estimates a test count range. If your implementation falls outside the range, investigate:
- Way below: tests probably skipped or not run
- Way above: scope creep, likely added tests for things not in the brief
- In range: probably fine

### pytest.approx tolerance
Default `pytest.approx` tolerance is `1e-6` relative. For combat math EVs, use `abs=EV_TOLERANCE` where `EV_TOLERANCE = 0.01`. Too strict and floating-point drift breaks tests; too loose and real bugs slip through.

### Killer regression test
The Strike Hard EV 8.55 test in `tests/test_scenario.py::TestKillerValidation::test_strike_hard_from_disk` must pass at every checkpoint. If it breaks, you have a regression. Fix before moving on.

### Existing tests after `banner_planted` required param
CP4 made `banner_planted` a required parameter on `GridSpatialQueries`. If you add a new test and construct `GridSpatialQueries()` directly, you must pass `banner_planted=True` or `banner_planted=False`. Missing this is a TypeError, not a test failure — easy to debug but annoying.

### CombatantState.position vs character.abilities
`state.position` is on `CombatantState` (mutable). `state.character.abilities` is on the underlying immutable Character. Don't confuse these.

## Architecture Pitfalls

### Don't add to `tests/fixtures.py`
It's a backward-compat shim that re-exports from `sim/party.py`. New factories, constants, or logic go in `sim/party.py`. If you find yourself wanting to add to `fixtures.py`, you're in the wrong file.

### Don't import from `sim/` in `pf2e/`
Ever. If you need grid distance, use the `SpatialQueries.distance_ft()` Protocol method. If you need character positions, pass them as arguments. See `pf2e/tactics.py::intercept_attack_ev()` for the pattern.

### Don't add game-specific logic to `pf2e/`
The rules engine doesn't know about scenarios, search, or players. If something smells "game-y" and you're editing `pf2e/`, stop and consider if it should be in `sim/` instead.

## Brief Interpretation Pitfalls

### "Stub" means returns ineligible
When a brief says "stub evaluator returns ineligible," the evaluator must return `ActionResult(eligible=False, outcomes=(), ineligibility_reason="...")`. It must not return incorrect data.

### Canonical keys in dicts
When a brief specifies canonical keys for a dict (e.g., `damage_prevented_sources` uses "plant_banner_temp_hp", "gather_reposition", etc.), those exact strings are the contract. Don't use variants like "plantBannerTempHP" or "plant-banner-temp-hp".

### "Deferred to CP X" is binding
When a brief says "deferred to Checkpoint X.Y," do not implement it now. Even if you think it's a quick addition. Scope discipline protects future flexibility.

## Performance Pitfalls

### Don't optimize prematurely
CP5.1 algorithms (beam search, state cloning) will have performance concerns. Solve them *after* correctness is proven. A slow-but-correct algorithm is a much better baseline than a fast-but-wrong one.

### Deep cloning large objects
`RoundState` (CP5.1 3b) uses shallow cloning with frozenset conditions to avoid deep-copy overhead. Don't introduce deep copies into the search hot path without profiling first.

## Commit Pitfalls

### Don't commit broken tests
Always run `pytest tests/ -v` before committing. If some tests fail, either fix them or don't commit.

### Don't commit commented-out code
If code is obsolete, delete it. Git history preserves the old version.

### Keep commit messages checkpoint-referenced
"CP5.1 Pass 3a: foundation implementation" is clear. "fixes stuff" is not.
