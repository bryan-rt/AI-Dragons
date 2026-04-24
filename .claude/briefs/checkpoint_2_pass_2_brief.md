# Checkpoint 2 Pass 2: Corrections and Movement Rule Addition

## Context

Your Pass 1 plan is strong. The coordinate system, distance algorithm, GridState/Position decisions, module structure, and integration test scope are approved as-is. This Pass 2 brief covers concrete corrections and one new rule.

**Do NOT rewrite the whole plan.** Apply the corrections below and output a compact updated plan. Unchanged sections can be summarized as "unchanged from Pass 1."

**Standing rules apply.** Verify against AoN, cite URLs, surface discrepancies, don't expand scope, read existing code before changing it.

---

## Corrections to Apply

### C.1 Emanation geometry — quote the exact AoN rule

Your Pass 1 plan claims: "For a Medium creature occupying 1 square, an emanation of radius R ft includes all squares where distance_ft(center, square) <= R. This is because emanations extend from the sides of the creature's space."

This is almost certainly correct, but the Pass 1 plan didn't include the verbatim AoN text. Before Pass 3, fetch https://2e.aonprd.com/Rules.aspx?ID=2387 again and quote the exact wording of the emanation rule (under 15 words per copyright compliance, but enough to confirm the "extends from sides" language). Include the verbatim quote in the docstring of `squares_in_emanation`.

If the rule actually says emanations extend from edges of the creature's square (not center), confirm the "measure from center" simplification is mathematically equivalent for Medium creatures. Show the derivation. If it's NOT equivalent (unlikely but possible), update the algorithm.

This matters because every banner aura check, every AoE spell check, and every emanation-based area depends on this geometry being correct.

### C.2 Movement cannot pass through occupied squares (NEW RULE)

**This is the major change in Pass 2.** The Pass 1 plan used straight-line distance for `can_reach_with_stride`. That's wrong for our simulator.

New rule: **Characters cannot move through any occupied square, and cannot end movement in an occupied square.** This applies to both ally and enemy occupied squares. Walls are also impassable.

This is stricter than PF2e's actual rules (which allow moving through allied squares as difficult terrain, per https://2e.aonprd.com/Rules.aspx?ID=2366 — verify text). We're adopting the stricter rule as a conservative simplification. The simulator biases toward false negatives (reports "can't reach" when RAW might allow it) rather than false positives. Document this deviation explicitly in code comments.

Implementation implications:

**`can_reach_with_stride` must use pathfinding, not straight-line distance.** BFS from the ally's start square, treating all occupied squares (enemies, allies other than self, walls) as impassable. Terminate when any square adjacent to the target is reached with total cost <= max_ft. The "adjacent square" must itself be unoccupied (the ally has to stand there).

**New helper: `shortest_movement_cost(start, target_adjacency, blocked, grid)`** in `sim/grid.py`. Returns the minimum movement cost in feet to reach any square adjacent to `target_adjacency`, or a sentinel (e.g., 999 or None) if unreachable.

**Movement cost model for pathfinding:** For Checkpoint 2, use Chebyshev step cost of 5 ft per step (each grid square costs 5 ft to enter, diagonal or orthogonal). This is a simplification of the 5/10 diagonal rule — it underestimates the cost of long diagonal paths. Flag this as a known approximation with a comment:

```python
# SIMPLIFICATION: pathfinding uses uniform 5-ft step cost per square.
# PF2e's strict 5/10 diagonal rule is used for point-to-point distance
# queries (distance_ft, emanations) but not for pathfinding cost, because
# the 5/10 alternation is a total-path property that complicates BFS.
# For a single Stride (20-35 ft), the underestimate is at most 5 ft.
# Future work: implement Dijkstra with proper 5/10 diagonal accumulation.
```

**Occupied squares set**: `GridSpatialQueries.__init__` builds a `set[Pos]` of all occupied squares (all combatant positions + walls from GridState). This set is passed to `shortest_movement_cost` as the `blocked` parameter. The ally's own starting square is NOT in the blocked set for their own movement (they can leave it).

**Banner is not an obstacle.** A planted banner is an item, not a creature. Its square is passable. Combatants can stand on the banner square (historically, the commander often does — they plant it at their feet). Confirm this interpretation against AoN banner rules: https://2e.aonprd.com/Rules.aspx?ID=3421.

**Add early return for already-adjacent allies:**
```python
def can_reach_with_stride(self, name: str, target: str, max_ft: int) -> bool:
    a_pos = self._positions.get(name)
    b_pos = self._positions.get(target)
    if a_pos is None or b_pos is None:
        return False
    # Already adjacent: zero movement needed
    if chebyshev_squares(a_pos, b_pos) == 1:
        return True
    # Use pathfinding to find minimum movement to reach an adjacent square
    cost = shortest_movement_cost(
        start=a_pos,
        target=b_pos,  # find any unoccupied square adjacent to target
        blocked=self._occupied_squares - {a_pos},  # ally can leave their own square
        grid=self._grid,
    )
    return cost <= max_ft
```

**New test cases required:**
- Ally and target adjacent with empty path → True
- Ally blocked by an enemy between them, but a detour exists within max_ft → True
- Ally blocked by an enemy, no detour within max_ft → False
- Ally blocked by an ally between them, no detour → False (strict rule)
- All adjacent squares to target are occupied → False (can't end anywhere)
- Target in a corner of the grid with one open adjacent square → True if reachable

### C.3 `can_reach_with_stride` documentation requirements

Even with BFS, document the remaining approximations:

1. Uniform 5-ft step cost (underestimates long diagonal moves by up to ~10 ft on a full Stride)
2. Stricter than PF2e: no ally pass-through (biases toward false negatives)
3. No consideration of difficult terrain, hazards, or elevation

### C.4 Move `EnemyState` to `pf2e/character.py`

Resolve the import-direction concern from your Section 11.7 by moving `EnemyState` out of `pf2e/tactics.py` and into `pf2e/character.py` alongside `Character` and `CombatantState`. It's a fundamental combatant type, not specific to the tactics system.

Keep `SpatialQueries` Protocol in `pf2e/tactics.py` — it's only used by the tactics evaluators. No need to move it.

After the move:
- `pf2e/tactics.py` imports `EnemyState` from `pf2e/character.py`
- `sim/grid_spatial.py` imports `EnemyState` from `pf2e/character.py` and `SpatialQueries` from `pf2e/tactics.py`

This will require a small refactor: update the import in `pf2e/tactics.py` and any test that currently does `from pf2e.tactics import EnemyState`. The test file `tests/test_tactics.py` currently has this import — change it to `from pf2e.character import EnemyState` (or re-export from tactics for backward compat — prefer the explicit import).

### C.5 Put `melee_reach_ft` in `pf2e/combat_math.py`

Not `sim/grid.py`. Melee reach is a character-level derivation, analogous to `effective_speed(state)` which already lives in `combat_math.py`. Put it there:

```python
# pf2e/combat_math.py
def melee_reach_ft(character: Character) -> int:
    """Maximum melee reach across all equipped melee weapons.
    
    Standard melee reach for Medium creatures is 5 ft. Weapons with the
    'reach' trait extend this to 10 ft.
    (AoN: https://2e.aonprd.com/Traits.aspx?ID=684 — reach trait)
    """
    max_reach = 5
    for eq in character.equipped_weapons:
        if eq.weapon.is_melee and "reach" in eq.weapon.traits:
            max_reach = max(max_reach, 10)
    return max_reach
```

`sim/grid_spatial.py` then imports it from `pf2e/combat_math.py` (same module it already imports `effective_speed` from).

### C.6 Banner rendering: accept both tokens, emit one

Parser accepts `B` OR `*` for planted banner. Renderer always emits `*`. This handles the `B` vs "Brute/Bandit" collision while keeping backward compatibility with prototype scenario files.

Document in `parse_map` docstring:
```python
# Token 'B' or '*' — planted banner (accepted on input, rendered as '*')
```

The roundtrip integration test (Test A) should then:
1. Parse a grid containing `B` at some position
2. Render the resulting GridState + positions
3. Verify the output has `*` at that position (not `B`)
4. Re-parse the rendered output and confirm positions match

Explicitly document that parse-render is NOT literally identity — it's a semantic roundtrip.

### C.7 Resolve the `distance_ft` name collision

Pick one:

**Option A (preferred)**: Module-level function in `sim/grid.py` is named `distance_ft(pos_a: Pos, pos_b: Pos) -> int`. The method on `GridSpatialQueries` is also named `distance_ft` but takes names. Inside the method, reference the module function via qualified import:

```python
from sim import grid  # at the top of grid_spatial.py
...
class GridSpatialQueries:
    def distance_ft(self, a_name: str, b_name: str) -> int:
        a_pos = self._positions[a_name]
        b_pos = self._positions[b_name]
        return grid.distance_ft(a_pos, b_pos)
```

**Option B**: Rename the module function to `grid_distance_ft` to avoid ambiguity.

Recommend Option A. The qualified import `grid.distance_ft` is clear inside the method body, and the Protocol's `distance_ft(a_name, b_name)` signature is what callers see.

### C.8 Add `Pos` type alias in `sim/grid.py`

```python
Pos = tuple[int, int]  # (row, col) grid coordinate
```

Use `Pos` in all `sim/grid.py` and `sim/grid_spatial.py` function signatures. Do NOT touch `pf2e/` files — the existing `tuple[int, int]` annotations there stay as-is. This keeps the alias localized to the new `sim/` package.

### C.9 Occupied squares helper on GridSpatialQueries

To avoid recomputing the occupied-squares set on every query, build it once in `__init__`:

```python
class GridSpatialQueries:
    def __init__(self, grid, commander, squadmates, enemies, banner_position):
        self._grid = grid
        self._positions = {}  # name -> Pos
        self._combatants = {}  # name -> CombatantState
        self._enemies_by_name = {}  # name -> EnemyState
        self._banner_pos = banner_position
        
        # ... populate dicts ...
        
        # Pre-compute occupied squares (for pathfinding).
        # Banner is an item, not a creature — its square is passable.
        self._occupied_squares: set[Pos] = set(self._positions.values()) | grid.walls
```

If positions change during a simulation run (which they will in Checkpoint 5's turn evaluator), we'll need a way to rebuild this. For Checkpoint 2, assume positions are static within a single `GridSpatialQueries` instance. Flag for future: add an `update_positions()` method or recommend constructing a fresh `GridSpatialQueries` per tactic evaluation.

---

## Confirmed as-is from Pass 1

- Coordinate convention `(row, col)` with row increasing downward
- Cell size = 5 ft
- Strict 5/10/5/10 diagonal rule for `distance_ft` (point-to-point) — the formula is mathematically correct (I verified it manually)
- 10-ft reach special case: Chebyshev ≤ 2 for exactly 10-ft reach
- GridState holds terrain only (walls), positions live on CombatantState/EnemyState
- Tokens: `.` `#` `c` `g` `b` `i` `m` `M` with auto-numbering for `m`/`M`
- Module structure: `sim/grid.py` + `sim/grid_spatial.py`
- Integration tests A (roundtrip), B (GridSpatialQueries correctness), C (Protocol compatibility), D (distance edge cases), E (10-ft reach), F (emanation boundary)
- `GridSpatialQueries.from_context(grid, ctx)` classmethod
- Banner aura = 30-ft emanation per https://2e.aonprd.com/Rules.aspx?ID=3421

## Additional test cases needed

Beyond the Pass 1 tests A-F, add:

**Test G: Movement blocked by enemy.** Ally at (3,3), enemy-obstacle at (3,4), target at (3,5). Ally has 20 ft Stride. Straight line blocked but diagonal path (3,3)→(4,4)→(3,5-adjacent) exists. Verify `can_reach_with_stride` returns True via the detour.

**Test H: Movement blocked with no detour.** Ally at (3,3) in a 1-wide corridor, enemy-obstacle at (3,4), target at (3,5), walls at (2,4) and (4,4). No detour possible. Verify False.

**Test I: Target surrounded — no adjacent open square.** Target at (3,3), allies or enemies at all 8 adjacent squares. No free square to end in. Verify False even with plenty of movement budget.

**Test J: Ally pass-through blocked (strict rule).** Ally A at (3,3), Ally B at (3,4), target at (3,5). Ally A wants to reach target adjacency. Straight path through ally B is blocked under strict rule. Verify Ally A must detour or return False.

---

## Output Format

Produce a compact Pass 2 plan document with:

1. **Corrections applied** — brief confirmation of each C.1–C.9 item
2. **Updated Section 5 (Core Spatial Helpers)** with the new `shortest_movement_cost` pathfinding function and the early-return logic in `can_reach_with_stride`
3. **Updated Section 6 (GridSpatialQueries)** with the occupied-squares set and the pathfinding-based `can_reach_with_stride`
4. **Updated Section 9 (Integration Tests)** including the new G–J tests
5. **Updated Section 10 (Module Structure)** noting the EnemyState move and `melee_reach_ft` location
6. **Quoted emanation rule text** (verbatim from AoN, under 15 words) in the `squares_in_emanation` docstring
7. **Unchanged from Pass 1** — one-line summary of what stayed the same

Aim for 3-4 pages. This is a meaningful update (new pathfinding) but still surgical, not a rewrite.

Cite AoN URLs for every mechanical claim. Any remaining UNVERIFIED items must be flagged as blockers for Pass 3.

When you're done, output the Pass 2 plan as a single document. Wait for review before any code is written.

---

## What Happens Next

1. You produce this Pass 2 plan.
2. I review and confirm (or flag anything I missed).
3. We move to Pass 3 implementation.
4. Code lands with tests passing, and we close Checkpoint 2.
