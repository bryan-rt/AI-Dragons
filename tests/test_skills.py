"""Tests for skill and lore proficiency system (CP5.1 Pass 3a).

Updated Phase B: skill values from Foundry VTT exports (JSON authoritative).
"""

from pf2e.combat_math import lore_bonus, skill_bonus
from pf2e.types import Skill
from tests.fixtures import make_aetregan, make_dalai, make_erisen, make_rook


class TestAetreganSkills:
    """Verified against Foundry VTT actor export."""

    def test_warfare_lore_plus_7(self) -> None:
        """Warfare Lore: Int 18 (+4) + trained (+3 at L1) = +7."""
        assert lore_bonus(make_aetregan(), "Warfare") == 7

    def test_deity_lore_untrained(self) -> None:
        """Foundry JSON has no Deity Lore → untrained → Int mod only = +4."""
        assert lore_bonus(make_aetregan(), "Deity") == 4

    def test_arcana_plus_7(self) -> None:
        """Trained Int skill: Int +4 + trained +3 = +7."""
        assert skill_bonus(make_aetregan(), Skill.ARCANA) == 7

    def test_stealth_plus_6(self) -> None:
        """Dex +3, trained +3 = +6."""
        assert skill_bonus(make_aetregan(), Skill.STEALTH) == 6

    def test_intimidation_trained_plus_4(self) -> None:
        """Cha 12 (+1), trained (+3) = +4 (Foundry: Intimidation trained)."""
        assert skill_bonus(make_aetregan(), Skill.INTIMIDATION) == 4

    def test_deception_trained_plus_4(self) -> None:
        """Cha 12 (+1), trained (+3) = +4 (Foundry: Deception trained, D10).

        Note: Deceptive Tactics feat lets Aetregan use Warfare Lore (+7)
        in place of Deception for Create a Diversion / Feint checks.
        """
        assert skill_bonus(make_aetregan(), Skill.DECEPTION) == 4

    def test_athletics_untrained_plus_0(self) -> None:
        """Foundry: Athletics not in Aetregan's skills → Str +0 untrained."""
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
    """Values from Foundry VTT exports (JSON authoritative)."""

    def test_rook_athletics_plus_4(self) -> None:
        """Foundry: Athletics not trained for Rook → Str +4 untrained = +4."""
        assert skill_bonus(make_rook(), Skill.ATHLETICS) == 4

    def test_dalai_performance_plus_4(self) -> None:
        """Foundry: Performance not trained for Dalai → Cha +4 untrained = +4."""
        assert skill_bonus(make_dalai(), Skill.PERFORMANCE) == 4

    def test_erisen_crafting_plus_4(self) -> None:
        """Foundry: Crafting not trained for Erisen → Int +4 untrained = +4."""
        assert skill_bonus(make_erisen(), Skill.CRAFTING) == 4


class TestUnsetSkill:
    def test_untrained_returns_ability_mod_only(self) -> None:
        """Skill not in dict -> UNTRAINED -> just ability mod.
        MEDICINE not in Aetregan's skills: Wis +0 (Foundry: Wis 10), untrained +0 = +0.
        """
        assert skill_bonus(make_aetregan(), Skill.MEDICINE) == 0
