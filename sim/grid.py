"""Grid representation, parsing, rendering, and spatial geometry.

Pure geometry and data — no dependency on pf2e/tactics or character types.
All distances use PF2e's 5/10 diagonal alternation rule for point-to-point
queries. BFS pathfinding uses a simplified uniform 5-ft step cost.

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2356 — grid squares)
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2357 — diagonal movement)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

# Grid coordinates: (row, col) with row increasing downward.
Pos = tuple[int, int]


# ---------------------------------------------------------------------------
# GridState
# ---------------------------------------------------------------------------

@dataclass
class GridState:
    """Static terrain for a combat encounter.

    Combatant positions live on CombatantState/EnemyState. GridState
    holds only terrain: dimensions and walls.
    """
    rows: int
    cols: int
    walls: set[Pos] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def distance_ft(a: Pos, b: Pos) -> int:
    """PF2e grid distance with 5/10 diagonal alternation.

    First diagonal step costs 5 ft, second costs 10 ft, alternating.
    Orthogonal steps always cost 5 ft.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2357)
    """
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])
    diag = min(dr, dc)
    straight = abs(dr - dc)
    # Odd diagonals (1st, 3rd, ...) cost 5; even (2nd, 4th, ...) cost 10.
    diag_cost = (diag // 2) * 10 + ((diag + 1) // 2) * 5
    return diag_cost + straight * 5


def chebyshev_squares(a: Pos, b: Pos) -> int:
    """Chebyshev (chessboard) distance in grid squares."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def is_adjacent(a: Pos, b: Pos) -> bool:
    """True if Chebyshev distance is exactly 1 square (5 ft).

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2356)
    """
    return a != b and chebyshev_squares(a, b) == 1


def is_within_reach(attacker: Pos, target: Pos, reach_ft: int) -> bool:
    """True if target is within weapon reach.

    Special case: 10-ft reach can reach 2 squares diagonally, which
    would otherwise be 15 ft by strict 5/10 counting.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2379)
    """
    if reach_ft == 10:
        return 0 < chebyshev_squares(attacker, target) <= 2
    return 0 < distance_ft(attacker, target) <= reach_ft


def squares_in_emanation(
    center: Pos, radius_ft: int, grid: GridState,
) -> set[Pos]:
    """All in-bounds squares within an emanation of given radius.

    "An emanation issues forth from each side of your space."
    For Medium creatures (1 square), measuring from the center square
    is equivalent to measuring from the edges of that square, because
    the grid distance is counted in whole-square increments.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2387)
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2384 — area measurement)
    """
    max_sq = radius_ft // 5 + 1
    result: set[Pos] = set()
    for dr in range(-max_sq, max_sq + 1):
        for dc in range(-max_sq, max_sq + 1):
            pos = (center[0] + dr, center[1] + dc)
            if 0 <= pos[0] < grid.rows and 0 <= pos[1] < grid.cols:
                if distance_ft(center, pos) <= radius_ft:
                    result.add(pos)
    return result


# ---------------------------------------------------------------------------
# BFS pathfinding
# ---------------------------------------------------------------------------

def shortest_movement_cost(
    start: Pos, target: Pos, blocked: set[Pos], grid: GridState,
) -> int:
    """Minimum movement cost (ft) to reach any unoccupied square adjacent to target.

    Uses BFS with uniform 5-ft step cost. Returns 999 if unreachable
    or no unoccupied adjacent square exists.

    SIMPLIFICATION: Uses uniform 5-ft cost per step instead of PF2e's
    5/10 diagonal alternation. This underestimates diagonal path cost
    by at most ~15% over a full Stride. Acceptable for Checkpoint 2;
    Dijkstra with proper alternation is future work.

    SIMPLIFICATION: Cannot pass through ANY occupied square (ally or
    enemy). PF2e RAW allows passing through willing creatures' squares
    but not ending there. Our strict rule biases toward false negatives.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2360)
    """
    # Build goal set: unoccupied in-bounds squares adjacent to target
    goals: set[Pos] = set()
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            pos = (target[0] + dr, target[1] + dc)
            if (0 <= pos[0] < grid.rows and 0 <= pos[1] < grid.cols
                    and pos not in blocked):
                goals.add(pos)

    if not goals:
        return 999
    if start in goals:
        return 0

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


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Token legend for parse_map / render_map:
# .         empty square
# #         wall
# c         commander (Aetregan)
# g         guardian (Rook)
# b         bard (Dalai)
# i         inventor (Erisen)
# m         enemy minion (auto-numbered: m1, m2, ...)
# M         enemy brute (auto-numbered: M1, M2, ...)
# B or *    planted banner (parser accepts both; renderer emits *)

_ALLY_TOKENS = {"c", "g", "b", "i"}
_ENEMY_TOKENS = {"m", "M"}
_BANNER_TOKENS = {"B", "*"}


def parse_map(
    grid_str: str,
) -> tuple[GridState, dict[str, Pos], Pos | None]:
    """Parse an ASCII grid string into GridState + positions + banner pos.

    Tokens are single characters separated by whitespace. Lines may have
    leading row-number labels (digits) which are stripped. A leading
    column-header line (all digits/spaces) is also stripped.

    Returns:
        (GridState, positions_dict, banner_position_or_None)
        positions_dict maps token labels to (row, col).
        Auto-numbered tokens: m -> m1, m2, ...; M -> M1, M2, ...
    """
    lines = [line.strip() for line in grid_str.strip().splitlines() if line.strip()]

    # Strip header line if present (all tokens are digits or spaces)
    if lines and all(ch.isdigit() or ch.isspace() for ch in lines[0]):
        lines = lines[1:]

    walls: set[Pos] = set()
    positions: dict[str, Pos] = {}
    banner_pos: Pos | None = None
    counters: dict[str, int] = {}

    for row_idx, line in enumerate(lines):
        tokens = line.split()
        # Strip leading row number if present
        col_start = 0
        if tokens and tokens[0].isdigit():
            col_start = 1

        for col_offset, token in enumerate(tokens[col_start:]):
            col_idx = col_offset
            pos: Pos = (row_idx, col_idx)

            if token in (".", ""):
                continue
            elif token == "#":
                walls.add(pos)
            elif token in _BANNER_TOKENS:
                banner_pos = pos
            elif token in _ALLY_TOKENS:
                positions[token] = pos
            elif token in _ENEMY_TOKENS:
                counters.setdefault(token, 0)
                counters[token] += 1
                label = f"{token}{counters[token]}"
                positions[label] = pos
            elif token == "*":
                banner_pos = pos
            else:
                # Unknown token — treat as named position
                positions[token] = pos

    num_rows = len(lines)
    num_cols = max(
        (len(line.split()) - (1 if line.split()[0].isdigit() else 0)
         for line in lines),
        default=0,
    )

    return GridState(rows=num_rows, cols=num_cols, walls=walls), positions, banner_pos


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_map(
    grid: GridState,
    positions: dict[str, Pos],
    banner_position: Pos | None = None,
) -> str:
    """Render the grid as a string with column/row headers.

    Allies: the token character (c, g, b, i).
    Enemies (e.g., m1, M1): the base letter (m, M).
    Banner: *
    Walls: #
    Empty: .
    """
    # Build reverse lookup: pos -> display token
    pos_to_token: dict[Pos, str] = {}
    for label, pos in positions.items():
        if label in _ALLY_TOKENS:
            pos_to_token[pos] = label
        else:
            # Enemy tokens like m1, M1 — display the base letter
            pos_to_token[pos] = label[0]

    if banner_position is not None:
        pos_to_token[banner_position] = "*"

    # Column header
    col_header = "   " + "  ".join(str(c) for c in range(grid.cols))
    lines = [col_header]

    for r in range(grid.rows):
        row_tokens: list[str] = []
        for c in range(grid.cols):
            pos = (r, c)
            if pos in grid.walls:
                row_tokens.append("#")
            elif pos in pos_to_token:
                row_tokens.append(pos_to_token[pos])
            else:
                row_tokens.append(".")
        lines.append(f"{r:2d} " + "  ".join(row_tokens))

    return "\n".join(lines)
