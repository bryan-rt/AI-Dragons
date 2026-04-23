"""Tests for Checkpoint 4 defensive value computation."""

import pytest

from pf2e.character import CombatantState, EnemyState
from pf2e.combat_math import (
    expected_enemy_turn_damage,
    expected_incoming_damage,
    guardians_armor_resistance,
    plant_banner_temp_hp,
    temp_hp_ev,
)
from pf2e.tactics import (
    DEFENSIVE_RETREAT,
    GATHER_TO_ME,
    STRIKE_HARD,
    MockSpatialQueries,
    TacticContext,
    evaluate_tactic,
    intercept_attack_ev,
)
from pf2e.types import SaveType
from sim.grid import GridState
from sim.grid_spatial import GridSpatialQueries
from sim.scenario import load_scenario
from tests.fixtures import (
    make_aetregan,
    make_dalai,
    make_erisen,
    make_rook,
    make_rook_combat_state,
)

EV_TOLERANCE = 0.01


def _make_armed_bandit(
    name: str, pos: tuple[int, int],
    atk: int = 7, dmg: str = "1d8", dmg_bonus: int = 3,
) -> EnemyState:
    return EnemyState(
        name=name, ac=15,
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        position=pos,
        attack_bonus=atk, damage_dice=dmg, damage_bonus=dmg_bonus,
        num_attacks_per_turn=2,
    )


# ---------------------------------------------------------------------------
# Core math unit tests
# ---------------------------------------------------------------------------

class TestCoreMath:

    def test_plant_banner_temp_hp_scaling(self) -> None:
        assert plant_banner_temp_hp(1) == 4
        assert plant_banner_temp_hp(3) == 4
        assert plant_banner_temp_hp(4) == 8
        assert plant_banner_temp_hp(7) == 8
        assert plant_banner_temp_hp(8) == 12
        assert plant_banner_temp_hp(20) == 24

    def test_guardians_armor_resistance_scaling(self) -> None:
        assert guardians_armor_resistance(1) == 1
        assert guardians_armor_resistance(2) == 2
        assert guardians_armor_resistance(3) == 2
        assert guardians_armor_resistance(20) == 11

    def test_temp_hp_ev_capped(self) -> None:
        assert temp_hp_ev(4, 8.0) == 4.0

    def test_temp_hp_ev_partial(self) -> None:
        assert temp_hp_ev(4, 2.5) == 2.5

    def test_temp_hp_ev_zero_damage(self) -> None:
        assert temp_hp_ev(4, 0.0) == 0.0


# ---------------------------------------------------------------------------
# Expected incoming damage
# ---------------------------------------------------------------------------

class TestExpectedIncomingDamage:

    def test_first_strike_positive_ev(self) -> None:
        bandit = _make_armed_bandit("B", (5, 5))
        dalai = CombatantState.from_character(make_dalai())
        ev = expected_incoming_damage(bandit, dalai, attack_number=1)
        assert ev > 0.0

    def test_map_reduces_second_strike(self) -> None:
        bandit = _make_armed_bandit("B", (5, 5))
        dalai = CombatantState.from_character(make_dalai())
        ev1 = expected_incoming_damage(bandit, dalai, 1)
        ev2 = expected_incoming_damage(bandit, dalai, 2)
        assert ev2 < ev1

    def test_rook_resistance_reduces_ev(self) -> None:
        """Guardian's Armor reduces expected damage vs Rook."""
        bandit = _make_armed_bandit("B", (5, 5))
        rook = make_rook_combat_state()
        dalai = CombatantState.from_character(make_dalai())
        ev_rook = expected_incoming_damage(bandit, rook, 1)
        ev_dalai = expected_incoming_damage(bandit, dalai, 1)
        assert ev_rook < ev_dalai

    def test_no_damage_dice_returns_zero(self) -> None:
        harmless = EnemyState(
            name="H", ac=15,
            saves={SaveType.REFLEX: 0, SaveType.FORTITUDE: 0, SaveType.WILL: 0},
            position=(5, 5),
        )
        dalai = CombatantState.from_character(make_dalai())
        assert expected_incoming_damage(harmless, dalai) == 0.0

    def test_enemy_turn_total(self) -> None:
        """Full turn (2 attacks) > single attack."""
        bandit = _make_armed_bandit("B", (5, 5))
        dalai = CombatantState.from_character(make_dalai())
        ev_turn = expected_enemy_turn_damage(bandit, dalai)
        ev_single = expected_incoming_damage(bandit, dalai, 1)
        assert ev_turn > ev_single


# ---------------------------------------------------------------------------
# Intercept Attack
# ---------------------------------------------------------------------------

class TestInterceptAttackEv:

    def _setup(
        self, ally_pos: tuple[int, int], enemy_has_offense: bool = True,
    ) -> tuple[CombatantState, CombatantState, list[EnemyState], GridSpatialQueries]:
        grid = GridState(rows=10, cols=10)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        rook = make_rook_combat_state()
        rook.position = (5, 5)
        dalai = CombatantState.from_character(make_dalai())
        dalai.position = ally_pos
        dmg = "1d8" if enemy_has_offense else ""
        enemy = EnemyState(
            name="B", ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 7),
            attack_bonus=7, damage_dice=dmg, damage_bonus=3,
            num_attacks_per_turn=2,
        )
        spatial = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[rook, dalai], enemies=[enemy],
            banner_position=None, banner_planted=False,
        )
        return rook, dalai, [enemy], spatial

    def test_ally_adjacent_intercept(self) -> None:
        rook, ally, enemies, spatial = self._setup((5, 6))
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        assert ev == pytest.approx(1.0, abs=EV_TOLERANCE)

    def test_ally_too_far(self) -> None:
        rook, ally, enemies, spatial = self._setup((5, 9))
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        assert ev == 0.0

    def test_no_guardian_reaction(self) -> None:
        rook, ally, enemies, spatial = self._setup((5, 6))
        rook.guardian_reactions_available = 0
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        assert ev == 0.0

    def test_no_offensive_enemy(self) -> None:
        rook, ally, enemies, spatial = self._setup((5, 6), False)
        ev = intercept_attack_ev(rook, ally, enemies, spatial)
        assert ev == 0.0


# ---------------------------------------------------------------------------
# Planted banner 40-ft aura (regression from C.1)
# ---------------------------------------------------------------------------

class TestPlantedBannerAura:

    def test_35ft_diagonal_in_planted_out_carried(self) -> None:
        """5 diagonal squares = 35 ft. Planted (40-ft): IN. Carried (30-ft): OUT."""
        grid = GridState(rows=10, cols=10)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (0, 0)
        ally = make_rook_combat_state()
        ally.position = (5, 5)

        planted = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[ally], enemies=[],
            banner_position=(0, 0), banner_planted=True,
        )
        assert planted.is_in_banner_aura("Rook") is True

        carried = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[ally], enemies=[],
            banner_position=(0, 0), banner_planted=False,
        )
        assert carried.is_in_banner_aura("Rook") is False


# ---------------------------------------------------------------------------
# Gather to Me defensive EV
# ---------------------------------------------------------------------------

class TestGatherToMeDefensive:

    def test_temp_hp_for_ally_entering_aura(self) -> None:
        """Ally outside planted aura, enemy threatening → temp HP EV > 0."""
        grid = GridState(rows=15, cols=15)
        aetregan = CombatantState.from_character(make_aetregan(), anthem_active=True)
        aetregan.position = (7, 7)
        # Dalai far from banner but within enemy reach
        dalai = CombatantState.from_character(make_dalai(), anthem_active=True)
        dalai.position = (0, 0)
        rook = make_rook_combat_state(anthem_active=True)
        rook.position = (7, 8)
        bandit = _make_armed_bandit("Bandit1", (0, 1))

        spatial = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[rook, dalai], enemies=[bandit],
            banner_position=(7, 7), banner_planted=True,
        )
        ctx = TacticContext(
            commander=aetregan, squadmates=[rook, dalai],
            enemies=[bandit], banner_position=(7, 7),
            banner_planted=True, spatial=spatial, anthem_active=True,
        )
        result = evaluate_tactic(GATHER_TO_ME, ctx)
        assert result.eligible
        assert result.expected_damage_avoided > 0
        assert "plant_banner_temp_hp" in result.damage_prevented_sources

    def test_no_defensive_ev_without_enemy_offense(self) -> None:
        """Enemies with no damage_dice → 0 defensive EV."""
        grid = GridState(rows=10, cols=10)
        aetregan = CombatantState.from_character(make_aetregan())
        aetregan.position = (5, 5)
        rook = make_rook_combat_state()
        rook.position = (5, 6)
        harmless = EnemyState(
            name="H", ac=10,
            saves={SaveType.REFLEX: 0, SaveType.FORTITUDE: 0, SaveType.WILL: 0},
            position=(0, 0),
        )
        spatial = GridSpatialQueries(
            grid_state=grid, commander=aetregan,
            squadmates=[rook], enemies=[harmless],
            banner_position=(5, 5), banner_planted=True,
        )
        ctx = TacticContext(
            commander=aetregan, squadmates=[rook], enemies=[harmless],
            banner_position=(5, 5), banner_planted=True,
            spatial=spatial, anthem_active=False,
        )
        result = evaluate_tactic(GATHER_TO_ME, ctx)
        assert result.expected_damage_avoided == 0.0


# ---------------------------------------------------------------------------
# Regression: Strike Hard EV unchanged
# ---------------------------------------------------------------------------

class TestStrikeHardRegression:

    def test_ev_855_from_scenario_file(self) -> None:
        """Strike Hard EV 8.55 unchanged after Checkpoint 4 changes."""
        scenario = load_scenario(
            "scenarios/checkpoint_1_strike_hard.scenario",
        )
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(
            8.55, abs=EV_TOLERANCE,
        )
        assert result.expected_damage_avoided == 0.0
        assert result.damage_prevented_sources == {}
