"""Tests for sim/grid.py — geometry, parsing, rendering, pathfinding."""

import pytest

from sim.grid import (
    GridState,
    chebyshev_squares,
    distance_ft,
    is_adjacent,
    is_within_reach,
    parse_map,
    render_map,
    shortest_movement_cost,
    squares_in_emanation,
)


# ---------------------------------------------------------------------------
# Test D: Distance edge cases (5/10 diagonal rule)
# ---------------------------------------------------------------------------

class TestDistanceFt:
    """(AoN: https://2e.aonprd.com/Rules.aspx?ID=2357)"""

    def test_same_square(self) -> None:
        assert distance_ft((3, 3), (3, 3)) == 0

    def test_orthogonal_one(self) -> None:
        assert distance_ft((3, 3), (3, 4)) == 5

    def test_orthogonal_two(self) -> None:
        assert distance_ft((3, 3), (3, 5)) == 10

    def test_diagonal_one(self) -> None:
        """First diagonal = 5 ft."""
        assert distance_ft((3, 3), (4, 4)) == 5

    def test_diagonal_two(self) -> None:
        """5 + 10 = 15 ft."""
        assert distance_ft((3, 3), (5, 5)) == 15

    def test_diagonal_three(self) -> None:
        """5 + 10 + 5 = 20 ft."""
        assert distance_ft((3, 3), (6, 6)) == 20

    def test_diagonal_four(self) -> None:
        """5 + 10 + 5 + 10 = 30 ft."""
        assert distance_ft((3, 3), (7, 7)) == 30

    def test_mixed_2row_1col(self) -> None:
        """2 rows, 1 col = 1 diag + 1 straight = 5 + 5 = 10 ft."""
        assert distance_ft((3, 3), (5, 4)) == 10

    def test_mixed_3row_1col(self) -> None:
        """3 rows, 1 col = 1 diag + 2 straight = 5 + 10 = 15 ft."""
        assert distance_ft((3, 3), (6, 4)) == 15

    def test_symmetric(self) -> None:
        """distance(a, b) == distance(b, a)."""
        assert distance_ft((2, 5), (7, 3)) == distance_ft((7, 3), (2, 5))


# ---------------------------------------------------------------------------
# Test: Chebyshev squares
# ---------------------------------------------------------------------------

class TestChebyshevSquares:

    def test_same(self) -> None:
        assert chebyshev_squares((3, 3), (3, 3)) == 0

    def test_adjacent(self) -> None:
        assert chebyshev_squares((3, 3), (3, 4)) == 1
        assert chebyshev_squares((3, 3), (4, 4)) == 1

    def test_two_away(self) -> None:
        assert chebyshev_squares((3, 3), (5, 5)) == 2
        assert chebyshev_squares((3, 3), (3, 5)) == 2


# ---------------------------------------------------------------------------
# Test: Adjacency
# ---------------------------------------------------------------------------

class TestAdjacent:

    def test_orthogonal_adjacent(self) -> None:
        assert is_adjacent((3, 3), (3, 4)) is True
        assert is_adjacent((3, 3), (4, 3)) is True

    def test_diagonal_adjacent(self) -> None:
        assert is_adjacent((3, 3), (4, 4)) is True

    def test_same_square_not_adjacent(self) -> None:
        assert is_adjacent((3, 3), (3, 3)) is False

    def test_two_away_not_adjacent(self) -> None:
        assert is_adjacent((3, 3), (3, 5)) is False


# ---------------------------------------------------------------------------
# Test E: 10-ft reach special case
# ---------------------------------------------------------------------------

class TestWithinReach:
    """(AoN: https://2e.aonprd.com/Rules.aspx?ID=2379)"""

    def test_longsword_adjacent_orth(self) -> None:
        assert is_within_reach((3, 3), (3, 4), 5) is True

    def test_longsword_adjacent_diag(self) -> None:
        assert is_within_reach((3, 3), (4, 4), 5) is True

    def test_longsword_2_squares(self) -> None:
        """5-ft reach, 2 orth squares (10 ft) → False."""
        assert is_within_reach((3, 3), (3, 5), 5) is False

    def test_whip_2_diagonal(self) -> None:
        """10-ft reach, 2 diag squares → True (Chebyshev special case)."""
        assert is_within_reach((3, 3), (5, 5), 10) is True

    def test_whip_2_orthogonal(self) -> None:
        """10-ft reach, 2 orth squares (10 ft) → True."""
        assert is_within_reach((3, 3), (3, 5), 10) is True

    def test_whip_3_diagonal(self) -> None:
        """10-ft reach, 3 diag squares → False (Chebyshev 3 > 2)."""
        assert is_within_reach((3, 3), (6, 6), 10) is False

    def test_same_square_not_in_reach(self) -> None:
        """Can't reach yourself."""
        assert is_within_reach((3, 3), (3, 3), 5) is False
        assert is_within_reach((3, 3), (3, 3), 10) is False


# ---------------------------------------------------------------------------
# Test F: Emanation boundary (30-ft banner aura)
# ---------------------------------------------------------------------------

class TestEmanation:
    """(AoN: https://2e.aonprd.com/Rules.aspx?ID=2387)"""

    def test_30ft_orthogonal_in(self) -> None:
        g = GridState(rows=20, cols=20)
        aura = squares_in_emanation((10, 10), 30, g)
        assert (10, 16) in aura  # 6 orth = 30 ft

    def test_30ft_orthogonal_out(self) -> None:
        g = GridState(rows=20, cols=20)
        aura = squares_in_emanation((10, 10), 30, g)
        assert (10, 17) not in aura  # 7 orth = 35 ft

    def test_30ft_diagonal_in(self) -> None:
        g = GridState(rows=20, cols=20)
        aura = squares_in_emanation((10, 10), 30, g)
        assert (14, 14) in aura  # 4 diag = 30 ft

    def test_30ft_diagonal_out(self) -> None:
        g = GridState(rows=20, cols=20)
        aura = squares_in_emanation((10, 10), 30, g)
        assert (15, 15) not in aura  # 5 diag = 35 ft

    def test_includes_center(self) -> None:
        g = GridState(rows=10, cols=10)
        aura = squares_in_emanation((5, 5), 5, g)
        assert (5, 5) in aura

    def test_clips_to_grid(self) -> None:
        """Emanation near the grid edge doesn't include out-of-bounds."""
        g = GridState(rows=5, cols=5)
        aura = squares_in_emanation((0, 0), 10, g)
        assert (-1, 0) not in aura
        assert all(0 <= r < 5 and 0 <= c < 5 for r, c in aura)


# ---------------------------------------------------------------------------
# Test A: Parse/render semantic roundtrip
# ---------------------------------------------------------------------------

class TestParseRender:

    def test_basic_roundtrip(self) -> None:
        grid_str = (
            ".  .  .  .  .\n"
            ".  .  m  .  .\n"
            ".  g  .  m  .\n"
            ".  .  c  .  .\n"
            ".  .  B  .  .\n"
        )
        grid_state, positions, banner_pos = parse_map(grid_str)
        assert grid_state.rows == 5
        assert grid_state.cols == 5
        assert positions["c"] == (3, 2)
        assert positions["g"] == (2, 1)
        assert "m1" in positions
        assert "m2" in positions
        assert banner_pos == (4, 2)

    def test_banner_renders_as_star(self) -> None:
        grid_str = ". . B\n. c .\n. . ."
        grid_state, positions, banner_pos = parse_map(grid_str)
        rendered = render_map(grid_state, positions, banner_pos)
        assert "*" in rendered
        # B should not appear in rendered output
        # (check lines, not header which might have digits)
        data_lines = rendered.split("\n")[1:]  # skip header
        for line in data_lines:
            assert "B" not in line

    def test_star_input_accepted(self) -> None:
        """Parser accepts * as banner token too."""
        grid_str = ". . *\n. c ."
        _, _, banner_pos = parse_map(grid_str)
        assert banner_pos == (0, 2)

    def test_walls_parsed(self) -> None:
        grid_str = "# . #\n. c .\n# . #"
        grid_state, positions, _ = parse_map(grid_str)
        assert (0, 0) in grid_state.walls
        assert (0, 2) in grid_state.walls
        assert (2, 0) in grid_state.walls
        assert (2, 2) in grid_state.walls
        assert positions["c"] == (1, 1)

    def test_render_with_row_col_headers(self) -> None:
        grid = GridState(rows=3, cols=3)
        positions = {"c": (1, 1)}
        rendered = render_map(grid, positions)
        lines = rendered.split("\n")
        assert "0" in lines[0]  # column header
        assert lines[1].strip().startswith("0")  # row 0


# ---------------------------------------------------------------------------
# Test H: Movement blocked in corridor
# ---------------------------------------------------------------------------

class TestPathfindingCorridor:

    def test_blocked_no_detour(self) -> None:
        """Ally in 1-wide corridor, enemy blocking, walls on sides."""
        walls = set()
        for c in range(5):
            walls.add((0, c))
            walls.add((2, c))
        grid = GridState(rows=3, cols=5, walls=walls)
        # Start (1,1), blocker at (1,2), target at (1,3)
        blocked = walls | {(1, 2)}
        cost = shortest_movement_cost((1, 1), (1, 3), blocked, grid)
        assert cost == 999

    def test_open_field_straight_path(self) -> None:
        """No obstacles — shortest path is straight."""
        grid = GridState(rows=10, cols=10)
        # Start (5,2), target (5,5). Adjacent goals include (5,4).
        # Cost: (5,2)->(5,3)->(5,4) = 10 ft. But (5,4) is adjacent to (5,5).
        cost = shortest_movement_cost((5, 2), (5, 5), set(), grid)
        assert cost == 10

    def test_already_adjacent(self) -> None:
        """Start is already adjacent to target."""
        grid = GridState(rows=10, cols=10)
        cost = shortest_movement_cost((5, 4), (5, 5), set(), grid)
        assert cost == 0


# ---------------------------------------------------------------------------
# Test I: Target surrounded
# ---------------------------------------------------------------------------

class TestPathfindingSurrounded:

    def test_all_adjacent_occupied(self) -> None:
        grid = GridState(rows=5, cols=5)
        target = (2, 2)
        surrounders = {
            (1, 1), (1, 2), (1, 3),
            (2, 1),         (2, 3),
            (3, 1), (3, 2), (3, 3),
        }
        cost = shortest_movement_cost((0, 0), target, surrounders, grid)
        assert cost == 999
