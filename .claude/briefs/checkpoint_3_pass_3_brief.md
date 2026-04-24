# Checkpoint 3 Pass 3: Scenario Loading — Implementation

## Context

The Pass 2 architectural plan is approved with one style correction. Time to write code. This brief tells you exactly what to implement, in what order, with what tests.

**Standing rules apply**: verify against AoN, cite URLs in docstrings, read existing code first, surface discrepancies, don't expand scope, test what you build.

## One Style Correction from Pass 2 Review

The `_build_combatant` helper in your Pass 2 plan has asymmetric control flow (early return inside `else`, final statement only executed by the `g` branch). Use this cleaner version instead:

```python
def _build_combatant(token: str, pos: Pos, anthem_active: bool) -> CombatantState:
    """Build a CombatantState from a grid token + position.
    
    Rook (token 'g') uses make_rook_combat_state() which applies the
    full plate speed penalty. All others use from_character() directly.
    """
    if token == "g":
        state = make_rook_combat_state(anthem_active=anthem_active)
        state.position = pos
    else:
        factory = TOKEN_TO_FACTORY[token]
        state = CombatantState.from_character(
            factory(), position=pos, anthem_active=anthem_active,
        )
    return state
```

Single return at the bottom. Each branch fully constructs its state before the return.

## Pre-implementation: Read existing code

Before writing anything:

- `tests/fixtures.py` — you'll be moving factories out of this into `sim/party.py`
- `sim/grid.py` — especially `parse_map()` and `_ALLY_TOKENS`, `_ENEMY_TOKENS`, `_BANNER_TOKENS`
- `sim/grid_spatial.py` — `GridSpatialQueries` constructor signature
- `pf2e/character.py` — confirm `CombatantState.from_character` signature accepts `position` and `anthem_active`
- `pf2e/tactics.py` — `TacticContext` and `EnemyState` structures
- `tests/test_grid_spatial.py` — specifically the `TestSwapMockForGrid` killer test; this is the pattern you're replicating but loading from disk
- `CHANGELOG.md` — review Checkpoint 2 entry as a template

## Scope

### What to implement

1. **New module**: `sim/party.py` — move factories and equipment constants from `tests/fixtures.py`; add `TOKEN_TO_FACTORY` and `COMMANDER_TOKEN`.
2. **Update**: `tests/fixtures.py` — becomes a thin re-export shim importing from `sim/party.py`.
3. **New module**: `sim/scenario.py` — `Scenario` dataclass, `ScenarioParseError`, `parse_scenario()`, `load_scenario()`, `_build_combatant()` helper.
4. **New file**: `scenarios/checkpoint_1_strike_hard.scenario` — the canonical validation scenario.
5. **New test file**: `tests/test_scenario.py` — five integration tests including the EV 8.55 killer test.
6. **CHANGELOG update**: document Checkpoint 3.

### What NOT to implement

- No defensive value computation — Checkpoint 4
- No turn planning — Checkpoint 5
- No formatter — Checkpoint 6
- No multi-word enemy names (single-word only)
- No carried banner (planted only)
- No scenario-level tactic overrides
- No custom party composition (fixed four-PC party for now)

---

## Implementation Order

### Step 1: Create `sim/party.py` and update `tests/fixtures.py`

#### Step 1a: Create `sim/party.py`

Move from `tests/fixtures.py` into `sim/party.py`:
- All weapon/armor constants (`WHIP`, `LONGSWORD`, `RAPIER`, `JAVELIN`, `DAGGER`, `STEEL_SHIELD`, `SUBTERFUGE_SUIT`, `FULL_PLATE`, `LEATHER_ARMOR`, `STUDDED_LEATHER`, etc.)
- All character factory functions (`make_aetregan`, `make_rook`, `make_dalai`, `make_erisen`)
- The `make_rook_combat_state(anthem_active=False)` helper

Add at the end:

```python
from typing import Callable
from pf2e.character import Character

TOKEN_TO_FACTORY: dict[str, Callable[[], Character]] = {
    "c": make_aetregan,
    "g": make_rook,
    "b": make_dalai,
    "i": make_erisen,
}

COMMANDER_TOKEN = "c"
SQUADMATE_TOKENS: tuple[str, ...] = ("g", "b", "i")
```

Top-of-file docstring:

```python
"""Party definitions for the Outlaws of Alkenstar campaign.

Canonical character builds, equipment constants, and grid-token
factory mappings. Used by the scenario loader and test fixtures.
"""
```

#### Step 1b: Update `tests/fixtures.py`

Replace the old content with re-exports:

```python
"""Test fixtures — re-exports the canonical party from sim/party.py.

Historical location for factories; production code now lives in
sim/party.py. Tests import from here for backward compatibility.
"""

from sim.party import (
    WHIP, LONGSWORD, RAPIER, JAVELIN, DAGGER,
    STEEL_SHIELD, SUBTERFUGE_SUIT, FULL_PLATE,
    LEATHER_ARMOR, STUDDED_LEATHER,
    make_aetregan, make_rook, make_dalai, make_erisen,
    make_rook_combat_state,
)
```

Include every constant and function that existing tests import. Run `grep -rn "from tests.fixtures import"` across the codebase to make sure you catch all of them. If any test imports something not in your re-export list, add it.

#### Step 1c: Run all existing tests

`pytest tests/ -v`. All 171 tests must still pass. If anything breaks, stop and surface the failures before continuing — likely a missing re-export.

### Step 2: Create `sim/scenario.py`

Top-of-file:

```python
"""Scenario file loading: text → fully-wired TacticContext.

A scenario file bundles grid terrain, party positions, enemy stats,
banner state, and anthem state. load_scenario() reads from disk;
parse_scenario() parses a string. Both produce a Scenario object,
which exposes build_tactic_context() for evaluation.

File format (see scenarios/*.scenario for examples):

    [meta]
    name = <description>
    level = <int>
    source = <citation>
    description = <long text>
    
    [grid]
    <ASCII grid with tokens separated by whitespace>
    
    [banner]
    planted = true | false
    position = <row>, <col>
    
    [anthem]
    active = true | false
    
    [enemies]
    <token> name=<word> ac=<int> ref=<int> fort=<int> will=<int>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pf2e.character import Character, CombatantState, EnemyState
from pf2e.tactics import TacticContext
from pf2e.types import SaveType
from sim.grid import GridState, Pos, parse_map
from sim.grid_spatial import GridSpatialQueries
from sim.party import (
    COMMANDER_TOKEN, SQUADMATE_TOKENS, TOKEN_TO_FACTORY,
    make_rook_combat_state,
)


class ScenarioParseError(Exception):
    """Raised when a scenario file/string cannot be parsed."""
    pass
```

Then the `Scenario` dataclass:

```python
@dataclass(frozen=True)
class Scenario:
    """A fully-loaded combat scenario, ready to produce a TacticContext.
    
    Frozen — scenarios are built once from a file and don't change.
    The CombatantState objects inside are mutable (for transient state
    like reactions), but the Scenario wrapper cannot be reassigned.
    """
    name: str
    level: int
    source: str
    description: str
    
    grid: GridState
    banner_position: Pos | None
    banner_planted: bool
    
    anthem_active: bool
    
    commander: CombatantState
    squadmates: list[CombatantState]
    enemies: list[EnemyState]
    
    def build_tactic_context(self) -> TacticContext:
        """Produce a fresh TacticContext with GridSpatialQueries wired in.
        
        Constructs a new GridSpatialQueries each call. Safe to call
        multiple times; the returned contexts are independent.
        """
        spatial = GridSpatialQueries(
            grid_state=self.grid,
            commander=self.commander,
            squadmates=list(self.squadmates),
            enemies=list(self.enemies),
            banner_position=self.banner_position,
        )
        return TacticContext(
            commander=self.commander,
            squadmates=list(self.squadmates),
            enemies=list(self.enemies),
            banner_position=self.banner_position,
            banner_planted=self.banner_planted,
            spatial=spatial,
            anthem_active=self.anthem_active,
        )
```

Then `_build_combatant` (the corrected version from the top of this brief).

Then the parser functions. Structure the parser as:

```python
def load_scenario(path: str | Path) -> Scenario:
    """Read and parse a scenario file from disk."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_scenario(text)


def parse_scenario(text: str) -> Scenario:
    """Parse scenario text into a Scenario object."""
    sections = _split_into_sections(text)
    # Required: [grid]
    if "grid" not in sections:
        raise ScenarioParseError("Missing required [grid] section")
    
    meta = _parse_meta(sections.get("meta", ""))
    grid, positions, grid_banner_pos = parse_map(sections["grid"])
    banner_pos, banner_planted = _parse_banner(
        sections.get("banner"), grid_banner_pos,
    )
    anthem_active = _parse_anthem(sections.get("anthem"))
    enemy_specs = _parse_enemies(sections.get("enemies", ""))
    
    # Commander required
    if COMMANDER_TOKEN not in positions:
        raise ScenarioParseError(
            f"No commander ({COMMANDER_TOKEN!r}) token found in grid"
        )
    
    # Validate enemy tokens match
    grid_enemy_tokens = {
        t for t in positions
        if (t.startswith("m") or t.startswith("M"))
        and t != COMMANDER_TOKEN
        and any(c.isdigit() for c in t)
    }
    missing_stats = grid_enemy_tokens - enemy_specs.keys()
    missing_grid = enemy_specs.keys() - grid_enemy_tokens
    if missing_stats:
        raise ScenarioParseError(
            f"Enemy tokens in grid with no [enemies] stats: {sorted(missing_stats)}"
        )
    if missing_grid:
        raise ScenarioParseError(
            f"[enemies] entries with no grid token: {sorted(missing_grid)}"
        )
    
    # Build party
    commander = _build_combatant(
        COMMANDER_TOKEN, positions[COMMANDER_TOKEN], anthem_active,
    )
    squadmates = [
        _build_combatant(tok, positions[tok], anthem_active)
        for tok in SQUADMATE_TOKENS if tok in positions
    ]
    
    # Build enemies
    enemies = [
        _build_enemy(spec, positions[token])
        for token, spec in enemy_specs.items()
    ]
    
    return Scenario(
        name=meta.get("name", "Untitled"),
        level=int(meta.get("level", 1)),
        source=meta.get("source", ""),
        description=meta.get("description", ""),
        grid=grid,
        banner_position=banner_pos,
        banner_planted=banner_planted,
        anthem_active=anthem_active,
        commander=commander,
        squadmates=squadmates,
        enemies=enemies,
    )
```

The helper functions `_split_into_sections`, `_parse_meta`, `_parse_banner`, `_parse_anthem`, `_parse_enemies`, `_build_enemy` are your responsibility. Sketch:

**`_split_into_sections(text) -> dict[str, str]`**: Walk lines, skip `#` comments and blanks, detect `[section]` headers (strip whitespace, lowercase), collect subsequent lines as section content until the next header or EOF. Return dict of section_name → content_string.

**`_parse_meta(text) -> dict[str, str]`**: Split lines, parse `key = value` with value being "everything after the `=` stripped." Return dict.

**`_parse_banner(text, grid_fallback_pos) -> tuple[Pos | None, bool]`**: If text is empty/None and grid_fallback_pos is None → (None, False). If text is empty/None and grid_fallback_pos exists → (grid_fallback_pos, True). If text exists, parse `planted = true/false` and `position = row, col`. If planted != true, raise ScenarioParseError (carried banner deferred).

**`_parse_anthem(text) -> bool`**: If text empty/None → False. Otherwise parse `active = true/false`.

**`_parse_enemies(text) -> dict[str, dict[str, str]]`**: One enemy per non-blank line. First whitespace-separated token is the grid token; remaining tokens are `key=value` pairs (no spaces around `=`). Return `{token: {key: value}}` dict.

**`_build_enemy(spec, pos) -> EnemyState`**: Required keys: `name`, `ac`, `ref`, `fort`, `will`. Optional: `off_guard`, `prone` (default false). Raise ScenarioParseError with clear message if required keys missing or integer parsing fails.

Enemy token regex for validation: a token is an "enemy token" if it matches `[mM]\d+` (m or M followed by digits). Auto-numbered tokens from `parse_map` always follow this pattern.

### Step 3: Create `scenarios/checkpoint_1_strike_hard.scenario`

Exact contents:

```
# scenarios/checkpoint_1_strike_hard.scenario
# Recreates the Checkpoint 1 and Checkpoint 2 Strike Hard killer test.
# Expected: Strike Hard! -> Rook longsword reaction Strike, EV 8.55.

[meta]
name = Strike Hard Validation
level = 1
source = Checkpoint 1 ground truth
description = Rook adjacent to Bandit1 in banner aura. Anthem active.

[grid]
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . c g m . .
. . . . i b . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .

[banner]
planted = true
position = 5, 5

[anthem]
active = true

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
```

Grid layout verification:
- Row 5: `c` at (5,5), `g` at (5,6), `m` at (5,7) → auto-numbered `m1`
- Row 6: `i` at (6,4), `b` at (6,5)
- Banner at (5,5) = Aetregan's position
- Rook at (5,6), Bandit1 at (5,7) — Chebyshev distance 1, adjacent
- Rook distance from banner: 5 ft, in 30-ft aura
- Anthem active → +1 attack/+1 damage

This produces EV = 8.55 for Rook's longsword reaction Strike.

### Step 4: Create `tests/test_scenario.py`

```python
"""Tests for sim/scenario.py — scenario loading and TacticContext building."""

import pytest

from pf2e.tactics import STRIKE_HARD, evaluate_tactic
from sim.scenario import (
    Scenario, ScenarioParseError, load_scenario, parse_scenario,
)

EV_TOLERANCE = 0.01
SCENARIOS_DIR = "scenarios"


# ---------------------------------------------------------------------------
# Test A: Killer validation — load from disk, evaluate, EV 8.55
# ---------------------------------------------------------------------------

class TestKillerValidation:
    """The canonical end-to-end test: file -> grid -> tactics -> EV 8.55."""
    
    def test_strike_hard_from_disk(self):
        scenario = load_scenario(
            f"{SCENARIOS_DIR}/checkpoint_1_strike_hard.scenario"
        )
        assert scenario.name == "Strike Hard Validation"
        assert scenario.level == 1
        assert scenario.banner_planted is True
        assert scenario.banner_position == (5, 5)
        assert scenario.anthem_active is True
        assert len(scenario.squadmates) == 3
        assert len(scenario.enemies) == 1
        assert scenario.enemies[0].name == "Bandit1"
        
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        
        assert result.eligible
        assert result.best_target_ally == "Rook"
        assert result.best_target_enemy == "Bandit1"
        assert result.expected_damage_dealt == pytest.approx(
            8.55, abs=EV_TOLERANCE,
        )


# ---------------------------------------------------------------------------
# Test B: Parse error handling
# ---------------------------------------------------------------------------

class TestParseErrors:
    
    def test_missing_grid_section(self):
        text = """
[meta]
name = broken

[enemies]
m1 name=X ac=10 ref=0 fort=0 will=0
"""
        with pytest.raises(ScenarioParseError, match="grid"):
            parse_scenario(text)
    
    def test_missing_commander_in_grid(self):
        text = """
[grid]
. . . . .
. g . m .
. . . . .

[enemies]
m1 name=X ac=10 ref=0 fort=0 will=0
"""
        with pytest.raises(ScenarioParseError, match="commander"):
            parse_scenario(text)
    
    def test_enemy_in_grid_no_stats(self):
        text = """
[grid]
. . . . .
. c g m .
. . . . .
"""
        # m in grid becomes m1, no [enemies] section exists
        with pytest.raises(ScenarioParseError, match="m1"):
            parse_scenario(text)
    
    def test_enemy_stats_no_grid_token(self):
        text = """
[grid]
. . . . .
. c g . .
. . . . .

[enemies]
m1 name=Ghost ac=14 ref=2 fort=2 will=2
"""
        with pytest.raises(ScenarioParseError, match="m1"):
            parse_scenario(text)
    
    def test_invalid_integer_in_enemy_stats(self):
        text = """
[grid]
. . . . .
. c g m .
. . . . .

[enemies]
m1 name=X ac=abc ref=5 fort=3 will=2
"""
        with pytest.raises(ScenarioParseError):
            parse_scenario(text)


# ---------------------------------------------------------------------------
# Test C: Minimal scenario (no banner, no anthem)
# ---------------------------------------------------------------------------

class TestMinimalScenario:
    
    def test_no_banner_no_anthem(self):
        text = """
[grid]
. . . . . .
. c g . m .
. . . . . .

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
"""
        scenario = parse_scenario(text)
        assert scenario.banner_position is None
        assert scenario.banner_planted is False
        assert scenario.anthem_active is False
        
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        # No banner means no aura, so no squadmates can respond to Strike Hard
        assert not result.eligible
        assert "aura" in result.ineligibility_reason.lower()


# ---------------------------------------------------------------------------
# Test D: Grid banner fallback (no [banner] section)
# ---------------------------------------------------------------------------

class TestGridBannerFallback:
    
    def test_grid_B_token_populates_banner(self):
        text = """
[grid]
. . . . . .
. c g B . .
. . . . . .
"""
        scenario = parse_scenario(text)
        # No [banner] section, but grid has B token — use it
        assert scenario.banner_position == (1, 3)
        assert scenario.banner_planted is True


# ---------------------------------------------------------------------------
# Test E: parse_scenario with inline text
# ---------------------------------------------------------------------------

class TestInlineParse:
    
    def test_inline_full_scenario(self):
        """parse_scenario works without touching the filesystem."""
        text = """
[meta]
name = Inline Test

[grid]
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . c g m . .
. . . . i b . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .

[banner]
planted = true
position = 5, 5

[anthem]
active = true

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
"""
        scenario = parse_scenario(text)
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.eligible
        assert result.expected_damage_dealt == pytest.approx(
            8.55, abs=EV_TOLERANCE,
        )
```

### Step 5: Update CHANGELOG.md

Append a new section:

```markdown
## [3.0] - Checkpoint 3: Scenario Loading

### New module: sim/party.py
- Moved factories and equipment constants from tests/fixtures.py.
- Added TOKEN_TO_FACTORY (dict[token, factory]), COMMANDER_TOKEN, SQUADMATE_TOKENS.
- tests/fixtures.py becomes a re-export shim for backward compatibility.

### New module: sim/scenario.py
- Scenario (frozen dataclass) bundling grid, banner state, anthem state,
  commander, squadmates, enemies, and metadata.
- parse_scenario(text) and load_scenario(path) functions.
- ScenarioParseError for all parsing failures.
- Scenario.build_tactic_context() produces a ready-to-evaluate TacticContext
  with GridSpatialQueries wired in.

### New scenario: scenarios/checkpoint_1_strike_hard.scenario
- Canonical end-to-end validation scenario.
- Recreates the Checkpoint 1/2 Strike Hard test.
- Load + evaluate produces EV 8.55, identical to the mocked and
  grid-only validations from prior checkpoints.

### File format
- Section-based text format (.scenario extension): [meta], [grid],
  [banner], [anthem], [enemies]. Comments via leading #.
- Coordinates as `row, col`. Booleans as `true`/`false`.
- [banner] section is authoritative over grid B/* tokens.
- Commander token ('c') is required; squadmate tokens optional
  (absent = not in the encounter).

### Validation and error handling
- Missing [grid] section → ScenarioParseError
- Missing commander token → ScenarioParseError
- Enemy token in grid without matching [enemies] stats → ScenarioParseError
- [enemies] entry without matching grid token → ScenarioParseError
- Invalid integer / boolean parsing → ScenarioParseError

### Design decisions
- Frozen Scenario; build_tactic_context() constructs fresh
  GridSpatialQueries per call (no caching, no stale positions).
- Single-word enemy names only (multi-word deferred to future work).
- Carried banner deferred (planted only for Checkpoint 3).
- Non-default party composition deferred.
```

---

## Validation Checklist

- [ ] Step 1: All 171 existing tests still pass after the factory move
- [ ] Step 2: `sim/scenario.py` implements parser and Scenario dataclass
- [ ] Step 3: `scenarios/checkpoint_1_strike_hard.scenario` file exists with exact content
- [ ] Step 4: Five test classes added
- [ ] **Killer test passes**: TestKillerValidation loads from disk, evaluates Strike Hard, gets EV 8.55
- [ ] Parse error tests all raise ScenarioParseError with descriptive messages
- [ ] Minimal scenario test confirms absent `[banner]`/`[anthem]` default correctly
- [ ] Grid banner fallback test passes
- [ ] Inline parse test passes (filesystem-independent)
- [ ] Target: ~185-195 tests total passing
- [ ] CHANGELOG updated
- [ ] All docstrings cite AoN URLs where mechanical claims appear
- [ ] No files created outside the ones listed in Scope

## Common Pitfalls

**Circular import risk.** `sim/scenario.py` imports from `pf2e/tactics.py` (for `TacticContext`). `pf2e/tactics.py` may re-export `EnemyState` from `pf2e/character.py`. Make sure the import chain doesn't cycle. Run `pytest` to catch any cycle.

**The `tests/fixtures.py` re-export must be exhaustive.** If any test imports a constant or function that didn't make it into the re-export list, it'll fail with `ImportError`. Grep all test files for imports from `tests.fixtures` before considering Step 1 complete.

**Enemy token regex.** An "enemy token" is one that matches the pattern letter-followed-by-digits (e.g., `m1`, `M2`, `m10`). The grid parser produces these via auto-numbering. Don't match bare `m` or `M` — those shouldn't appear in the positions dict (parse_map auto-numbers them).

**Banner fallback logic.** Four cases to handle:
1. `[banner]` section present + valid → use it
2. `[banner]` section absent + grid has B/* → use grid position with planted=true
3. Both present → `[banner]` section wins (section authoritative)
4. Neither → `banner_position = None, banner_planted = False`

The `parse_map` function already returns the grid banner position as its third tuple element. Use that as the fallback argument when parsing the `[banner]` section.

**CombatantState.from_character has `position` and `anthem_active` as kwargs.** Verified in Pass 2. Pass them directly for non-Rook party members. For Rook (token `g`), use `make_rook_combat_state(anthem_active=...)` and set `state.position = pos` after.

**Anthem buff is +1 status to attack AND damage.** With anthem_active, Rook's longsword EV is 8.55 (not 6.80 from the no-Anthem case). The fixture `make_rook_combat_state(anthem_active=True)` handles this; just make sure you pass `anthem_active=True` when constructing per the scenario's `[anthem]` section.

**Line endings in the scenario file.** The parser should handle both `\n` and `\r\n` line endings. `splitlines()` does this automatically; `split("\n")` does not. Prefer `splitlines()`.

## What Comes After

1. You implement everything above.
2. You run `pytest tests/ -v` and confirm 100% pass.
3. You push the repo.
4. I review via the code files.
5. We move to Checkpoint 4: Defensive value computation — the architecturally novel part of the project (Shield Block, Intercept Attack, repositioning to dodge, AoE friendly-fire assessment). This is where the "expected_damage_avoided" field on TacticResult gets populated for real.
