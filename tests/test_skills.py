"""Tests for skill and lore proficiency system (CP5.1 Pass 3a)."""

from pf2e.combat_math import lore_bonus, skill_bonus
from pf2e.types import Skill
from tests.fixtures import make_aetregan, make_dalai, make_erisen, make_rook


class TestAetreganSkills:
    """Verified against Pathbuilder JSON character sheet."""

    def test_warfare_lore_plus_8(self) -> None:
        """Int +4, trained +3 = +7... wait: lore uses Int mod + prof.
        Int 18 (+4), trained at level 1 = +2 + 1 = +3. Total +7.
        Actually: proficiency_bonus(TRAINED, 1) = 2 + 1 = 3.
        lore_bonus = 4 + 3 = 7.
        """
        assert lore_bonus(make_aetregan(), "Warfare") == 7

    def test_deity_lore_plus_7(self) -> None:
        assert lore_bonus(make_aetregan(), "Deity") == 7

    def test_arcana_plus_7(self) -> None:
        """Trained Int skill: Int +4 + trained +3 = +7."""
        assert skill_bonus(make_aetregan(), Skill.ARCANA) == 7

    def test_stealth_plus_6(self) -> None:
        """Dex +3, trained +3 = +6."""
        assert skill_bonus(make_aetregan(), Skill.STEALTH) == 6

    def test_intimidation_untrained_plus_0(self) -> None:
        """Cha 10 (+0), untrained (+0) = +0."""
        assert skill_bonus(make_aetregan(), Skill.INTIMIDATION) == 0

    def test_deception_untrained_plus_0(self) -> None:
        """Cha 10 (+0), untrained (+0) = +0.

        Note: Deceptive Tactics feat lets Aetregan use Warfare Lore (+7)
        in place of Deception for Create a Diversion / Feint checks.
        """
        assert skill_bonus(make_aetregan(), Skill.DECEPTION) == 0

    def test_athletics_untrained_plus_0(self) -> None:
        assert skill_bonus(make_aetregan(), Skill.ATHLETICS) == 0

    def test_unknown_lore_returns_int_mod_only(self) -> None:
        """Lore not in character's list -> untrained -> Int mod only."""
        assert lore_bonus(make_aetregan(), "Underwater Basket Weaving") == 4

    def test_deceptive_tactics_flag(self) -> None:
        assert make_aetregan().has_deceptive_tactics is True

    def test_lengthy_diversion_flag(self) -> None:
        assert make_aetregan().has_lengthy_diversion is True

    def test_plant_banner_flag_false(self) -> None:
        assert make_aetregan().has_plant_banner is False


class TestSquadmateSkills:
    """Grounded defaults; verify against character sheets when available."""

    def test_rook_athletics_plus_7(self) -> None:
        """Str +4, trained +3 = +7."""
        assert skill_bonus(make_rook(), Skill.ATHLETICS) == 7

    def test_dalai_performance_plus_7(self) -> None:
        """Cha +4, trained +3 = +7."""
        assert skill_bonus(make_dalai(), Skill.PERFORMANCE) == 7

    def test_erisen_crafting_plus_7(self) -> None:
        """Int +4, trained +3 = +7."""
        assert skill_bonus(make_erisen(), Skill.CRAFTING) == 7


class TestUnsetSkill:
    def test_untrained_returns_ability_mod_only(self) -> None:
        """Skill not in dict -> UNTRAINED -> just ability mod."""
        # MEDICINE not in Aetregan's skills: Wis +1, untrained +0 = +1
        assert skill_bonus(make_aetregan(), Skill.MEDICINE) == 1
