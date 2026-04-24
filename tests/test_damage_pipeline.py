"""Tests for pf2e/damage_pipeline.py — strict PF2e damage resolution."""

import pytest

from pf2e.character import CombatantState, EnemyState
from pf2e.damage_pipeline import ReactionChoices, resolve_strike_outcome
from pf2e.types import SaveType
from sim.grid import GridState
from sim.grid_spatial import GridSpatialQueries
from sim.round_state import (
    CombatantSnapshot,
    EnemySnapshot,
    RoundState,
)
from tests.fixtures import (
    make_aetregan,
    make_dalai,
    make_rook_combat_state,
)


def _build_state(
    pcs: list[CombatantState] | None = None,
    enemies: list[EnemyState] | None = None,
    temp_hp_overrides: dict[str, int] | None = None,
) -> RoundState:
    """Build a minimal RoundState for pipeline tests."""
    if pcs is None:
        rook = make_rook_combat_state(anthem_active=True)
        rook.position = (5, 5)
        dalai = CombatantState.from_character(make_dalai(), anthem_active=True)
        dalai.position = (5, 6)
        aetregan = CombatantState.from_character(make_aetregan(), anthem_active=True)
        aetregan.position = (5, 4)
        pcs = [aetregan, rook, dalai]
    if enemies is None:
        enemies = [EnemyState(
            name="Bandit1", ac=15, position=(5, 7),
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            attack_bonus=7, damage_dice="1d8", damage_bonus=3,
            num_attacks_per_turn=2,
        )]
    grid = GridState(rows=10, cols=10)

    pc_snaps: dict[str, CombatantSnapshot] = {}
    for pc in pcs:
        snap = CombatantSnapshot.from_combatant_state(pc)
        if temp_hp_overrides and snap.name in temp_hp_overrides:
            from dataclasses import replace
            snap = replace(snap, temp_hp=temp_hp_overrides[snap.name])
        pc_snaps[snap.name] = snap
    enemy_snaps = {e.name: EnemySnapshot.from_enemy_state(e) for e in enemies}

    return RoundState(
        pcs=pc_snaps,
        enemies=enemy_snaps,
        initiative_order=tuple(
            list(pc_snaps.keys()) + list(enemy_snaps.keys())
        ),
        current_turn_idx=0,
        round_number=1,
        grid=grid,
        banner_position=(5, 4),
        banner_planted=False,
        anthem_active=True,
    )


NO_REACTIONS = ReactionChoices()


class TestResolveStrikeBasic:

    def test_hit_damage_reduces_hp(self) -> None:
        state = _build_state()
        res = resolve_strike_outcome(10.0, "Dalai Alpaca", state, NO_REACTIONS)
        assert res.damage_to_hp == 10.0
        assert res.target_name == "Dalai Alpaca"

    def test_crit_double_passed_through(self) -> None:
        """Pipeline receives pre-doubled damage; it all lands."""
        state = _build_state()
        res = resolve_strike_outcome(20.0, "Dalai Alpaca", state, NO_REACTIONS)
        assert res.damage_to_hp == 20.0

    def test_miss_zero_damage(self) -> None:
        state = _build_state()
        res = resolve_strike_outcome(0.0, "Dalai Alpaca", state, NO_REACTIONS)
        assert res.damage_to_hp == 0.0
        assert res.damage_to_temp_hp == 0.0
        assert res.shield_hardness_absorbed == 0.0
        assert res.resistance_absorbed == 0.0


class TestShieldBlock:

    def test_shield_block_absorbs_hardness(self) -> None:
        """Steel shield hardness 5: 10 dmg → 5 absorbed, 5 to HP."""
        state = _build_state()
        reactions = ReactionChoices(shield_block_by="Rook")
        res = resolve_strike_outcome(10.0, "Rook", state, reactions)
        assert res.shield_hardness_absorbed == 5.0
        # Remaining 5 → resistance 1 (Guardian's Armor) → 4 to HP
        assert res.resistance_absorbed == 1.0
        assert res.damage_to_hp == 4.0

    def test_shield_takes_passed_through_damage(self) -> None:
        state = _build_state()
        reactions = ReactionChoices(shield_block_by="Rook")
        res = resolve_strike_outcome(10.0, "Rook", state, reactions)
        assert res.shield_damage == 5.0  # 10 - 5 hardness = 5 passed through

    def test_shield_block_consumes_general_reaction(self) -> None:
        state = _build_state()
        reactions = ReactionChoices(shield_block_by="Rook")
        res = resolve_strike_outcome(10.0, "Rook", state, reactions)
        assert res.reactions_consumed["Rook"] == "general"


class TestIntercept:

    def test_intercept_redirects_to_interceptor(self) -> None:
        state = _build_state()
        reactions = ReactionChoices(intercept_by="Rook")
        res = resolve_strike_outcome(10.0, "Dalai Alpaca", state, reactions)
        assert res.target_name == "Rook"
        assert res.intercepted is True

    def test_intercept_consumes_guardian_reaction(self) -> None:
        state = _build_state()
        reactions = ReactionChoices(intercept_by="Rook")
        res = resolve_strike_outcome(10.0, "Dalai Alpaca", state, reactions)
        assert res.reactions_consumed["Rook"] == "guardian"

    def test_intercept_applies_guardians_armor(self) -> None:
        """Rook intercepts 10 physical → resistance 1 → 9 to HP."""
        state = _build_state()
        reactions = ReactionChoices(intercept_by="Rook")
        res = resolve_strike_outcome(10.0, "Dalai Alpaca", state, reactions)
        assert res.resistance_absorbed == 1.0
        assert res.damage_to_hp == 9.0


class TestResistance:

    def test_guardians_armor_reduces_damage(self) -> None:
        """Rook (Guardian L1, full plate) takes 10 physical → resistance 1."""
        state = _build_state()
        res = resolve_strike_outcome(10.0, "Rook", state, NO_REACTIONS)
        assert res.resistance_absorbed == 1.0
        assert res.damage_to_hp == 9.0

    def test_resistance_physical_only(self) -> None:
        """Non-physical damage bypasses Guardian's Armor."""
        state = _build_state()
        res = resolve_strike_outcome(
            10.0, "Rook", state, NO_REACTIONS, is_physical=False,
        )
        assert res.resistance_absorbed == 0.0
        assert res.damage_to_hp == 10.0


class TestTempHP:

    def test_temp_hp_absorbed_first(self) -> None:
        state = _build_state(temp_hp_overrides={"Dalai Alpaca": 4})
        res = resolve_strike_outcome(10.0, "Dalai Alpaca", state, NO_REACTIONS)
        assert res.damage_to_temp_hp == 4.0
        assert res.damage_to_hp == 6.0

    def test_temp_hp_exceeds_damage(self) -> None:
        state = _build_state(temp_hp_overrides={"Dalai Alpaca": 10})
        res = resolve_strike_outcome(4.0, "Dalai Alpaca", state, NO_REACTIONS)
        assert res.damage_to_temp_hp == 4.0
        assert res.damage_to_hp == 0.0


class TestFullPipeline:

    def test_all_absorptions_in_order(self) -> None:
        """20 physical to Dalai, intercepted by Rook who has shield + 4 temp HP.

        Pipeline: intercept → Rook receives 20
        Shield Block (hardness 5) → 15 remaining
        Resistance (Guardian's Armor 1) → 14 remaining
        Temp HP (4) → 10 remaining
        Real HP → 10 damage
        """
        state = _build_state(temp_hp_overrides={"Rook": 4})
        reactions = ReactionChoices(intercept_by="Rook", shield_block_by="Rook")
        res = resolve_strike_outcome(20.0, "Dalai Alpaca", state, reactions)
        assert res.intercepted is True
        assert res.target_name == "Rook"
        assert res.shield_hardness_absorbed == 5.0
        assert res.resistance_absorbed == 1.0
        assert res.damage_to_temp_hp == 4.0
        assert res.damage_to_hp == 10.0

    def test_absorption_exact_amounts(self) -> None:
        """7 physical to Rook with shield block, no temp HP.

        Shield Block (5) → 2 remaining
        Resistance (1) → 1 remaining
        Temp HP (0) → 0 absorbed
        HP → 1 damage
        """
        state = _build_state()
        reactions = ReactionChoices(shield_block_by="Rook")
        res = resolve_strike_outcome(7.0, "Rook", state, reactions)
        assert res.shield_hardness_absorbed == 5.0
        assert res.resistance_absorbed == 1.0
        assert res.damage_to_temp_hp == 0.0
        assert res.damage_to_hp == 1.0
