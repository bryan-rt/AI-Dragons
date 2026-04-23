"""Real SpatialQueries backed by a GridState and combatant positions.

Implements the SpatialQueries Protocol from pf2e/tactics.py.
Positions are resolved from CombatantState/EnemyState objects at
construction time. The occupied-squares set is precomputed for
BFS pathfinding.
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

    Banner is an item (not a creature) — its square is passable.
    """

    def __init__(
        self,
        grid_state: GridState,
        commander: CombatantState,
        squadmates: list[CombatantState],
        enemies: list[EnemyState],
        banner_position: Pos | None,
        banner_planted: bool,
    ) -> None:
        self._grid = grid_state
        self._banner_pos = banner_position
        self._banner_planted = banner_planted
        self._positions: dict[str, Pos] = {}
        self._combatants: dict[str, CombatantState] = {}
        self._enemies_by_name: dict[str, EnemyState] = {}

        # Index commander
        self._positions[commander.character.name] = commander.position
        self._combatants[commander.character.name] = commander

        # Index squadmates
        for sq in squadmates:
            self._positions[sq.character.name] = sq.position
            self._combatants[sq.character.name] = sq

        # Index enemies
        for e in enemies:
            self._positions[e.name] = e.position
            self._enemies_by_name[e.name] = e

        # Occupied squares: all combatant positions + walls.
        # Banner is an item, not a creature — its square is passable.
        self._occupied_squares: set[Pos] = (
            set(self._positions.values()) | self._grid.walls
        )

    @classmethod
    def from_context(
        cls, grid_state: GridState, ctx: TacticContext,
    ) -> GridSpatialQueries:
        """Build from a TacticContext for convenient Protocol swap."""
        return cls(
            grid_state,
            ctx.commander,
            ctx.squadmates,
            ctx.enemies,
            ctx.banner_position,
            banner_planted=ctx.banner_planted,
        )

    def is_in_banner_aura(self, name: str) -> bool:
        """True if combatant is within the banner aura.

        Base aura: 30-ft emanation. When the banner is planted, the aura
        expands to a 40-ft burst.
        (AoN: https://2e.aonprd.com/Classes.aspx?ID=66 — base aura)
        (AoN: https://2e.aonprd.com/Feats.aspx?ID=7796 — planted expansion)
        """
        if self._banner_pos is None:
            return False
        pos = self._positions.get(name)
        if pos is None:
            return False
        radius = 40 if self._banner_planted else 30
        return grid.distance_ft(pos, self._banner_pos) <= radius

    def enemies_reachable_by(self, name: str) -> list[str]:
        """List enemies within this combatant's melee weapon reach.

        Uses melee_reach_ft() from the character's equipped weapons.
        10-ft reach (e.g., whip) uses the Chebyshev special case.
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2379)
        """
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
        """True if Chebyshev distance between the two is exactly 1."""
        a = self._positions.get(a_name)
        b = self._positions.get(b_name)
        if a is None or b is None:
            return False
        return grid.is_adjacent(a, b)

    def can_reach_with_stride(
        self, name: str, target: str, max_ft: int,
    ) -> bool:
        """Can this combatant Stride up to max_ft and end adjacent to target?

        Uses BFS pathfinding. The combatant's own square is excluded from
        the blocked set (they leave it). All other occupied squares and
        walls are impassable.

        SIMPLIFICATIONS:
        1. Uniform 5-ft step cost (not PF2e 5/10 diagonal alternation)
        2. No pass-through of occupied squares (stricter than RAW)
        3. No difficult terrain
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2360)
        """
        a_pos = self._positions.get(name)
        b_pos = self._positions.get(target)
        if a_pos is None or b_pos is None:
            return False
        # Already adjacent: zero movement needed
        if grid.is_adjacent(a_pos, b_pos):
            return True
        # Pathfind — exclude ally's own square from blocked set
        blocked = self._occupied_squares - {a_pos}
        cost = shortest_movement_cost(a_pos, b_pos, blocked, self._grid)
        return cost < 999 and cost <= max_ft

    def distance_ft(self, a_name: str, b_name: str) -> int:
        """PF2e grid distance (5/10 diagonal) between two combatants."""
        a = self._positions.get(a_name)
        b = self._positions.get(b_name)
        if a is None or b is None:
            return 999
        return grid.distance_ft(a, b)
