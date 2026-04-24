"""Tests for CombatantState and EnemyState extensions (Pass 3a)."""

from pf2e.character import CombatantState, EnemyState
from pf2e.types import SaveType
from tests.fixtures import make_aetregan, make_rook_combat_state


class TestCombatantHP:
    def test_current_hp_defaults_to_none(self) -> None:
        state = CombatantState.from_character(make_aetregan())
        assert state.current_hp is None

    def test_effective_current_hp_none_means_max(self) -> None:
        state = CombatantState.from_character(make_aetregan())
        assert state.effective_current_hp == 15

    def test_effective_current_hp_with_value(self) -> None:
        state = CombatantState.from_character(make_aetregan())
        state.current_hp = 8
        assert state.effective_current_hp == 8

    def test_temp_hp_default(self) -> None:
        state = CombatantState.from_character(make_aetregan())
        assert state.temp_hp == 0

    def test_actions_remaining_default(self) -> None:
        state = CombatantState.from_character(make_aetregan())
        assert state.actions_remaining == 3


class TestEnemyExtensions:
    def _make(self, **kwargs) -> EnemyState:
        defaults = dict(
            name="B", ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
            position=(5, 5),
        )
        defaults.update(kwargs)
        return EnemyState(**defaults)

    def test_default_max_hp(self) -> None:
        assert self._make().max_hp == 20

    def test_explicit_max_hp(self) -> None:
        assert self._make(max_hp=60).max_hp == 60

    def test_effective_current_hp_none_means_max(self) -> None:
        assert self._make(max_hp=20).effective_current_hp == 20

    def test_effective_current_hp_with_value(self) -> None:
        e = self._make(max_hp=20)
        e.current_hp = 12
        assert e.effective_current_hp == 12

    def test_perception_dc_derivation(self) -> None:
        assert self._make(perception_bonus=4).perception_dc == 14

    def test_perception_dc_zero(self) -> None:
        assert self._make(perception_bonus=0).perception_dc == 10

    def test_actions_remaining_default(self) -> None:
        assert self._make().actions_remaining == 3
