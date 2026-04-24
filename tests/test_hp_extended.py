"""Tests for HP data on all PCs (CP5.1 Pass 3a)."""

from pf2e.combat_math import max_hp
from tests.fixtures import make_aetregan, make_dalai, make_erisen, make_rook


class TestAllPartyHP:

    def test_aetregan_15(self) -> None:
        """Elf 6 + (Commander 8 + Con +1) x 1 = 15."""
        assert max_hp(make_aetregan()) == 15

    def test_rook_23(self) -> None:
        """Automaton 10 + (Guardian 10 + Con +3) x 1 = 23."""
        assert max_hp(make_rook()) == 23

    def test_dalai_17(self) -> None:
        """Human 8 + (Bard 8 + Con +1) x 1 = 17."""
        assert max_hp(make_dalai()) == 17

    def test_erisen_16(self) -> None:
        """Elf 6 + (Inventor 8 + Con +2) x 1 = 16."""
        assert max_hp(make_erisen()) == 16
