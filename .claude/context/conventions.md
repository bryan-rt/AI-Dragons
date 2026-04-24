# Code Conventions

## Style

- **Python 3.10+ syntax.** Use `X | None` not `Optional[X]`. Use `list[X]` not `List[X]`.
- **Type hints on public APIs.** Private helpers may skip hints when obvious.
- **Imports sorted.** Standard library, third-party (pytest only in tests), local. No `from X import *`.
- **Line length: not strictly enforced.** Aim for ~100 chars, but readability wins.

## Dataclass Conventions

- **Frozen dataclasses for value types.** `Character`, `Weapon`, `ArmorData`, `Shield`, `EquippedWeapon`, `WeaponRunes`, `TacticDefinition`, `TacticResult`, `Action`, `ActionOutcome`, `ActionResult`, `Scenario`.
- **Mutable dataclasses for state.** `CombatantState`, `EnemyState`, `RoundState` (when added).
- **Mutable dict/set fields in frozen dataclasses** are allowed for skill_proficiencies, lores, etc. Do NOT mutate them after construction by convention. Use `dataclasses.replace()` to produce new instances.
- **`field(default_factory=dict)` / `field(default_factory=list)`** for mutable defaults. Never use `= {}` as default.

## Naming

- **snake_case** for functions, methods, variables, module names.
- **PascalCase** for classes, enums, type aliases.
- **SCREAMING_SNAKE_CASE** for module-level constants.
- **Leading underscore** for module-private helpers: `_evaluate_reaction_strike`, `_build_combatant`.
- **Verb-based for functions computing values:** `attack_bonus()`, `expected_strike_damage()`, `shortest_movement_cost()`.
- **Noun-based for data accessors:** `armor_class()` (returns a number, is_a_number-noun).
- **`is_X` and `has_X`** for boolean properties.

## Docstrings

Every public function has a docstring. Format:

```python
def function_name(args) -> ReturnType:
    """One-line summary.
    
    Longer explanation if needed. What the function computes, not how.
    
    Args:
        arg_name: What it is.
    
    Returns:
        What the return value represents.
    
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=XXXX)
    """
```

- **AoN URL in the docstring** for any function that implements a specific PF2e rule. Multiple URLs on separate lines.
- **Inline comments for non-obvious rule applications.** E.g., "# Plant Banner expands aura to 40 ft (AoN: ...)".
- **Explain discrepancies.** If the code diverges from the "obvious" PF2e rule (e.g., BFS uses uniform 5-ft instead of 5/10 alternation), document why.

## Testing Patterns

- **One test class per conceptual thing being tested.** E.g., `TestArmorClass`, `TestAttackBonus`.
- **Test method names start with `test_`.** Specific and descriptive: `test_rook_ac_no_shield`, not `test_ac`.
- **Use `pytest.approx` for floating-point comparisons.** Tolerance `abs=EV_TOLERANCE` where `EV_TOLERANCE = 0.01` at the top of the file.
- **Parametrize when testing the same logic with multiple inputs.** Use `@pytest.mark.parametrize`.
- **Fixtures in `conftest.py`** for shared across files, or as `@pytest.fixture` in the test file for local use.
- **Use the canonical fixtures from `tests/fixtures.py`** (`make_aetregan`, `make_rook`, etc.). Don't build characters from scratch in tests.

## File Organization

When adding a new class or function:

1. **Does it fit in an existing module?** Add it there if yes. Don't create new modules unless a clear concept boundary exists.
2. **If creating a new module:** add an `"""..."""` module docstring at the top explaining scope.
3. **Import order:** `__future__` first, then standard library, then third-party (pytest in tests only), then local.

## Tests for New Code

Every new function needs tests. Target coverage:
- Happy path (normal usage)
- Edge cases (zero, boundary values, empty inputs)
- Error cases (invalid inputs, raises expected exceptions)

For combat math specifically:
- Verify against hand-computed expected values
- Verify against AoN rule examples when provided
- Include regression tests for corrected discrepancies

## CHANGELOG Format

Every checkpoint updates `CHANGELOG.md`:

```markdown
## [X.Y] - Checkpoint Name

Brief description of what shipped.

### Category 1
- Specific change (AoN link if relevant)
- Another change

### Category 2
- More changes

### Deferred to Checkpoint Y+1
- What was intentionally left out
```

Most recent entry goes at the top (reverse chronological).

## Commit Messages

- **First line: brief subject, 50 chars or less.** "CP5.1 Pass 3a: foundation implementation"
- **Blank line, then body if needed.** Bullets listing major changes.
- **Reference GitHub issues or PRs if applicable.** We don't use them much currently.

## AoN Verification

- **Before implementing a rule, verify at AoN.** Don't rely on memory.
- **If AoN says X and you had implemented Y, update to X and add a citation.** This is not a "bug"; it's the normal research process.
- **If a rule seems wrong or inconsistent with itself, flag it** — PF2e occasionally has edge cases where different rule sections disagree, and we need a human decision.

## Scope Discipline

- **The brief is the scope. Period.** If the brief says "15 action types," that's all you implement.
- **Flag out-of-scope issues; don't fix them inline.** If you notice a bug while implementing the brief, note it for review. Don't "while I'm here" fix it.
- **Deferred items stay deferred.** Every Pass 3 brief has a "What NOT to implement" section. Respect it.

## When to Ask for Clarification

- **Rule interpretation questions.** If two AoN rules seem to contradict, ask.
- **Architectural choices not covered by the brief.** If the brief is silent on something, make a reasonable choice but flag it in the commit message.
- **Unexpected test failures.** If existing tests fail after your changes and you don't understand why, stop and investigate. Don't "fix" them by changing expected values without understanding.

## Logging and Diagnostic Output

For simple rule-derivation code (combat math, equipment, character builders), tests provide enough visibility. Don't add logging.

For complex algorithms (search, state threading, multi-step evaluators), logging is essential for debugging. When a brief introduces algorithmic work, it will specify logging requirements. Follow them:

- **Use the standard library `logging` module.** No print statements in production code. Tests may use print for debug output during development but should be cleaned before committing.
- **Logger per module:** `logger = logging.getLogger(__name__)` at module top. Propagates to the root logger; user controls verbosity.
- **Log levels:**
  - `DEBUG`: per-iteration detail (beam state per depth, each candidate evaluated, scoring breakdowns)
  - `INFO`: checkpoint-level events (round start, action chosen, EV of final plan)
  - `WARNING`: recoverable anomalies (probability sum drift, unexpected empty result)
  - `ERROR`: genuine bugs that should not happen in validated code
- **CLI flags for diagnostic output.** Algorithm-heavy modules expose `--debug-search` or similar flags that set logger levels at runtime. The flag is documented in the brief that introduces it.
- **Logged data is structured.** Prefer f-string formatting of specific fields over dumping whole objects. `logger.debug(f"Beam depth {d}: {len(beam)} candidates, best EV {best:.2f}")` — not `logger.debug(f"Beam: {beam}")`.
- **Tests may assert on log output** for critical paths. Use `caplog` fixture in pytest when verifying that warnings fire when expected.

## Diagnostic Conventions for Complex Algorithm Work

When reviewing output from complex algorithms during development:

- Dump full state at a specific depth or iteration with a CLI flag, not by editing the code
- Probability sums should be verified with `ActionResult.verify_probability_sum()` in any test that constructs action results
- When EVs don't match expectations, log the inputs (bonuses, DCs, outcome counts) before changing anything — the bug is usually upstream of where you first noticed it
- Keep a "killer regression" test at every checkpoint. Small regressions in beam search can shift EVs by fractions; the killer test is your canary
