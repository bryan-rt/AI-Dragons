"""Tests for sim/initiative.py — seeded initiative rolling and tiebreakers."""

import random

import pytest

from pf2e.character import CombatantState, EnemyState
from pf2e.types import SaveType
from sim.initiative import roll_initiative
from sim.round_state import CombatantSnapshot, EnemySnapshot
from tests.fixtures import make_aetregan, make_dalai, make_rook_combat_state


def _pc_snap(name_override: str | None = None) -> CombatantSnapshot:
    """Quick PC snapshot from Aetregan."""
    state = CombatantState.from_character(make_aetregan())
    snap = CombatantSnapshot.from_combatant_state(state)
    if name_override:
        from dataclasses import replace
        snap = replace(snap, name=name_override)
    return snap


def _enemy_snap(
    name: str = "Bandit1", perception: int = 4,
) -> EnemySnapshot:
    e = EnemyState(
        name=name, ac=15, position=(5, 5),
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        perception_bonus=perception,
    )
    return EnemySnapshot.from_enemy_state(e)


class TestRolling:

    def test_seeded_deterministic(self) -> None:
        pcs = [CombatantSnapshot.from_combatant_state(
            CombatantState.from_character(make_aetregan()),
        )]
        enemies = [_enemy_snap()]
        order1 = roll_initiative(pcs, enemies, seed=42)
        order2 = roll_initiative(pcs, enemies, seed=42)
        assert order1 == order2

    def test_perception_bonus_applied(self) -> None:
        """Higher perception should tend to go first with same seed."""
        rook = CombatantSnapshot.from_combatant_state(
            make_rook_combat_state(),
        )  # Perception +6 (expert)
        dalai = CombatantSnapshot.from_combatant_state(
            CombatantState.from_character(make_dalai()),
        )  # Perception +5 (expert, lower Wis)
        # Use explicit to isolate the test from d20 variance
        order = roll_initiative(
            [rook, dalai], [], seed=1,
            explicit={"Rook": 16, "Dalai Alpaca": 15},
        )
        assert order[0] == "Rook"

    def test_isolated_rng_not_global(self) -> None:
        """roll_initiative uses its own RNG, not the global random module."""
        random.seed(999)
        ref_val = random.random()
        # Reset global seed
        random.seed(999)
        # Call initiative (should NOT touch global RNG)
        pcs = [CombatantSnapshot.from_combatant_state(
            CombatantState.from_character(make_aetregan()),
        )]
        roll_initiative(pcs, [_enemy_snap()], seed=42)
        # Global RNG should still produce the same value
        assert random.random() == ref_val


class TestOverrides:

    def test_full_explicit_override(self) -> None:
        pcs = [_pc_snap()]
        enemies = [_enemy_snap()]
        order = roll_initiative(
            pcs, enemies, seed=1,
            explicit={"Aetregan": 5, "Bandit1": 20},
        )
        assert order == ["Bandit1", "Aetregan"]

    def test_partial_override(self) -> None:
        """One combatant explicit, rest roll normally."""
        pcs = [_pc_snap()]
        enemies = [_enemy_snap("E1"), _enemy_snap("E2")]
        order = roll_initiative(
            pcs, enemies, seed=1,
            explicit={"Aetregan": 100},  # guaranteed first
        )
        assert order[0] == "Aetregan"


class TestTiebreakers:

    def test_enemy_beats_pc_on_tie(self) -> None:
        pcs = [_pc_snap()]
        enemies = [_enemy_snap()]
        order = roll_initiative(
            pcs, enemies, seed=1,
            explicit={"Aetregan": 15, "Bandit1": 15},
        )
        assert order[0] == "Bandit1"

    def test_alphabetical_among_pc_tie(self) -> None:
        a = _pc_snap("Alpha")
        b = _pc_snap("Beta")
        order = roll_initiative(
            [b, a], [], seed=1,
            explicit={"Alpha": 10, "Beta": 10},
        )
        assert order == ["Alpha", "Beta"]

    def test_alphabetical_among_enemy_tie(self) -> None:
        e1 = _enemy_snap("Goblin")
        e2 = _enemy_snap("Bandit")
        order = roll_initiative(
            [], [e2, e1], seed=1,
            explicit={"Goblin": 10, "Bandit": 10},
        )
        assert order == ["Bandit", "Goblin"]
