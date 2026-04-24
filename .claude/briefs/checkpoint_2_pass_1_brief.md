# Checkpoint 2 Pass 1: Grid and Spatial Reasoning — Architectural Plan

## Context

Checkpoint 1 is complete (123/123 tests passing). The tactic dispatcher works against a `SpatialQueries` Protocol. Checkpoint 2 builds the real grid implementation that replaces `MockSpatialQueries` in production scenarios.

This is **Pass 1 of the three-pass loop for Checkpoint 2**. Your job is to produce an architectural plan, not code. After I review it, we'll do Pass 2 (refinement) and then Pass 3 (implementation).

## Standing Rules (apply to every brief)

1. **Verify rules against Archives of Nethys (https://2e.aonprd.com/)** before stating them. Use web search + web_fetch. Cite URLs. Mark unverifiable claims as UNVERIFIED.
2. **Cite AoN URLs** in every docstring for non-trivial mechanics.
3. **Read existing code before proposing changes.** Start by reading `pf2e/tactics.py` (especially `SpatialQueries` Protocol and `MockSpatialQueries`), `pf2e/character.py`, `CHANGELOG.md`, and the original prototype files in `/home/claude/pf2e_sim/` if they're still available. If not, ask the user for relevant reference files before proceeding.
4. **Surface discrepancies, don't silently fix them.** If PF2e spatial rules don't match my brief, flag it.
5. **Don't expand scope.** Grid and spatial queries only. No scenario loader, no turn evaluator, no formatter.
6. **Describe test cases, don't write them.** Pass 1 is architectural.

---

## Your Task: Architectural Plan for Checkpoint 2

Design the grid representation and real spatial query implementation. Produce a written plan covering the sections below.

## Scope

### What's in scope for Checkpoint 2

- A new top-level `sim/` package (sibling to `pf2e/`)
- `sim/grid.py` — grid representation, position helpers, distance/adjacency/burst math
- `sim/grid_spatial.py` (or similar) — a `GridSpatialQueries` class implementing the `SpatialQueries` Protocol
- Grid parsing: take an ASCII string → populated `GridState`
- Grid rendering: take a `GridState` → ASCII string (for CLI output)
- Integration test: recreate a simple scenario, use the grid, evaluate a tactic, confirm the result matches expectations

### What's explicitly NOT in scope

- No `sim/scenario.py` — Checkpoint 3
- No defensive value computation — Checkpoint 4
- No turn planning — Checkpoint 5
- No formatter — Checkpoint 6
- No changes to `pf2e/` unless absolutely necessary (e.g., adding a position helper). Flag any proposed change for approval before implementing.

---

## What the Plan Must Cover

### 1. Grid coordinate system and basic math

Decide and justify:

- **Coordinate convention**: `(row, col)` with row increasing downward? Or `(x, y)` with y increasing upward? The prototype used `(row, col)` — stick with that for consistency unless you have a strong reason otherwise.
- **Cell size**: In PF2e, one grid square = 5 feet. This is the canonical scale. (AoN: https://2e.aonprd.com/Rules.aspx?ID=2375 — verify URL)
- **Distance calculation**: PF2e uses **Chebyshev distance** where diagonals count as 1 square for the first step, 2 squares for the second, 1 again for the third, etc. (alternating "5/10/5/10" pattern). The simplified "diagonal = 1 square" works only for short distances. Verify against AoN's movement rules and decide how detailed to be.

Propose a `distance_squares(pos_a, pos_b) -> int` function and a `distance_ft(pos_a, pos_b) -> int` wrapper. Document the exact algorithm you use.

**Verify against AoN**: https://2e.aonprd.com/Rules.aspx — search for "Diagonal" and "Counting Movement." Cite the specific rules page.

### 2. Position and GridState dataclasses

Sketch the core dataclasses:

```python
@dataclass(frozen=True)
class Position:
    row: int
    col: int
    # Methods? Or just a tuple alias?

@dataclass
class GridState:
    # Grid dimensions
    # Character positions
    # Enemy positions
    # Banner position (if planted)
    # Terrain features? (walls, difficult terrain, cover)
```

Decide:

- **Position as a frozen dataclass or a tuple alias?** The tactics module already uses `tuple[int, int]` for positions. Changing to a `Position` class means changing signatures in `pf2e/tactics.py` and `pf2e/character.py` (CombatantState.position). Staying with tuples keeps consistency. Recommend one and justify.
- **Mutable or immutable GridState?** Positions move during combat (Stride, Step, Gather to Me). If immutable, every movement creates a new GridState. If mutable, we need to be careful about state leakage between tactic evaluations.
- **What terrain features matter for Checkpoint 2?** Probably just walls (block movement and line of sight) and empty squares. Difficult terrain, cover, elevation, and hazards are out of scope for now — flag them as future work.

### 3. Grid parsing: ASCII → GridState

The original prototype had `parse_map(grid_str)` that converted a string like:

```
.  .  .  .  .  .  .  .  .  .
.  .  m  .  .  .  .  .  .  .
.  .  g  m  .  c  .  .  .  .
.  .  .  .  .  .  .  .  .  .
...
```

...into positions. Port this to the new codebase. Decide:

- **Legend**: What characters map to what? The prototype used:
  - `.` or ` ` = empty
  - `c` = commander (Aetregan)
  - `g` = guardian (Rook)
  - `b` = bard (Dalai)
  - `i` = inventor (Erisen)
  - `m` = enemy minion
  - `M` = enemy brute
  - `B` = banner
  - Multiple of same letter auto-numbered
- Should the new legend match or change? Matching preserves scenario file compatibility. Changing lets you be more explicit (e.g., uppercase for Commander, distinct token for banner). Recommend one.
- **Terrain tokens**: Add `#` for wall? Leave that for Checkpoint 3? Recommend.
- **Return type**: Does `parse_map` return a `GridState` directly, or does it return an intermediate dict that the scenario loader (Checkpoint 3) composes with character data? For Checkpoint 2, returning enough to build a GridState is sufficient.

Sketch the function signature and a brief description of the algorithm.

### 4. Grid rendering: GridState → ASCII

The inverse operation. The original prototype's `render_map` produced:

```
   0 1 2 3 4 5 6 7 8 9
 0 . . . . . . . . . .
 1 . . M . . . . . . .
 2 . . r M . a . . . .
 3 . . . . . . . . . .
 4 . . . . . B . . . .
 5 . . . . d . . . . .
 6 . . . . . . . . . .
 7 . . . . e . . . . .
 8 . . . . . . . . . .
 9 . . . . . . . . . .
```

Port this. Decide:

- **Include header/row numbers?** Useful for debugging and scenario author feedback.
- **Character representation**: The prototype used first-letter lowercase for allies, first-letter uppercase for enemies. Does this scale to parties with name collisions (e.g., two characters starting with "E")? Probably fine for now — flag as future work.
- **Banner rendering**: `B` in the grid was "banner." But `B` could also mean "Bandit" in scenarios with bandits. Disambiguate?

### 5. Core spatial helpers

The functions the grid needs to support all spatial queries:

- `distance_squares(pos_a, pos_b) -> int` — Chebyshev or PF2e-correct counting
- `distance_ft(pos_a, pos_b) -> int` — wrapper that multiplies by 5 (or does the 5/10/5/10 diagonal counting)
- `is_adjacent(pos_a, pos_b) -> bool` — true if within 5 ft
- `in_burst(center_pos, radius_ft) -> set[Position]` — all squares in a burst
- `in_emanation(center_pos, radius_ft) -> set[Position]` — all squares in an emanation (different from burst? In PF2e they use the same geometry but different source: burst from a point, emanation from a creature)

Verify against AoN:
- Bursts vs. emanations vs. cones: https://2e.aonprd.com/Rules.aspx — search "Areas"
- Reach rules for weapons with the reach trait: https://2e.aonprd.com/Traits.aspx?ID=192

Decide:

- **How to handle weapons with reach**: When asking "enemies reachable by Aetregan" with the whip (reach trait, 10 ft), the query should consider all squares within 10 ft, not just adjacent. The `GridSpatialQueries.enemies_reachable_by()` implementation needs access to each character's weapon reach.
- **What about ranged weapons and thrown distance?** For Checkpoint 2, limit "reachable" to melee reach. Ranged attacks are evaluated separately (and the tactics we care about — Strike Hard, Tactical Takedown — are about melee reach anyway). Flag this as a scope decision.

### 6. GridSpatialQueries implementation

The main deliverable. Class that implements the `SpatialQueries` Protocol using the `GridState` and character data.

```python
class GridSpatialQueries:
    def __init__(self, grid: GridState, ...):
        ...
    
    def is_in_banner_aura(self, combatant_name: str) -> bool: ...
    def enemies_reachable_by(self, combatant_name: str) -> list[str]: ...
    def is_adjacent(self, a_name: str, b_name: str) -> bool: ...
    def can_reach_with_stride(
        self, combatant_name: str, target_name: str, max_distance_ft: int,
    ) -> bool: ...
    def distance_ft(self, a_name: str, b_name: str) -> int: ...
```

Sketch each method's implementation. Specifically:

**`is_in_banner_aura(name)`**: Look up the combatant's position, look up the banner position (planted or carried at commander's position), compute distance. Banner aura is 30 ft (6 squares). Confirm aura size against AoN. Citation: https://2e.aonprd.com/Classes.aspx?ID=66 — Commander's Banner.

**`enemies_reachable_by(name)`**: Find the combatant, look at their equipped melee weapons, find the maximum reach, return all enemies within that reach. Whip = 10 ft, longsword = 5 ft, etc.

**`can_reach_with_stride(name, target_name, max_distance_ft)`**: This is used by Tactical Takedown to check if an ally can half-Speed Stride and end adjacent to an enemy. The actual question is: can the ally traverse `max_distance_ft` of open squares to end up adjacent to the target?

  For Checkpoint 2, simplify: use straight-line distance. If `distance_ft(ally_pos, target_pos) <= max_distance_ft + 5` (they need to end adjacent, so add 5 ft buffer), return True. This doesn't account for walls or pathfinding — flag as a future improvement.

**Open question**: Should `GridSpatialQueries` compute this on-demand each call, or pre-compute a cache? Given there are 5-10 characters per scenario and a handful of tactic evaluations, on-demand is fine. Flag if you think otherwise.

### 7. How `GridSpatialQueries` sources combatant positions

This is the subtle architectural question. The Protocol's methods take `combatant_name: str`, not `CombatantState`. So `GridSpatialQueries` needs a way to look up a position from a name.

Options:

- **A) `GridState` holds positions.** When a character moves, update `GridState`. `CombatantState.position` becomes redundant or a cache.
- **B) `CombatantState.position` is the source of truth.** `GridSpatialQueries` holds references to all combatants and reads their positions.
- **C) Positions duplicated.** Both `GridState` and `CombatantState` hold positions; they're synced whenever the grid is built.

Recommend one and justify. Option B has the cleanest semantics (position is part of combatant state, not grid state), but means `GridSpatialQueries` needs a combatant lookup mechanism. Option A is simpler for grid rendering but complicates "move this combatant" operations. Option C is pragmatic but risks desync bugs.

**Recommendation**: Option B. The `GridSpatialQueries` constructor takes the `TacticContext` (or just its squadmates + enemies lists) and resolves names to positions at query time. This matches how `MockSpatialQueries` works — the mock's `in_aura` dict is keyed by name.

### 8. Legend for grid tokens: match the old prototype?

Propose a legend table. The old prototype used:

- `.` = empty
- `c` = commander (Aetregan)
- `g` = guardian (Rook)
- `b` = bard (Dalai)
- `i` = inventor (Erisen)
- `m` / `M` = enemy minion / brute
- `B` = banner
- Auto-numbered if duplicates (e.g., `m`, `m2`, `m3`)

Decide whether to keep this or improve it. If you propose changes, explain why. The tradeoff: new scheme might be clearer but breaks any existing scenario files.

### 9. Integration test scope

Sketch 2-3 integration tests that prove the pieces work together. At minimum:

**Test A: Parse, render, re-parse roundtrip.**  
A grid string parses into a GridState; rendering it produces the same string (modulo whitespace normalization). Confirms parsing and rendering are inverses.

**Test B: GridSpatialQueries produces correct answers for a known scenario.**  
Build a 10x10 grid with Aetregan at (3,3) with banner planted there, Rook at (3,4) holding a longsword, Bandit1 at (3,5). Verify:
- `is_in_banner_aura("Rook")` returns True (distance 5 ft <= 30 ft)
- `enemies_reachable_by("Rook")` returns `["Bandit1"]` (adjacent with longsword reach 5)
- `is_adjacent("Rook", "Bandit1")` returns True
- `distance_ft("Aetregan", "Bandit1")` returns 10 (two squares via Chebyshev)

**Test C: Swap MockSpatialQueries for GridSpatialQueries in a tactic evaluation.**  
Take the Checkpoint 1 Strike Hard test scenario. Build a real GridState matching the mock's assumptions. Pass `GridSpatialQueries` to `TacticContext`. Call `evaluate_tactic(STRIKE_HARD, context)`. Expect the same result as the mocked version (EV 8.55, best_target_ally="Rook").

This last one is the killer test — it proves the Protocol abstraction works. If it fails, either the Protocol is wrong or `GridSpatialQueries` doesn't correctly implement it.

### 10. Module structure

Propose the file layout:

```
sim/
├── __init__.py
├── grid.py            # Position, GridState, parse_map, render_map, distance_ft
└── grid_spatial.py    # GridSpatialQueries
```

Or combine into one file if you prefer. Justify.

### 11. Open questions for Pass 2

List decisions where you want my input. Examples I'd expect:

- Diagonal distance algorithm (simple Chebyshev vs PF2e 5/10/5/10)?
- Should `Position` replace `tuple[int, int]` throughout the codebase, or stay separate?
- How to handle characters whose reach varies by equipped weapon (Aetregan's whip vs shield bash)?
- Should `GridSpatialQueries` cache computations?
- Legend changes from prototype?

### 12. Potential PF2e rules to research

Flag any rules you're unsure about and need to verify on AoN:

- Counting squares for diagonals
- Burst vs emanation geometry
- Reach rules (weapon reach vs creature reach)
- Banner aura size (30 ft confirmed, but verify)
- How difficult terrain affects movement (out of scope for Checkpoint 2, but worth noting for Checkpoint 3 planning)

Research these before finalizing the plan.

## Output Format

Produce a single markdown document with sections matching the 12 items above. Use code blocks for dataclass sketches and function signatures. Aim for skimmable but thorough.

Cite AoN URLs for every mechanical claim. Mark anything you can't verify as `(UNVERIFIED — please check)`.

When you're done, output the plan as a single document and wait for review. No code yet.

## What Comes After

1. You produce this Pass 1 plan.
2. I review it, flag errors, write a Pass 2 correction brief.
3. You produce a Pass 2 refined plan.
4. I review again, write the Pass 3 implementation brief.
5. You implement the code + tests.
6. We confirm all 123+ tests still pass, and the new integration tests prove the Protocol abstraction holds.
7. We close Checkpoint 2 and move to Checkpoint 3: Scenario loading.
