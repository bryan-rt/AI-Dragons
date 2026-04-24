"""Tests for sim/round_state.py — frozen snapshots and RoundState branching."""

import pytest

from pf2e.character import CombatantState, EnemyState
from pf2e.types import SaveType
from sim.grid import GridState
from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState
from sim.scenario import load_scenario
from tests.fixtures import (
    make_aetregan,
    make_dalai,
    make_erisen,
    make_rook_combat_state,
)


def _make_bandit(name: str = "Bandit1") -> EnemyState:
    return EnemyState(
        name=name, ac=15,
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        position=(5, 7), attack_bonus=7, damage_dice="1d8",
        damage_bonus=3, num_attacks_per_turn=2,
    )


class TestRoundStateConstruction:

    def test_from_scenario_produces_correct_pc_snapshots(self) -> None:
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        init_order = ["Aetregan", "Rook", "Dalai Alpaca", "Erisen", "Bandit1"]
        state = RoundState.from_scenario(scenario, init_order)
        assert state.pcs["Aetregan"].current_hp == 15
        assert state.pcs["Rook"].current_hp == 23
        assert state.pcs["Dalai Alpaca"].current_hp == 17
        assert state.pcs["Erisen"].current_hp == 16

    def test_from_scenario_initiative_order_applied(self) -> None:
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        order = ["Bandit1", "Rook", "Aetregan", "Dalai Alpaca", "Erisen"]
        state = RoundState.from_scenario(scenario, order)
        assert state.initiative_order == tuple(order)

    def test_grid_shared_reference(self) -> None:
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        state = RoundState.from_scenario(scenario, ["Aetregan", "Bandit1"])
        assert state.grid is scenario.grid


class TestSnapshotImmutability:

    def test_combatant_snapshot_is_frozen(self) -> None:
        state = CombatantState.from_character(make_aetregan(), anthem_active=True)
        snap = CombatantSnapshot.from_combatant_state(state)
        with pytest.raises(Exception):
            snap.current_hp = 10  # type: ignore[misc]

    def test_enemy_snapshot_is_frozen(self) -> None:
        enemy = _make_bandit()
        snap = EnemySnapshot.from_enemy_state(enemy)
        with pytest.raises(Exception):
            snap.current_hp = 5  # type: ignore[misc]

    def test_saves_dict_copied_on_construction(self) -> None:
        enemy = _make_bandit()
        snap = EnemySnapshot.from_enemy_state(enemy)
        enemy.saves[SaveType.REFLEX] = 99
        assert snap.saves[SaveType.REFLEX] == 5


class TestBranching:

    def _make_state(self) -> RoundState:
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Aetregan", "Rook", "Bandit1"],
        )

    def test_with_pc_update_returns_new_instance(self) -> None:
        s1 = self._make_state()
        s2 = s1.with_pc_update("Aetregan", current_hp=10)
        assert s1 is not s2
        assert s2.pcs["Aetregan"].current_hp == 10

    def test_with_pc_update_other_pcs_unchanged(self) -> None:
        s1 = self._make_state()
        s2 = s1.with_pc_update("Aetregan", current_hp=10)
        assert s1.pcs["Rook"] is s2.pcs["Rook"]

    def test_with_pc_update_original_preserved(self) -> None:
        s1 = self._make_state()
        s1.with_pc_update("Aetregan", current_hp=10)
        assert s1.pcs["Aetregan"].current_hp == 15

    def test_branch_probability_carries_through(self) -> None:
        s1 = self._make_state()
        s2 = s1.with_branch_probability(0.6)
        s3 = s2.with_pc_update("Aetregan", current_hp=10)
        assert s3.branch_probability == 0.6
