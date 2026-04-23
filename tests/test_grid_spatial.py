"""Tests for GridSpatialQueries — the SpatialQueries Protocol implementation.

Includes the killer swap test: rerun the Checkpoint 1 Strike Hard scenario
with a real grid and confirm identical EV.
"""

import pytest

from pf2e.character import CombatantState, EnemyState
from pf2e.tactics import (
    STRIKE_HARD,
    TACTICAL_TAKEDOWN,
    MockSpatialQueries,
    TacticContext,
    evaluate_tactic,
)
from pf2e.types import SaveType
from sim.grid import GridState
from sim.grid_spatial import GridSpatialQueries
from tests.fixtures import (
    make_aetregan,
    make_dalai,
    make_erisen,
    make_rook,
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


# ---------------------------------------------------------------------------
# Test B: GridSpatialQueries correctness against a known grid
# ---------------------------------------------------------------------------

class TestGridSpatialCorrectness:

    def test_known_scenario(self) -> None:
        """Aetregan at (5,5) with banner, Rook at (5,6), Bandit at (5,7)."""
        grid = GridState(rows=10, cols=10)
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

        # Rook is 5 ft from banner → in 30-ft aura
        assert spatial.is_in_banner_aura("Rook") is True
        # Bandit adjacent to Rook, longsword reach 5 ft
        assert spatial.enemies_reachable_by("Rook") == ["Bandit1"]
        assert spatial.is_adjacent("Rook", "Bandit1") is True
        # 2 orthogonal squares = 10 ft
        assert spatial.distance_ft("Aetregan", "Bandit1") == 10

    def test_whip_reach(self) -> None:
        """Aetregan's whip (reach 10 ft) can hit enemies 2 squares away."""
        grid = GridState(rows=10, cols=10)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (5, 5)
        bandit_near = _make_bandit("Near", (5, 7))   # 2 orth = 10 ft
        bandit_far = _make_bandit("Far", (5, 8))     # 3 orth = 15 ft
        bandit_diag = _make_bandit("Diag", (7, 7))   # 2 diag (Chebyshev ≤ 2)

        spatial = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[],
            enemies=[bandit_near, bandit_far, bandit_diag],
            banner_position=None,
        )

        reachable = spatial.enemies_reachable_by("Aetregan")
        assert "Near" in reachable
        assert "Far" not in reachable
        assert "Diag" in reachable  # 10-ft reach Chebyshev exception

    def test_not_in_aura_when_far(self) -> None:
        """A squadmate far from the banner is NOT in the aura."""
        grid = GridState(rows=20, cols=20)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        erisen = CombatantState.from_character(make_erisen())
        erisen.position = (15, 15)

        spatial = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[erisen],
            enemies=[],
            banner_position=(0, 0),
        )
        # distance_ft((0,0),(15,15)) = lots (15 diag) >> 30 ft
        assert spatial.is_in_banner_aura("Erisen") is False

    def test_unknown_name_returns_safe_defaults(self) -> None:
        grid = GridState(rows=5, cols=5)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)

        spatial = GridSpatialQueries(
            grid_state=grid,
            commander=aetregan,
            squadmates=[],
            enemies=[],
            banner_position=(0, 0),
        )
        assert spatial.is_in_banner_aura("Nobody") is False
        assert spatial.enemies_reachable_by("Nobody") == []
        assert spatial.is_adjacent("Nobody", "Also Nobody") is False
        assert spatial.distance_ft("Nobody", "Also Nobody") == 999
        assert spatial.can_reach_with_stride("Nobody", "Also Nobody", 999) is False


# ---------------------------------------------------------------------------
# Test C: Killer swap test — Mock → Grid, same EV
# ---------------------------------------------------------------------------

class TestSwapMockForGrid:

    def test_strike_hard_ev_matches_mock(self) -> None:
        """Build a real grid matching the Checkpoint 1 mock's assumptions.

        Expect identical result: eligible=True, best=Rook, EV 8.55.
        """
        grid = GridState(rows=10, cols=10)
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
            spatial=MockSpatialQueries(),  # placeholder
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


# ---------------------------------------------------------------------------
# Test G: Pathfinding detour around blocker
# ---------------------------------------------------------------------------

class TestPathfindingDetour:

    def test_detour_around_blocking_enemy(self) -> None:
        """Ally at (2,1), blocking enemy at (2,2), target at (2,4).

        Direct path blocked. Diagonal detour: (2,1)->(3,2)->(2,3).
        Cost = 10 ft. (2,3) is adjacent to (2,4).
        Rook half-speed = 10 ft → reachable.
        """
        grid = GridState(rows=5, cols=6)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
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
        # Rook half-speed = 10 ft
        assert spatial.can_reach_with_stride("Rook", "Target", 10) is True

    def test_detour_insufficient_speed(self) -> None:
        """Same setup but with only 5 ft budget → can't make it."""
        grid = GridState(rows=5, cols=6)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
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
        assert spatial.can_reach_with_stride("Rook", "Target", 5) is False


# ---------------------------------------------------------------------------
# Test I: Target surrounded
# ---------------------------------------------------------------------------

class TestSurroundedTarget:

    def test_no_open_adjacent_square(self) -> None:
        """All 8 squares around target occupied. Can't end adjacent."""
        grid = GridState(rows=5, cols=5)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        ally = make_rook_combat_state()
        ally.position = (0, 1)

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
        assert spatial.can_reach_with_stride("Rook", "Target", 999) is False


# ---------------------------------------------------------------------------
# Test J (corrected): Diagonal bypass of strict ally blocking
# ---------------------------------------------------------------------------

class TestDiagonalBypass:

    def test_diagonal_bypass_five_feet(self) -> None:
        """Ally A at (3,3), Ally B blocking at (3,4), target at (3,5).

        Diagonal neighbor (2,4) or (4,4) is adjacent to target and
        reachable in one diagonal step = 5 ft.
        """
        grid = GridState(rows=6, cols=6)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        ally_a = make_rook_combat_state()
        ally_a.position = (3, 3)
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
        # One diagonal step (5 ft) to (2,4) or (4,4), both adjacent to target
        assert spatial.can_reach_with_stride("Rook", "Target", 5) is True
        assert spatial.can_reach_with_stride("Rook", "Target", 4) is False
