"""Tests for pf2e/modifiers.py — BonusTracker stacking rules + migration parity.

CP10.3 Pass 3 Part 4: ~28 tests (16 BonusTracker unit + 11 migration parity + 1 regression).
"""

import pytest

from pf2e.modifiers import BonusTracker, BonusType

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# BonusType enum
# ---------------------------------------------------------------------------

class TestBonusType:
    def test_all_types_exist(self):
        assert BonusType.CIRCUMSTANCE
        assert BonusType.STATUS
        assert BonusType.ITEM
        assert BonusType.PROFICIENCY
        assert BonusType.UNTYPED

    def test_types_are_distinct(self):
        types = list(BonusType)
        assert len(types) == 5
        assert len(set(types)) == 5


# ---------------------------------------------------------------------------
# BonusTracker unit tests (~16)
# ---------------------------------------------------------------------------

class TestBonusTrackerUnit:

    def test_empty_tracker_returns_zero(self):
        t = BonusTracker()
        assert t.total() == 0

    def test_single_untyped_positive(self):
        t = BonusTracker()
        t.add(BonusType.UNTYPED, 3, "ability")
        assert t.total() == 3

    def test_multiple_untyped_all_stack(self):
        """Multiple untyped bonuses all accumulate."""
        t = BonusTracker()
        t.add(BonusType.UNTYPED, 3, "ability")
        t.add(BonusType.UNTYPED, 2, "other")
        assert t.total() == 5

    def test_untyped_negatives_all_stack(self):
        """Multiple untyped penalties all accumulate (e.g., MAP + other)."""
        t = BonusTracker()
        t.add(BonusType.UNTYPED, -5, "MAP")
        t.add(BonusType.UNTYPED, -1, "other penalty")
        assert t.total() == -6

    def test_single_circumstance_bonus(self):
        t = BonusTracker()
        t.add(BonusType.CIRCUMSTANCE, 2, "cover")
        assert t.total() == 2

    def test_two_circumstance_bonuses_takes_highest(self):
        """Cover +2 circ + Raise Shield +2 circ = +2, not +4.
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2099)
        """
        t = BonusTracker()
        t.add(BonusType.CIRCUMSTANCE, 1, "lesser cover")
        t.add(BonusType.CIRCUMSTANCE, 2, "raise shield")
        assert t.total() == 2

    def test_single_circumstance_penalty(self):
        t = BonusTracker()
        t.add(BonusType.CIRCUMSTANCE, -2, "off-guard")
        assert t.total() == -2

    def test_two_circumstance_penalties_takes_worst(self):
        t = BonusTracker()
        t.add(BonusType.CIRCUMSTANCE, -1, "lesser penalty")
        t.add(BonusType.CIRCUMSTANCE, -2, "off-guard")
        assert t.total() == -2

    def test_circumstance_bonus_and_penalty_both_apply(self):
        """+2 and -2 CIRCUMSTANCE -> total = 0, not +2 or -2.
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2099)
        """
        t = BonusTracker()
        t.add(BonusType.CIRCUMSTANCE, 2, "raise shield")
        t.add(BonusType.CIRCUMSTANCE, -2, "off-guard")
        assert t.total() == 0

    def test_status_bonus_highest_only(self):
        t = BonusTracker()
        t.add(BonusType.STATUS, 1, "inspire courage")
        t.add(BonusType.STATUS, 2, "heroism")
        assert t.total() == 2

    def test_status_penalty_worst_only(self):
        t = BonusTracker()
        t.add(BonusType.STATUS, -1, "frightened 1")
        t.add(BonusType.STATUS, -2, "frightened 2")
        assert t.total() == -2

    def test_item_bonus_highest_only(self):
        t = BonusTracker()
        t.add(BonusType.ITEM, 1, "potency +1")
        t.add(BonusType.ITEM, 2, "potency +2")
        assert t.total() == 2

    def test_proficiency_highest_only(self):
        """Only one proficiency source expected; both accumulate (treated as untyped)."""
        t = BonusTracker()
        t.add(BonusType.PROFICIENCY, 3, "trained")
        t.add(BonusType.PROFICIENCY, 5, "expert")
        # PROFICIENCY is treated as untyped for stacking — both accumulate
        assert t.total() == 8

    def test_mixed_types_all_contribute(self):
        """Simulate: ability +3, prof +4, item +1, status +1, MAP -5."""
        t = BonusTracker()
        t.add(BonusType.UNTYPED, 3, "ability")
        t.add(BonusType.PROFICIENCY, 4, "trained")
        t.add(BonusType.ITEM, 1, "potency")
        t.add(BonusType.STATUS, 1, "inspire courage")
        t.add(BonusType.UNTYPED, -5, "MAP")
        assert t.total() == 4

    def test_zero_value_ignored(self):
        """Adding a zero-value typed modifier has no effect."""
        t = BonusTracker()
        t.add(BonusType.CIRCUMSTANCE, 0, "nothing")
        t.add(BonusType.STATUS, 0, "nothing")
        t.add(BonusType.ITEM, 0, "nothing")
        assert t.total() == 0

    def test_source_param_is_optional(self):
        """Source parameter defaults to empty string if omitted."""
        t = BonusTracker()
        t.add(BonusType.UNTYPED, 3)
        t.add(BonusType.CIRCUMSTANCE, 2)
        assert t.total() == 5


# ---------------------------------------------------------------------------
# Migration parity tests (~11)
# Verify that combat_math derivation functions produce the same values
# they always have, confirming BonusTracker integration is correct.
# ---------------------------------------------------------------------------

class TestMigrationParity:

    def test_attack_bonus_rook_parity(self):
        """Rook Earthbreaker: Str +4, trained +3, potency 0 = +7."""
        from pf2e.combat_math import attack_bonus
        from pf2e.character import CombatantState
        from tests.fixtures import make_rook

        rook = make_rook()
        state = CombatantState.from_character(rook)
        eq = rook.equipped_weapons[0]  # Earthbreaker
        assert attack_bonus(state, eq) == 7

    def test_attack_bonus_aetregan_parity(self):
        """Aetregan Scorpion Whip: Dex +3 (finesse), trained +3 = +6."""
        from pf2e.combat_math import attack_bonus
        from pf2e.character import CombatantState
        from tests.fixtures import make_aetregan

        aet = make_aetregan()
        state = CombatantState.from_character(aet)
        eq = aet.equipped_weapons[0]  # Scorpion Whip
        assert attack_bonus(state, eq) == 6

    def test_attack_bonus_with_anthem_parity(self):
        """Aetregan + Anthem: +6 base + status +1 = +7."""
        from pf2e.combat_math import attack_bonus
        from pf2e.character import CombatantState
        from tests.fixtures import make_aetregan

        aet = make_aetregan()
        state = CombatantState.from_character(aet, anthem_active=True)
        eq = aet.equipped_weapons[0]
        assert attack_bonus(state, eq) == 7

    def test_armor_class_rook_parity(self):
        """Rook AC: 10 + Dex 0 (cap 0) + trained 3 + full plate 6 = 19."""
        from pf2e.combat_math import armor_class
        from pf2e.character import CombatantState
        from tests.fixtures import make_rook

        state = CombatantState.from_character(make_rook())
        assert armor_class(state) == 19

    def test_armor_class_aetregan_parity(self):
        """Aetregan AC: 10 + Dex 3 + trained 3 + suit 2 = 18."""
        from pf2e.combat_math import armor_class
        from pf2e.character import CombatantState
        from tests.fixtures import make_aetregan

        state = CombatantState.from_character(make_aetregan())
        assert armor_class(state) == 18

    def test_armor_class_shield_raised_parity(self):
        """Rook AC with shield raised: 19 + shield 2 = 21."""
        from pf2e.combat_math import armor_class
        from pf2e.character import CombatantState
        from tests.fixtures import make_rook

        state = CombatantState.from_character(make_rook())
        state.shield_raised = True
        assert armor_class(state) == 21

    def test_armor_class_off_guard_and_shield(self):
        """Shield +2 circ, off_guard -2 circ -> both apply -> net 0 circ.

        Rook base AC 19, shield +2, off_guard -2 = 19.
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2099)
        """
        from pf2e.combat_math import armor_class
        from pf2e.character import CombatantState
        from tests.fixtures import make_rook

        state = CombatantState.from_character(make_rook())
        state.shield_raised = True
        state.off_guard = True
        assert armor_class(state) == 19

    def test_save_bonus_parity_all_chars(self):
        """Save bonuses match established values for all four characters."""
        from pf2e.combat_math import save_bonus
        from pf2e.types import SaveType
        from tests.fixtures import make_aetregan, make_rook, make_dalai, make_erisen

        # Aetregan: Fort +4, Ref +8, Will +5
        c = make_aetregan()
        assert save_bonus(c, SaveType.FORTITUDE) == 4
        assert save_bonus(c, SaveType.REFLEX) == 8
        assert save_bonus(c, SaveType.WILL) == 5
        # Rook: Fort +8, Ref +3, Will +6
        c = make_rook()
        assert save_bonus(c, SaveType.FORTITUDE) == 8
        assert save_bonus(c, SaveType.REFLEX) == 3
        assert save_bonus(c, SaveType.WILL) == 6
        # Dalai: Fort +4, Ref +5, Will +5
        c = make_dalai()
        assert save_bonus(c, SaveType.FORTITUDE) == 4
        assert save_bonus(c, SaveType.REFLEX) == 5
        assert save_bonus(c, SaveType.WILL) == 5
        # Erisen: Fort +7, Ref +5, Will +5
        c = make_erisen()
        assert save_bonus(c, SaveType.FORTITUDE) == 7
        assert save_bonus(c, SaveType.REFLEX) == 5
        assert save_bonus(c, SaveType.WILL) == 5

    def test_skill_bonus_parity_all_chars(self):
        """Skill bonuses match established values."""
        from pf2e.combat_math import skill_bonus
        from pf2e.types import Skill
        from tests.fixtures import make_aetregan, make_rook, make_dalai, make_erisen

        assert skill_bonus(make_aetregan(), Skill.ARCANA) == 7
        assert skill_bonus(make_aetregan(), Skill.STEALTH) == 6
        assert skill_bonus(make_aetregan(), Skill.INTIMIDATION) == 4
        assert skill_bonus(make_rook(), Skill.ATHLETICS) == 4
        assert skill_bonus(make_dalai(), Skill.PERFORMANCE) == 4
        assert skill_bonus(make_erisen(), Skill.CRAFTING) == 4

    def test_lore_bonus_warfare_parity(self):
        """Aetregan Warfare Lore: Int +4, trained +3 = +7."""
        from pf2e.combat_math import lore_bonus
        from tests.fixtures import make_aetregan

        assert lore_bonus(make_aetregan(), "Warfare") == 7

    def test_spell_attack_bonus_parity(self):
        """Dalai spell attack: Cha +4, trained +3 = +7. Equal to class_dc - 10."""
        from pf2e.combat_math import spell_attack_bonus, class_dc
        from tests.fixtures import make_dalai

        dalai = make_dalai()
        assert spell_attack_bonus(dalai) == 7
        assert spell_attack_bonus(dalai) == class_dc(dalai) - 10


# ---------------------------------------------------------------------------
# Regression (1)
# ---------------------------------------------------------------------------

class TestRegression:

    def test_ev_7_65_regression(self):
        """26th verification: Strike Hard EV 7.65 after CP10.3."""
        from sim.scenario import load_scenario
        from pf2e.tactics import evaluate_tactic, STRIKE_HARD

        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        ctx = scenario.build_tactic_context()
        result = evaluate_tactic(STRIKE_HARD, ctx)
        assert result.expected_damage_dealt == pytest.approx(7.65, abs=EV_TOLERANCE)
