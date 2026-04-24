# Checkpoint 2 Pass 3: Grid and Spatial Reasoning — Implementation

## Context

The Pass 2 architectural plan is approved with one correction. Time to write code. This brief tells you exactly what to implement, in what order, with what tests.

**Standing rules apply**: verify against AoN, cite URLs in docstrings, read existing code first, surface discrepancies, don't expand scope, test what you build.

## One Correction from Pass 2 Review

**Test J expected cost is wrong in the Pass 2 plan.** The plan says the diagonal detour around Ally B costs 10 ft. It actually costs **5 ft** because Chebyshev diagonals bypass a single blocker in one step (cost = 5 ft per step in our uniform-cost BFS).

Corrected Test J: Ally A at (3,3), Ally B at (3,4), target at (3,5). Both diagonal neighbors of (3,3) that are adjacent to target — (2,4) and (4,4) — are unblocked. Expected BFS cost: **5 ft** (one diagonal step to (2,4) or (4,4)). If `max_ft >= 5` → True.

Reframe the test as: "Verifies that the strict no-pass-through rule is bypassed by diagonal geometry when an open diagonal exists." This is a useful test of the BFS correctness.

## Pre-implementation: Read existing code

Before writing anything, verify the foundation:

- `pf2e/character.py` — **critical: check whether `CombatantState` has a `position: Pos` field.** If it doesn't, add it. The Pass 2 plan assumed it exists (`commander.position` is referenced in `GridSpatialQueries.__init__`). If it's missing, adding it is part of Step 1.
- `pf2e/tactics.py` — confirm the `SpatialQueries` Protocol, `MockSpatialQueries`, and `EnemyState` location. You'll move `EnemyState` out of this file.
- `pf2e/combat_math.py` — see where `effective_speed()` lives so you can add `melee_reach_ft()` in the same style.
- `tests/test_tactics.py` — check the current `EnemyState` import. You'll update it.
- `CHANGELOG.md` — review the Checkpoint 1 entry as a template for the Checkpoint 2 entry.

## Scope

### What to implement

1. **Foundation refactor**: Move `EnemyState` to `pf2e/character.py`, add `melee_reach_ft` to `pf2e/combat_math.py`, add `position` to `CombatantState` if missing.
2. **New module**: `sim/__init__.py` (empty) and `sim/grid.py` with geometry, parsing, rendering, and BFS.
3. **New module**: `sim/grid_spatial.py` with `GridSpatialQueries`.
4. **New test file**: `tests/test_grid.py` for pure geometry tests.
5. **New test file**: `tests/test_grid_spatial.py` for Protocol-level tests including the killer swap test.
6. **CHANGELOG update**: document the Checkpoint 2 additions.

### What NOT to implement

- No scenario loader (`sim/scenario.py`) — Checkpoint 3
- No defensive value computation — Checkpoint 4
- No turn planning — Checkpoint 5
- No formatter — Checkpoint 6
- No proper Dijkstra with 5/10 diagonal accumulation — future work
- No ally pass-through handling — future work (we're using the strict rule)
- No difficult terrain, cover, elevation, or hazards — future work

---

## Implementation Order

Work in this order to minimize churn.

### Step 1: Foundation refactor

#### Step 1a: Verify/add `position` on `CombatantState`

In `pf2e/character.py`, check if `CombatantState` has:
```python
position: tuple[int, int] = (0, 0)  # (row, col) grid coordinate
```

If not, add it. Position defaults to (0, 0) — real positions are set by the scenario layer (Checkpoint 3) or by tests.

#### Step 1b: Move `EnemyState` to `pf2e/character.py`

Cut the `EnemyState` dataclass from `pf2e/tactics.py` and paste it into `pf2e/character.py` alongside `Character` and `CombatantState`. 

In `pf2e/tactics.py`, add a backward-compat re-export at the top of the Data types section:
```python
from pf2e.character import EnemyState  # re-exported for compatibility
```

This way any existing code doing `from pf2e.tactics import EnemyState` keeps working.

Update `tests/test_tactics.py` to import `EnemyState` directly from `pf2e.character`:
```python
from pf2e.character import CombatantState, EnemyState  # was: from pf2e.tactics
```

#### Step 1c: Add `melee_reach_ft` to `pf2e/combat_math.py`

```python
def melee_reach_ft(character: Character) -> int:
    """Maximum melee reach across all equipped melee weapons.
    
    Standard melee reach for Medium creatures is 5 ft. Weapons with
    the reach trait extend this to 10 ft.
    (AoN: https://2e.aonprd.com/Traits.aspx?ID=684 — reach trait)
    """
    max_reach = 5
    for eq in character.equipped_weapons:
        if eq.weapon.is_melee and "reach" in eq.weapon.traits:
            max_reach = max(max_reach, 10)
    return max_reach
```

Place it next to `effective_speed()` — these are analogous character-level derivations.

#### Step 1d: Run the existing tests

Run `pytest tests/ -v`. All 123 existing tests must still pass. The EnemyState move and position/melee_reach_ft additions should not break anything. If they do, stop and surface the failures before continuing.

### Step 2: Create `sim/grid.py`

Create `sim/__init__.py` (empty file, just to make it a package) and `sim/grid.py`.

Top of file:
```python
"""Grid representation, parsing, rendering, and spatial geometry.

Pure geometry and data — no dependency on pf2e/tactics or character types.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field


# Grid coordinates. (row, col) with row increasing downward.
Pos = tuple[int, int]


@dataclass
class GridState:
    """Static terrain for a combat encounter.
    
    Combatant positions live on CombatantState/EnemyState. GridState
    holds only terrain: dimensions and walls.
    """
    rows: int
    cols: int
    walls: set[Pos] = field(default_factory=set)
```

Then implement the geometry functions per Pass 2 Section 2:

```python
def distance_ft(a: Pos, b: Pos) -> int:
    """PF2e grid distance with 5/10 diagonal alternation.
    
    First diagonal step costs 5 ft, second costs 10 ft, alternating.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2357)
    """
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])
    diag = min(dr, dc)
    straight = abs(dr - dc)
    diag_cost = (diag // 2) * 10 + ((diag + 1) // 2) * 5
    return diag_cost + straight * 5


def chebyshev_squares(a: Pos, b: Pos) -> int:
    """Chebyshev (chessboard) distance in grid squares."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def is_adjacent(a: Pos, b: Pos) -> bool:
    """True if Chebyshev distance is exactly 1 square (5 ft)."""
    return chebyshev_squares(a, b) == 1


def is_within_reach(attacker: Pos, target: Pos, reach_ft: int) -> bool:
    """True if target is within weapon reach.
    
    Special case: 10-ft reach extends to 2 squares diagonally, which
    would otherwise be 15 ft by strict 5/10 counting.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2379)
    """
    if reach_ft == 10:
        return chebyshev_squares(attacker, target) <= 2
    return distance_ft(attacker, target) <= reach_ft


def squares_in_emanation(
    center: Pos, radius_ft: int, grid: GridState,
) -> set[Pos]:
    """All in-bounds squares within an emanation of given radius.
    
    For Medium creatures (1 square), measuring from center is
    equivalent to measuring from the edges (RAW).
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2387)
    """
    # Search a bounding box just large enough to cover radius_ft
    max_squares = radius_ft // 5 + 1
    result: set[Pos] = set()
    for dr in range(-max_squares, max_squares + 1):
        for dc in range(-max_squares, max_squares + 1):
            pos = (center[0] + dr, center[1] + dc)
            if not (0 <= pos[0] < grid.rows and 0 <= pos[1] < grid.cols):
                continue
            if distance_ft(center, pos) <= radius_ft:
                result.add(pos)
    return result
```

Then the pathfinding function per Pass 2 Section 5:

```python
def shortest_movement_cost(
    start: Pos, target: Pos, blocked: set[Pos], grid: GridState,
) -> int:
    """Minimum movement cost (ft) to reach a square adjacent to target.
    
    Uses BFS with uniform 5-ft step cost. Returns 999 if unreachable
    or no unoccupied adjacent square exists.
    
    Simplifications:
    - Uniform 5-ft step cost (not PF2e's 5/10 diagonal alternation)
    - No pass-through of any occupied square (stricter than RAW)
    - No difficult terrain
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2360 — moving through creatures)
    """
    # Build the goal set: unoccupied in-bounds squares adjacent to target
    goals: set[Pos] = set()
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            pos = (target[0] + dr, target[1] + dc)
            if not (0 <= pos[0] < grid.rows and 0 <= pos[1] < grid.cols):
                continue
            if pos in blocked:
                continue
            goals.add(pos)
    
    if not goals:
        return 999
    if start in goals:
        return 0
    
    # BFS
    visited: set[Pos] = {start}
    queue: deque[tuple[Pos, int]] = deque([(start, 0)])
    while queue:
        pos, cost = queue.popleft()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                npos = (pos[0] + dr, pos[1] + dc)
                if npos in visited:
                    continue
                if not (0 <= npos[0] < grid.rows and 0 <= npos[1] < grid.cols):
                    continue
                if npos in blocked:
                    continue
                new_cost = cost + 5
                if npos in goals:
                    return new_cost
                visited.add(npos)
                queue.append((npos, new_cost))
    
    return 999
```

Then the parsing and rendering functions per Pass 2 Section 3 and 4. Document the token legend in the `parse_map` docstring. Handle auto-numbering for `m` and `M`. Accept both `B` and `*` for banner; renderer emits `*`.

```python
def parse_map(grid_str: str) -> tuple[GridState, dict[str, Pos], Pos | None]:
    """Parse an ASCII grid string into GridState + positions + banner_position.
    
    Tokens:
      . or (space)  empty square
      #             wall
      c             commander (Aetregan)
      g             guardian (Rook)
      b             bard (Dalai)
      i             inventor (Erisen)
      m             enemy minion (auto-numbered: m1, m2, ...)
      M             enemy brute (auto-numbered: M1, M2, ...)
      B or *        planted banner (parser accepts both; renderer emits *)
    
    Returns (GridState, positions_dict, banner_position_or_None).
    """
```

The return format: a 3-tuple of (GridState, positions dict, banner position). This is more explicit than bundling banner into positions and simpler than returning a composite object.

```python
def render_map(
    grid: GridState,
    positions: dict[str, Pos],
    banner_position: Pos | None = None,
) -> str:
    """Render the grid as a string with column/row headers.
    
    Allies: lowercase first letter of name.
    Enemies (names starting with M or m and followed by digits): that letter.
    Banner: *
    Walls: #
    Empty: .
    """
```

### Step 3: Create `sim/grid_spatial.py`

```python
"""Real SpatialQueries backed by a GridState and combatant positions.

Implements the SpatialQueries Protocol from pf2e/tactics.py.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from pf2e.character import CombatantState, EnemyState
from pf2e.combat_math import melee_reach_ft
from sim import grid
from sim.grid import GridState, Pos, is_within_reach, shortest_movement_cost

if TYPE_CHECKING:
    from pf2e.tactics import TacticContext


class GridSpatialQueries:
    """SpatialQueries implementation backed by a real grid.
    
    Positions are resolved from CombatantState/EnemyState objects at
    construction. The occupied-squares set is precomputed for pathfinding.
    """
    
    def __init__(
        self,
        grid_state: GridState,
        commander: CombatantState,
        squadmates: list[CombatantState],
        enemies: list[EnemyState],
        banner_position: Pos | None,
    ) -> None:
        self._grid = grid_state
        self._banner_pos = banner_position
        self._positions: dict[str, Pos] = {}
        self._combatants: dict[str, CombatantState] = {}
        self._enemies_by_name: dict[str, EnemyState] = {}
        
        self._positions[commander.character.name] = commander.position
        self._combatants[commander.character.name] = commander
        for sq in squadmates:
            self._positions[sq.character.name] = sq.position
            self._combatants[sq.character.name] = sq
        for e in enemies:
            self._positions[e.name] = e.position
            self._enemies_by_name[e.name] = e
        
        # Occupied squares: all combatant positions + walls.
        # Banner is an item (not a creature); its square is passable.
        self._occupied_squares: set[Pos] = (
            set(self._positions.values()) | self._grid.walls
        )
    
    @classmethod
    def from_context(
        cls, grid_state: GridState, ctx: TacticContext,
    ) -> GridSpatialQueries:
        return cls(
            grid_state, ctx.commander, ctx.squadmates, ctx.enemies,
            ctx.banner_position,
        )
    
    def is_in_banner_aura(self, name: str) -> bool:
        """30-ft emanation from the planted banner.
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=3421)
        """
        if self._banner_pos is None:
            return False
        pos = self._positions.get(name)
        if pos is None:
            return False
        return grid.distance_ft(pos, self._banner_pos) <= 30
    
    def enemies_reachable_by(self, name: str) -> list[str]:
        combatant = self._combatants.get(name)
        if combatant is None:
            return []
        pos = combatant.position
        reach = melee_reach_ft(combatant.character)
        return [
            en for en, es in self._enemies_by_name.items()
            if is_within_reach(pos, es.position, reach)
        ]
    
    def is_adjacent(self, a_name: str, b_name: str) -> bool:
        a = self._positions.get(a_name)
        b = self._positions.get(b_name)
        if a is None or b is None:
            return False
        return grid.is_adjacent(a, b)
    
    def can_reach_with_stride(
        self, name: str, target: str, max_ft: int,
    ) -> bool:
        """BFS pathfinding to a square adjacent to target.
        
        Simplifications: uniform 5-ft step cost, no pass-through of
        occupied squares, no difficult terrain.
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2360)
        """
        a_pos = self._positions.get(name)
        b_pos = self._positions.get(target)
        if a_pos is None or b_pos is None:
            return False
        if grid.is_adjacent(a_pos, b_pos):
            return True
        blocked = self._occupied_squares - {a_pos}
        cost = shortest_movement_cost(a_pos, b_pos, blocked, self._grid)
        return cost <= max_ft
    
    def distance_ft(self, a_name: str, b_name: str) -> int:
        a = self._positions.get(a_name)
        b = self._positions.get(b_name)
        if a is None or b is None:
            return 999
        return grid.distance_ft(a, b)
```

### Step 4: Create `tests/test_grid.py`

Pure geometry tests — no CombatantState needed.

```python
"""Tests for sim/grid.py — geometry, parsing, rendering, pathfinding."""

from sim.grid import (
    GridState, Pos, chebyshev_squares, distance_ft, is_adjacent,
    is_within_reach, parse_map, render_map, shortest_movement_cost,
    squares_in_emanation,
)


class TestDistanceFt:
    """Test D: Distance edge cases for 5/10 diagonal rule."""
    
    def test_same_square(self):
        assert distance_ft((3, 3), (3, 3)) == 0
    
    def test_orthogonal_one(self):
        assert distance_ft((3, 3), (3, 4)) == 5
    
    def test_diagonal_one(self):
        assert distance_ft((3, 3), (4, 4)) == 5
    
    def test_diagonal_two(self):
        assert distance_ft((3, 3), (5, 5)) == 15  # 5 + 10
    
    def test_diagonal_three(self):
        assert distance_ft((3, 3), (6, 6)) == 20  # 5 + 10 + 5
    
    def test_diagonal_four(self):
        assert distance_ft((3, 3), (7, 7)) == 30  # 5 + 10 + 5 + 10
    
    def test_mixed(self):
        # 2 rows, 1 col: 1 diag + 1 straight = 5 + 5 = 10 ft
        assert distance_ft((3, 3), (5, 4)) == 10


class TestReach:
    """Test E: 10-ft reach special case vs. standard distance."""
    
    def test_longsword_adjacent_diagonal(self):
        # 5-ft reach, 1 diag square → True
        assert is_within_reach((3, 3), (4, 4), 5) is True
    
    def test_longsword_2_diagonal(self):
        # 5-ft reach, 2 diag squares (15 ft strict) → False
        assert is_within_reach((3, 3), (5, 5), 5) is False
    
    def test_whip_2_diagonal(self):
        # 10-ft reach, 2 diag squares → True (special Chebyshev rule)
        assert is_within_reach((3, 3), (5, 5), 10) is True
    
    def test_whip_3_diagonal(self):
        # 10-ft reach, 3 diag squares → False (Chebyshev 3 > 2)
        assert is_within_reach((3, 3), (6, 6), 10) is False
    
    def test_whip_2_orthogonal(self):
        # 10-ft reach, 2 orth squares → True
        assert is_within_reach((3, 3), (3, 5), 10) is True


class TestEmanation:
    """Test F: Emanation boundary for 30-ft banner aura."""
    
    def test_banner_30ft_orthogonal_in(self):
        grid = GridState(rows=20, cols=20, walls=set())
        aura = squares_in_emanation((10, 10), 30, grid)
        # 6 orthogonal squares = 30 ft, in aura
        assert (10, 16) in aura
    
    def test_banner_30ft_orthogonal_boundary_out(self):
        grid = GridState(rows=20, cols=20, walls=set())
        aura = squares_in_emanation((10, 10), 30, grid)
        # 7 orthogonal squares = 35 ft, out of aura
        assert (10, 17) not in aura
    
    def test_banner_30ft_diagonal_in(self):
        grid = GridState(rows=20, cols=20, walls=set())
        aura = squares_in_emanation((10, 10), 30, grid)
        # 4 diagonal squares = 5+10+5+10 = 30 ft, in aura
        assert (14, 14) in aura
    
    def test_banner_30ft_diagonal_out(self):
        grid = GridState(rows=20, cols=20, walls=set())
        aura = squares_in_emanation((10, 10), 30, grid)
        # 5 diagonal squares = 35 ft, out of aura
        assert (15, 15) not in aura


class TestParseRender:
    """Test A: Parse/render semantic roundtrip."""
    
    def test_roundtrip_with_banner(self):
        grid_str = (
            ". . . . .\n"
            ". . m . .\n"
            ". g . m .\n"
            ". . c . .\n"
            ". . B . .\n"
        )
        grid, positions, banner_pos = parse_map(grid_str)
        rendered = render_map(grid, positions, banner_pos)
        # Banner was B on input, should be * on output
        assert "*" in rendered
        assert "B" not in rendered
        # Re-parse the rendered string
        grid2, positions2, banner_pos2 = parse_map(rendered)
        # Positions should match
        assert positions == positions2
        assert banner_pos == banner_pos2


class TestPathfindingCorridor:
    """Test H: Movement blocked with no detour."""
    
    def test_corridor_blocked(self):
        # Rows 0 and 2 are walls; only row 1 is open.
        # Start at (1,1), enemy at (1,2), target at (1,3). No detour.
        walls = {
            (0, 0), (0, 1), (0, 2), (0, 3), (0, 4),
            (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),
        }
        grid = GridState(rows=3, cols=5, walls=walls)
        blocked = walls | {(1, 2)}  # wall set + enemy position
        cost = shortest_movement_cost((1, 1), (1, 3), blocked, grid)
        assert cost == 999  # unreachable
```

### Step 5: Create `tests/test_grid_spatial.py`

Protocol-level tests using full CombatantStates.

```python
"""Tests for GridSpatialQueries — the Protocol implementation.

Includes the killer swap test: rerun the Checkpoint 1 Strike Hard
scenario with a real grid and confirm identical EV.
"""

import pytest

from pf2e.character import CombatantState, EnemyState
from pf2e.tactics import (
    STRIKE_HARD, EnemyState as _EnemyStateRexport,  # ensure re-export works
    MockSpatialQueries, TacticContext, evaluate_tactic,
)
from pf2e.types import SaveType
from sim.grid import GridState
from sim.grid_spatial import GridSpatialQueries
from tests.fixtures import (
    make_aetregan, make_dalai, make_erisen, make_rook,
    make_rook_combat_state,
)

EV_TOLERANCE = 0.01


def _make_bandit(name: str, pos: tuple[int, int]) -> EnemyState:
    return EnemyState(
        name=name,
        ac=15,
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        position=pos,
    )


class TestGridSpatialCorrectness:
    """Test B: Basic spatial query correctness against a known grid."""
    
    def test_known_scenario(self):
        grid = GridState(rows=10, cols=10, walls=set())
        aetregan = CombatantState.from_character(
            make_aetregan(), anthem_active=True,
        )
        aetregan.position = (5, 5)
        rook = make_rook_combat_state(anthem_active=True)
        rook.position = (5, 6)
        bandit = _make_bandit("Bandit1", (5, 7))
        
        spatial = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[rook],
            enemies=[bandit],
            banner_position=(5, 5),
        )
        
        # Rook is 5 ft from banner → in aura
        assert spatial.is_in_banner_aura("Rook") is True
        # Bandit is adjacent to Rook, longsword reach 5 ft → reachable
        assert spatial.enemies_reachable_by("Rook") == ["Bandit1"]
        # Chebyshev 1 square → adjacent
        assert spatial.is_adjacent("Rook", "Bandit1") is True
        # 2 orthogonal squares from Aetregan to Bandit
        assert spatial.distance_ft("Aetregan", "Bandit1") == 10


class TestSwapMockForGrid:
    """Test C: The killer test — same Strike Hard scenario, same EV."""
    
    def test_strike_hard_ev_matches_mock(self):
        """Build a real grid matching the Checkpoint 1 mock's assumptions.
        
        Expect identical result: eligible=True, best=Rook, EV 8.55.
        """
        grid = GridState(rows=10, cols=10, walls=set())
        aetregan = CombatantState.from_character(
            make_aetregan(), anthem_active=True,
        )
        aetregan.position = (5, 5)
        rook = make_rook_combat_state(anthem_active=True)
        rook.position = (5, 6)
        dalai = CombatantState.from_character(
            make_dalai(), anthem_active=True,
        )
        dalai.position = (6, 5)
        erisen = CombatantState.from_character(
            make_erisen(), anthem_active=True,
        )
        erisen.position = (2, 2)  # far from aura
        bandit = _make_bandit("Bandit1", (5, 7))
        
        ctx = TacticContext(
            commander=aetregan,
            squadmates=[rook, dalai, erisen],
            enemies=[bandit],
            banner_position=(5, 5),
            banner_planted=True,
            spatial=MockSpatialQueries(),  # will be replaced
            anthem_active=True,
        )
        ctx.spatial = GridSpatialQueries.from_context(grid, ctx)
        
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.eligible
        assert result.best_target_ally == "Rook"
        assert result.best_target_enemy == "Bandit1"
        assert result.expected_damage_dealt == pytest.approx(
            8.55, abs=EV_TOLERANCE,
        )


class TestPathfindingDetour:
    """Test G: Ally can detour around a blocking enemy."""
    
    def test_detour_around_blocker(self):
        grid = GridState(rows=5, cols=5, walls=set())
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)  # off to the side
        ally = make_rook_combat_state()
        ally.position = (2, 1)
        blocker = _make_bandit("Blocker", (2, 2))
        target = _make_bandit("Target", (2, 4))
        
        spatial = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[ally],
            enemies=[blocker, target],
            banner_position=None,
        )
        # Rook half-speed = 10 ft. Detour: (2,1)->(3,2)->(2,3) = 10 ft,
        # and (2,3) is adjacent to target. Reachable.
        assert spatial.can_reach_with_stride("Rook", "Target", 10) is True


class TestPathfindingSurrounded:
    """Test I: Target with all adjacent squares occupied."""
    
    def test_no_open_adjacent(self):
        grid = GridState(rows=5, cols=5, walls=set())
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        ally = make_rook_combat_state()
        ally.position = (0, 1)
        # Target at (2,2), all 8 adjacents occupied
        target = _make_bandit("Target", (2, 2))
        surrounders = [
            _make_bandit(f"S{i}", pos) for i, pos in enumerate([
                (1, 1), (1, 2), (1, 3),
                (2, 1),         (2, 3),
                (3, 1), (3, 2), (3, 3),
            ])
        ]
        spatial = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[ally],
            enemies=[target] + surrounders,
            banner_position=None,
        )
        # Even with huge budget, no unoccupied adjacent square exists
        assert spatial.can_reach_with_stride("Rook", "Target", 999) is False


class TestDiagonalBypass:
    """Test J (corrected): Strict rule bypassed by diagonal geometry.
    
    Ally A at (3,3), Ally B blocking at (3,4), target at (3,5).
    Diagonal neighbor (2,4) or (4,4) is adjacent to target and reachable
    in one diagonal step = 5 ft.
    """
    
    def test_diagonal_bypass_five_feet(self):
        grid = GridState(rows=6, cols=6, walls=set())
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        ally_a = make_rook_combat_state()
        ally_a.position = (3, 3)
        # Ally B is another squadmate (blocking per strict rule)
        ally_b = CombatantState.from_character(make_dalai())
        ally_b.position = (3, 4)
        target = _make_bandit("Target", (3, 5))
        
        spatial = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[ally_a, ally_b],
            enemies=[target],
            banner_position=None,
        )
        # Diagonal detour: (3,3) -> (2,4) or (4,4) = 5 ft, and adjacent to target
        assert spatial.can_reach_with_stride("Rook", "Target", 5) is True
        # With less than 5 ft budget, cannot reach
        assert spatial.can_reach_with_stride("Rook", "Target", 4) is False
```

### Step 6: Update CHANGELOG.md

Append a new section:

```markdown
## [2.0] - Checkpoint 2: Grid and Spatial Reasoning

### Foundation refactor
- `EnemyState` moved from `pf2e/tactics.py` to `pf2e/character.py`.
  Re-exported from tactics for backward compatibility.
- `position: tuple[int, int]` added to `CombatantState`.
- `melee_reach_ft(character)` added to `pf2e/combat_math.py`.
  Returns 10 ft if any equipped melee weapon has the reach trait, else 5 ft.
  (AoN: https://2e.aonprd.com/Traits.aspx?ID=684)

### New package: `sim/`
- `sim/grid.py` — Pos alias, GridState dataclass, ASCII parse/render,
  geometry helpers (distance_ft with 5/10 diagonal, chebyshev_squares,
  is_adjacent, is_within_reach with 10-ft exception, squares_in_emanation),
  and BFS pathfinding (shortest_movement_cost).
- `sim/grid_spatial.py` — GridSpatialQueries implementing the
  SpatialQueries Protocol. Precomputes occupied-squares set at
  construction. Banner square is passable (item, not creature).

### Verified PF2e rules
- Grid cell = 5 ft (https://2e.aonprd.com/Rules.aspx?ID=2356)
- Diagonal movement 5/10/5/10 (https://2e.aonprd.com/Rules.aspx?ID=2357)
- Area measurement follows movement rules (https://2e.aonprd.com/Rules.aspx?ID=2384)
- 10-ft reach diagonal exception (https://2e.aonprd.com/Rules.aspx?ID=2379)
- Emanation geometry (https://2e.aonprd.com/Rules.aspx?ID=2387)
- Moving through creature spaces (https://2e.aonprd.com/Rules.aspx?ID=2360)
- Banner 30-ft emanation (https://2e.aonprd.com/Rules.aspx?ID=3421)

### Design decisions
- Pos is a tuple[int, int] type alias, local to sim/. Not propagated
  to pf2e/ to avoid churn.
- BFS uses uniform 5-ft step cost (not strict 5/10 alternation).
  Underestimates long diagonal paths by up to ~15%. Strict 5/10 is
  preserved for point-to-point queries (distance_ft, emanations, aura).
- Movement cannot pass through ANY occupied square (enemies or allies).
  Stricter than PF2e RAW (which allows willing-ally pass-through).
  Chosen to bias toward false negatives in tactical advice.
- GridState holds terrain only. Combatant positions live on
  CombatantState/EnemyState. GridSpatialQueries resolves names to
  positions at construction time.
```

---

## Validation Checklist

- [ ] All 123 existing tests still pass after Step 1 (foundation refactor)
- [ ] `sim/grid.py` geometry tests pass (TestDistanceFt, TestReach, TestEmanation: ~14 tests)
- [ ] `sim/grid.py` parsing test passes (TestParseRender: 1 test)
- [ ] `sim/grid.py` pathfinding corridor test passes (TestPathfindingCorridor: 1 test)
- [ ] `sim/grid_spatial.py` correctness test passes (TestGridSpatialCorrectness: 1 test)
- [ ] **Killer test passes**: TestSwapMockForGrid returns EV 8.55 (the Protocol abstraction held up)
- [ ] Pathfinding detour test passes (TestPathfindingDetour: 1 test)
- [ ] Surrounded test passes (TestPathfindingSurrounded: 1 test)
- [ ] Diagonal bypass test passes (TestDiagonalBypass: 2 assertions)
- [ ] Target: ~145-155 tests total passing
- [ ] CHANGELOG updated with Checkpoint 2 entry
- [ ] All new docstrings cite AoN URLs
- [ ] No files created outside `sim/grid.py`, `sim/grid_spatial.py`, `sim/__init__.py`, `tests/test_grid.py`, `tests/test_grid_spatial.py` (plus the foundation edits and CHANGELOG)

## Common Pitfalls

**CombatantState.position may not exist yet.** The Pass 2 plan assumed it does. Check `pf2e/character.py` first. If missing, add `position: tuple[int, int] = (0, 0)` as part of Step 1a.

**`CombatantState.from_character()` may not set position.** The test helpers build states then set `.position` as a separate step. That's fine — CombatantState is mutable.

**The roundtrip test cannot use literal string equality.** Banner renders as `*` even though input had `B`. Compare parsed positions instead.

**Import cycle risk.** `sim/grid_spatial.py` uses `TYPE_CHECKING` to import `TacticContext` without creating a runtime cycle. `SpatialQueries` is only used structurally (duck-typed Protocol) so it doesn't need to be imported at runtime for the class to satisfy it. Run `pytest` to catch any cycle.

**`make_rook_combat_state()` returns a CombatantState with current_speed=20 already applied.** Don't set it again. Just set `.position`.

**The Strike Hard killer test uses real CombatantStates, not a mock.** Positions must be set on each state BEFORE constructing GridSpatialQueries (which reads them in __init__). If you construct the spatial queries first and then move a character, the internal positions dict is stale.

**Anthem active in the killer test.** Same as Checkpoint 1 — anthem_active=True on all CombatantStates, and TacticContext.anthem_active=True. EV must be 8.55, not 6.80.

## What Comes After

1. You implement everything above.
2. You run `pytest tests/ -v` and confirm 100% pass.
3. You push the repo.
4. I review.
5. We move to Checkpoint 3: Scenario loading (`sim/scenario.py`) — bringing together grid, characters, tactics, and encounter metadata into a single loadable bundle.
