# Checkpoint 3 Pass 1: Scenario Loading — Architectural Plan

## Context

Checkpoints 1 and 2 are complete (171/171 tests passing). The tactic dispatcher works against a real grid via `GridSpatialQueries`. Checkpoint 3 ties these layers together with a scenario loader that reads a text file and produces a fully-wired `TacticContext` ready to evaluate.

This is Pass 1 of the three-pass loop for Checkpoint 3. Produce an architectural plan — not code. After my review we'll do Pass 2 (corrections) and Pass 3 (implementation).

## Standing Rules

1. Verify rules against AoN. Cite URLs. Mark unverified claims as UNVERIFIED.
2. Cite AoN URLs in docstrings for non-trivial mechanics.
3. Read existing code first: `sim/grid.py`, `sim/grid_spatial.py`, `pf2e/tactics.py`, `pf2e/character.py`, `tests/fixtures.py`, `tests/test_grid_spatial.py` (especially the killer test that this checkpoint is modeled on).
4. Surface discrepancies, don't silently fix them.
5. Don't expand scope.
6. Describe test cases, don't write them.

## Your Task

Design the scenario-loading layer that converts a text file into a fully-initialized `Scenario` object, with a factory method producing a ready-to-evaluate `TacticContext`.

## Scope

### In scope

- `sim/scenario.py` — `Scenario` dataclass + `load_scenario()` parser + `build_tactic_context()` factory
- A text file format (with section headers) for declaring scenarios
- Character factory mapping (grid tokens → party member factories from `tests/fixtures.py`)
- Enemy declaration parsing (stats per enemy, keyed by grid token)
- Banner and anthem state declaration
- Encounter metadata (name, level, source citation)
- A `scenarios/` top-level directory with at least one example scenario (the Checkpoint 1 Strike Hard test)
- Integration tests that load scenarios from disk and validate EV against Checkpoint 1/2 ground truth

### Out of scope

- No defensive value computation — Checkpoint 4
- No turn planning — Checkpoint 5
- No formatter — Checkpoint 6
- No level-up or multi-level scenarios — Checkpoint 8
- No real Outlaws of Alkenstar AP scenarios — Checkpoint 9
- No scenario variants, templates, or inheritance
- No persistent state across turns
- No external format support (YAML, TOML, JSON)

## What the Plan Must Cover

### 1. File format design

Propose a concrete section-based text format. My starting recommendation:

```
[meta]
name = Strike Hard Test
level = 1
source = Internal test fixture
description = Rook adjacent to Bandit1 in banner aura. Expected EV 8.55.

[grid]
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . c g m1 . .
. . . . i d . . . .
. . . . . . . . . .
. . . . . . . . . .
. . . . . . . . . .

[banner]
position = (5, 5)
planted = true

[anthem]
active = true

[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
```

Decide:

- **Section delimiters**: `[section]` brackets? Or something else?
- **Comments**: support `#` line comments? Yes — essential for annotation.
- **Key-value syntax**: `key = value` with spaces, or `key=value` without? Be consistent.
- **Multi-token keys**: `m1 name=Bandit1 ac=15 ref=5` — all on one line, whitespace-separated? Or one key per line?
- **Coordinates**: `(row, col)` with parens? Or `5,5` without? Or two separate keys `row = 5; col = 5`?
- **Escape rules**: how to handle values with spaces in them (e.g., `description = Rook adjacent to Bandit1`)? Probably just "rest of line after `=`" is the value.
- **File extension**: `.txt`, `.scn`, or no extension? Recommend `.txt` for portability.
- **Encoding**: UTF-8.

Propose the exact syntax and parser behavior. The parser should produce clear error messages when sections are missing or malformed.

### 2. Scenario dataclass

Sketch the structure:

```python
@dataclass
class Scenario:
    # Metadata
    name: str
    level: int
    source: str
    description: str
    
    # Grid and banner
    grid: GridState
    banner_position: Pos | None
    banner_planted: bool
    
    # Anthem state
    anthem_active: bool
    
    # Party (positioned on the grid)
    commander: CombatantState
    squadmates: list[CombatantState]
    
    # Enemies (with positions, AC, saves)
    enemies: list[EnemyState]
    
    def build_tactic_context(self) -> TacticContext:
        ...
```

Decide:

- **Frozen or mutable?** Scenarios load once; their contents don't change during normal use. Recommend frozen to match `Character`.
- **Should `Scenario` hold the `GridSpatialQueries` instance?** Or construct it fresh in `build_tactic_context()`? Recommend constructing fresh — if positions change during simulation (Checkpoint 5 territory), a stale cached spatial queries object would silently produce wrong answers.
- **What should `build_tactic_context()` return?** A fully-wired `TacticContext` with `spatial = GridSpatialQueries(...)` installed.

### 3. Character factory mapping

For Checkpoint 3, the party is fixed: Aetregan, Rook, Dalai, Erisen. The grid tokens map to factory functions:

```python
_PARTY_FACTORIES = {
    "c": make_aetregan,   # Commander
    "g": make_rook,        # Guardian
    "b": make_dalai,       # Bard
    "i": make_erisen,      # Inventor
}
```

Decide:

- **Where does this mapping live?** Probably `sim/scenario.py` as a module-level constant, imported from `tests/fixtures.py`. This creates a dependency `sim/` → `tests/` which is backwards (tests should depend on sim, not vice versa). Better: **move the factories from `tests/fixtures.py` to a new module** like `sim/party.py` or `pf2e/party.py`, and have both `sim/scenario.py` and `tests/fixtures.py` import from there. Recommend a location.
- **Anthem propagation**: the `[anthem] active = true` flag should set `anthem_active=True` when building every party member's CombatantState. Confirm the factory functions accept this parameter (they should — Rook's does via `make_rook_combat_state(anthem_active=...)`). If the other factories don't, the loader will need to wire anthem state manually after construction.
- **Position assignment**: after each CombatantState is built, set its `.position` from the grid's parsed positions dict. For token `c`, `state.position = positions["c"]`.

Flag anything tricky about Rook specifically — he has a two-step construction (`make_rook_combat_state` applies the armor speed penalty). The scenario loader needs to call the right helper.

### 4. Enemy declaration format

Enemies appear in the grid as auto-numbered tokens (`m1`, `M1`, etc). Their stats come from the `[enemies]` section:

```
[enemies]
m1 name=Bandit1 ac=15 ref=5 fort=3 will=2
M1 name=Brute1 ac=17 ref=4 fort=8 will=5
```

Decide:

- **Required fields**: `name`, `ac`, `ref`, `fort`, `will`. Anything else?
- **Optional fields for Checkpoint 3**: `off_guard` (bool, default false), `prone` (bool, default false)? Probably yes — some scenarios may start with enemies already conditioned.
- **HP**: omitted for now? EnemyState has no HP field (all damage is EV, not actual HP tracking). Don't add HP until Checkpoint 5 or later needs it.
- **Creature size**: all enemies are Medium for now. Add a `size` field later if/when Large creatures matter.
- **Multi-word names**: `name=Bandit Captain` — does "Bandit Captain" parse correctly? With `key=value` split by `=` then whitespace, you get `name=Bandit` and then `Captain` as a stray token. Either require quotes (`name="Bandit Captain"`) or require single-word names for now. Recommend single-word names; flag as future work.

Validation:
- Every enemy token in the grid must have a matching line in `[enemies]`.
- Every line in `[enemies]` must correspond to a token in the grid.
- Missing or extra → clear error message.

### 5. Banner and anthem sections

`[banner]`:
- `position = (row, col)` — explicit coordinates. The banner has no token in the grid.
- `planted = true/false` — if false, the banner is carried (commander's position). For Checkpoint 3, planted = true most of the time; carried banner behavior is nuanced (aura moves with the commander). Recommend: for Checkpoint 3, require `planted = true`. Flag carried-banner as Checkpoint 4+ work.

`[anthem]`:
- `active = true/false` — if true, all squadmates and commander get the Courageous Anthem buff. Enemies do not.

Decide:

- **Should the grid support banner tokens (`B` or `*`)?** Or is the `[banner]` section the only way? Recommend: `[banner]` section is authoritative. The grid's `B`/`*` parsing (from Checkpoint 2) stays working for standalone grid tests but is ignored by the scenario loader. This lets the commander stand on the banner square without token collision.
- **If `[banner]` is omitted, what happens?** The scenario has no banner — `banner_position = None`, `banner_planted = False`. Several tactics will be ineligible (Strike Hard requires squadmates in aura). That's correct behavior.

### 6. `build_tactic_context()` method

The factory that produces a ready-to-evaluate context:

```python
def build_tactic_context(self) -> TacticContext:
    """Produce a TacticContext with GridSpatialQueries wired in."""
    spatial = GridSpatialQueries(
        grid_state=self.grid,
        commander=self.commander,
        squadmates=self.squadmates,
        enemies=self.enemies,
        banner_position=self.banner_position,
    )
    return TacticContext(
        commander=self.commander,
        squadmates=self.squadmates,
        enemies=self.enemies,
        banner_position=self.banner_position,
        banner_planted=self.banner_planted,
        spatial=spatial,
        anthem_active=self.anthem_active,
    )
```

This is the method every downstream consumer (Checkpoint 5 turn evaluator, Checkpoint 6 CLI) will call. Make it the stable public API.

Consider:

- **Should it cache?** No — positions could change between calls. Construct fresh each time.
- **Should it accept overrides?** e.g., "same scenario but swap in a different enemy" — no, keep it simple. Overrides are future work.

### 7. Loader function signature

```python
def load_scenario(path: str | Path) -> Scenario:
    """Parse a scenario file from disk into a Scenario object."""

def parse_scenario(text: str) -> Scenario:
    """Parse scenario text (useful for tests that embed scenarios inline)."""
```

Decide:

- **Separate load_scenario (file I/O) from parse_scenario (pure)?** Recommend yes. Tests can use `parse_scenario(SCENARIO_STRING)` without touching the filesystem.
- **Error types**: raise `ScenarioParseError` for all parsing failures. Include file path and line number in error messages where possible.

### 8. Example scenario file

Create `scenarios/checkpoint_1_strike_hard.txt` recreating the Checkpoint 1 Strike Hard test scenario exactly:

- Grid with Rook adjacent to Bandit1 and both in banner aura
- Banner at Aetregan's position
- Anthem active
- Bandit1 stats: AC 15, Reflex +5, Fort +3, Will +2

Loading this and evaluating Strike Hard must produce EV 8.55, matching Checkpoint 1 and Checkpoint 2's killer tests. This is the canonical end-to-end validation.

Sketch the exact file contents in your plan.

### 9. Integration test scope

Describe 3-4 integration tests:

**Test A: Roundtrip validation against Checkpoint 1/2 ground truth.**  
Load `scenarios/checkpoint_1_strike_hard.txt`, build context, evaluate Strike Hard, expect EV 8.55. If this passes, the full stack (file → grid → characters → tactics → evaluator) is working end-to-end.

**Test B: Parse error handling.**  
Feed `parse_scenario()` malformed input (missing section, missing enemy stats, out-of-bounds banner position) and verify clear error messages. 3-4 specific cases.

**Test C: Minimal scenario (no banner, no anthem).**  
A scenario with just grid + enemies. Verify `banner_position = None`, `anthem_active = False`, and that Strike Hard reports `ineligible` with a reason.

**Test D: Enemy-only validation.**  
Enemy `m2` appears in grid but no stats → error. Enemy `m3` has stats but no grid token → error.

### 10. Module structure

Propose the file layout:

```
sim/
├── __init__.py
├── grid.py
├── grid_spatial.py
├── party.py          # ← new? moves factories here
└── scenario.py       # ← new

scenarios/
└── checkpoint_1_strike_hard.txt  # ← new

tests/
├── fixtures.py       # ← imports factories from sim/party.py
└── test_scenario.py  # ← new
```

Or keep factories in `tests/fixtures.py` and import from there (backwards dependency). Recommend one and justify.

### 11. Open questions for Pass 2

List any decisions where you want input. Expected:

- File extension (.txt vs .scn)
- Whether to move factories out of tests/fixtures.py
- Multi-word enemy names
- Carried vs planted banner handling
- Whether the grid's `B`/`*` banner token should be ignored or honored by the scenario loader
- How to handle scenarios with non-default party composition (future work)

### 12. Potential discrepancies to flag

Read through the existing code and flag any decisions from Checkpoints 1/2 that might need revisiting for Checkpoint 3. Examples of what to look for:

- Does `CombatantState.position` default to `(0, 0)`? If so, a scenario file that forgets to place a character would silently put them at the origin. Consider: should position be required? Use `None` sentinel?
- Does every party factory accept `anthem_active`? Check `make_aetregan`, `make_dalai`, `make_erisen` signatures.
- Is there any assumption in `GridSpatialQueries` about all combatants being on the grid? If the scenario file doesn't place Erisen, does the code crash or handle it gracefully?

## Output Format

Produce a single markdown document with sections matching the 12 items above. Include:

- Concrete file-format grammar (not just examples)
- Sketched dataclass definitions
- Function signatures with docstrings
- A complete example scenario file
- Explicit test case descriptions with expected outcomes

Aim for skimmable but thorough. Cite AoN URLs for any mechanical claims.

When done, output the plan as a single document and wait for review. No code yet.

## What Comes After

1. You produce this Pass 1 plan.
2. I review, write Pass 2 corrections.
3. You produce Pass 2 refined plan.
4. I review, write Pass 3 implementation brief.
5. You implement code + tests.
6. We confirm all 171+ tests still pass, plus new scenario tests, plus the killer Strike Hard validation from disk.
7. We close Checkpoint 3 and move to Checkpoint 4: Defensive value computation.
