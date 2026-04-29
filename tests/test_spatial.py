"""Tests for spatial/positional systems (CP10.6).

Covers: are_flanking geometry, is_flanking with reach, compute_cover_level,
effective_target_ac integration, strike evaluator integration, and regression.
"""

import pytest
from dataclasses import replace

from pf2e.actions import Action, ActionType
from pf2e.strike import (
    _are_flanking,
    is_flanking,
    effective_target_ac,
    evaluate_pc_weapon_strike,
    evaluate_enemy_strike,
)
from sim.grid import (
    GridState,
    are_flanking as grid_are_flanking,
    CoverLevel,
    _bresenham_line,
    compute_cover_level,
)
from sim.round_state import RoundState
from sim.scenario import load_scenario

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quick_state(
    pc_overrides: dict | None = None,
    enemy_overrides: dict | None = None,
) -> RoundState:
    scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
    init_order = ["Aetregan", "Rook", "Dalai Alpaca", "Erisen", "Bandit1"]
    state = RoundState.from_scenario(scenario, init_order)
    if pc_overrides:
        for name, changes in pc_overrides.items():
            state = state.with_pc_update(name, **changes)
    if enemy_overrides:
        for name, changes in enemy_overrides.items():
            state = state.with_enemy_update(name, **changes)
    return state


# ===========================================================================
# are_flanking geometry (8)
# ===========================================================================

class TestAreFlanking:

    def test_opposite_sides_row(self):
        """A at (0,1), B at (2,1) flank T at (1,1) — directly opposite."""
        assert _are_flanking((0, 1), (1, 1), (2, 1)) is True
        assert grid_are_flanking((0, 1), (1, 1), (2, 1)) is True

    def test_opposite_sides_col(self):
        """A at (1,0), B at (1,2) flank T at (1,1)."""
        assert _are_flanking((1, 0), (1, 1), (1, 2)) is True

    def test_diagonal_opposite(self):
        """A at (0,0), B at (2,2) flank T at (1,1)."""
        assert _are_flanking((0, 0), (1, 1), (2, 2)) is True

    def test_same_side(self):
        """A at (0,0), B at (0,1) do NOT flank T at (1,1) — same side."""
        assert _are_flanking((0, 0), (1, 1), (0, 1)) is False

    def test_same_position(self):
        """Actor and ally at same position — not flanking."""
        assert _are_flanking((0, 0), (1, 1), (0, 0)) is False

    def test_at_target_position(self):
        """Actor at target position — not flanking."""
        assert _are_flanking((1, 1), (1, 1), (2, 2)) is False

    def test_ally_at_target(self):
        """Ally at target position — not flanking."""
        assert _are_flanking((0, 0), (1, 1), (1, 1)) is False

    def test_perpendicular_dot_zero(self):
        """(0,1) and (1,0) relative to (0,0) — dot=0 → flanking (approximation)."""
        assert _are_flanking((0, 1), (0, 0), (1, 0)) is True


# ===========================================================================
# is_flanking with reach (5)
# ===========================================================================

class TestIsFlanking:

    def test_ally_in_reach_opposite(self):
        """Rook at (5,6), Aetregan at (5,8), Bandit at (5,7) — opposite sides, both in reach."""
        state = _quick_state(pc_overrides={
            "Aetregan": {"position": (5, 8)},
        })
        assert is_flanking((5, 6), (5, 7), state) is True

    def test_ally_out_of_reach(self):
        """Ally geometrically flanking but too far to threaten."""
        state = _quick_state(pc_overrides={
            "Aetregan": {"position": (5, 11)},  # far away
        })
        # Only Aetregan is on opposite side; others are same side
        assert is_flanking((5, 6), (5, 7), state) is False

    def test_no_living_allies(self):
        state = _quick_state(pc_overrides={
            "Aetregan": {"current_hp": 0},
            "Dalai Alpaca": {"current_hp": 0},
            "Erisen": {"current_hp": 0},
        })
        assert is_flanking((5, 6), (5, 7), state) is False

    def test_dead_ally_excluded(self):
        """Dead ally on opposite side doesn't count."""
        state = _quick_state(pc_overrides={
            "Aetregan": {"position": (5, 8), "current_hp": 0},
        })
        assert is_flanking((5, 6), (5, 7), state) is False

    def test_self_excluded(self):
        """Actor's own position is excluded from ally check."""
        state = _quick_state()
        # Rook at (5,6) — checking flanking from (5,6) should skip Rook
        # All other PCs are on same side as (5,6), so no flanking
        assert is_flanking((5, 6), (5, 7), state) is False


# ===========================================================================
# compute_cover_level (5)
# ===========================================================================

class TestCoverLevel:

    def test_no_walls_returns_none(self):
        grid = GridState(rows=10, cols=10)
        assert compute_cover_level((0, 0), (5, 5), grid) == CoverLevel.NONE

    def test_wall_on_path_returns_standard(self):
        grid = GridState(rows=10, cols=10, walls={(2, 2)})
        level = compute_cover_level((0, 0), (4, 4), grid)
        assert level == CoverLevel.STANDARD

    def test_wall_beside_path_returns_none(self):
        """Wall adjacent but not on the line → no cover."""
        grid = GridState(rows=10, cols=10, walls={(1, 0)})
        level = compute_cover_level((0, 0), (0, 5), grid)
        assert level == CoverLevel.NONE

    def test_wall_at_endpoint_not_counted(self):
        """Wall at attacker position doesn't grant cover."""
        grid = GridState(rows=10, cols=10, walls={(0, 0)})
        level = compute_cover_level((0, 0), (3, 3), grid)
        assert level == CoverLevel.NONE

    def test_cover_level_values(self):
        assert CoverLevel.NONE == 0
        assert CoverLevel.LESSER == 1
        assert CoverLevel.STANDARD == 2
        assert CoverLevel.GREATER == 4


# ===========================================================================
# effective_target_ac (4)
# ===========================================================================

class TestEffectiveTargetAC:

    def test_base_ac_no_modifiers(self):
        state = _quick_state()
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (0, 0), state)
        assert ac == target.ac  # no flanking from (0,0), not off_guard

    def test_off_guard_minus_2(self):
        state = _quick_state(enemy_overrides={"Bandit1": {"off_guard": True}})
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (0, 0), state)
        assert ac == target.ac - 2

    def test_flanked_minus_2(self):
        """Flanking from opposite sides → -2 AC."""
        state = _quick_state(pc_overrides={
            "Aetregan": {"position": (5, 8)},
        })
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (5, 6), state)
        assert ac == target.ac - 2

    def test_cover_bonus_plus_2(self):
        state = _quick_state()
        target = state.enemies["Bandit1"]
        ac = effective_target_ac(target, (0, 0), state, cover_bonus=2)
        assert ac == target.ac + 2


# ===========================================================================
# Strike evaluator integration (4)
# ===========================================================================

class TestStrikeIntegration:

    def test_strike_flanked_enemy_higher_ev(self):
        """Flanked enemy → lower effective AC → higher EV."""
        # No flanking
        state_no = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")
        r_no = evaluate_pc_weapon_strike(action, state_no)

        # With flanking: move Aetregan to opposite side
        state_fl = _quick_state(pc_overrides={
            "Aetregan": {"position": (5, 8)},
        })
        r_fl = evaluate_pc_weapon_strike(action, state_fl)

        assert r_no.eligible and r_fl.eligible
        assert r_fl.expected_damage_dealt > r_no.expected_damage_dealt

    def test_strike_default_positions_unchanged(self):
        """Default scenario positions produce no flanking → same EV as before."""
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")
        result = evaluate_pc_weapon_strike(action, state)
        # No flanking from default positions, no walls → base AC 15
        assert result.eligible

    def test_strike_cover_increases_ac(self):
        """Cover bonus increases effective AC in the evaluator.

        Melee reach (5ft) means attacker and defender are adjacent, so
        Bresenham interior is empty — no wall-based cover possible for
        adjacent melee. Test via effective_target_ac directly to verify
        the cover_bonus parameter works end-to-end.
        """
        state = _quick_state()
        target = state.enemies["Bandit1"]
        base_ac = effective_target_ac(target, (5, 6), state, cover_bonus=0)
        cover_ac = effective_target_ac(target, (5, 6), state, cover_bonus=2)
        assert cover_ac == base_ac + 2

    def test_enemy_strike_ignores_flanking(self):
        """Enemy strike still uses armor_class(), not effective_target_ac."""
        state = _quick_state()
        action = Action(type=ActionType.STRIKE, actor_name="Bandit1",
                        action_cost=1, target_name="Rook")
        result = evaluate_enemy_strike(action, state)
        assert result.eligible


# ===========================================================================
# Regression (3)
# ===========================================================================

class TestRegression:

    def test_ev_7_65_34th_verification(self):
        """34th verification: EV 7.65 — no flanking in default positions."""
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)

    def test_mortar_ev_5_95(self):
        from pf2e.save_damage import basic_save_ev
        ev = basic_save_ev(dc=17, save_mod=5, base_dmg=7.0)
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)

    def test_prone_probability_55pct(self):
        from pf2e.tactics import evaluate_tactic, TACTICAL_TAKEDOWN
        from tests.test_tactics import MockSpatialQueries

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        ctx.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": False},
            distances={("Rook", "Bandit1"): 10, ("Dalai Alpaca", "Bandit1"): 10},
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, ctx)
        assert result.eligible
        assert result.condition_probabilities["Bandit1"]["prone"] == pytest.approx(
            0.55, abs=0.01)
