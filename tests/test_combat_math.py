"""Tests for combat math derivation functions.

Validates every number in the Pass 2.5 Section A.3 validation targets.
All tolerances are ±0.01 unless otherwise noted.
"""

import pytest

from pf2e.character import CombatantState
from pf2e.combat_math import (
    D20Outcomes,
    EnemyTarget,
    SiegeWeapon,
    armor_class,
    attack_ability,
    attack_bonus,
    class_dc,
    damage_ability_mod,
    damage_avg,
    die_average,
    effective_speed,
    enumerate_d20_outcomes,
    expected_aoe_damage,
    expected_strike_damage,
    map_penalty,
    perception_bonus,
    save_bonus,
    siege_save_dc,
)
from pf2e.equipment import EquippedWeapon
from pf2e.types import Ability, DamageType, SaveType
from tests.fixtures import (
    DAGGER,
    LONGSWORD,
    RAPIER,
    WHIP,
    make_aetregan,
    make_dalai,
    make_erisen,
    make_rook,
)

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def aetregan_state() -> CombatantState:
    return CombatantState.from_character(make_aetregan())


@pytest.fixture
def aetregan_anthem_state() -> CombatantState:
    return CombatantState.from_character(make_aetregan(), anthem_active=True)


@pytest.fixture
def rook_state() -> CombatantState:
    return CombatantState.from_character(make_rook())


@pytest.fixture
def dalai_state() -> CombatantState:
    return CombatantState.from_character(make_dalai())


@pytest.fixture
def erisen_state() -> CombatantState:
    return CombatantState.from_character(make_erisen())


LIGHT_MORTAR = SiegeWeapon(
    name="Light Mortar",
    damage_die="d6",
    base_damage_dice=2,
    damage_type=DamageType.BLUDGEONING,
    save_type=SaveType.REFLEX,
    aoe_shape="burst",
    aoe_radius_ft=10,
    range_increment=120,
)


# ---------------------------------------------------------------------------
# die_average
# ---------------------------------------------------------------------------

class TestDieAverage:
    def test_d4(self) -> None:
        assert die_average("d4") == 2.5

    def test_d6(self) -> None:
        assert die_average("d6") == 3.5

    def test_d8(self) -> None:
        assert die_average("d8") == 4.5

    def test_d10(self) -> None:
        assert die_average("d10") == 5.5

    def test_d12(self) -> None:
        assert die_average("d12") == 6.5


# ---------------------------------------------------------------------------
# MAP
# ---------------------------------------------------------------------------

class TestMapPenalty:
    """(AoN: https://2e.aonprd.com/Rules.aspx?ID=220)"""

    def test_standard_map(self) -> None:
        assert map_penalty(1, agile=False) == 0
        assert map_penalty(2, agile=False) == -5
        assert map_penalty(3, agile=False) == -10
        assert map_penalty(4, agile=False) == -10  # caps at 3rd

    def test_agile_map(self) -> None:
        assert map_penalty(1, agile=True) == 0
        assert map_penalty(2, agile=True) == -4
        assert map_penalty(3, agile=True) == -8
        assert map_penalty(4, agile=True) == -8


# ---------------------------------------------------------------------------
# d20 enumeration
# ---------------------------------------------------------------------------

class TestD20Enumeration:
    """Validate the d20 face-counting logic with nat 1/20 rules."""

    def test_outcomes_sum_to_20(self) -> None:
        for bonus in range(-5, 30):
            for dc in range(5, 35):
                o = enumerate_d20_outcomes(bonus, dc)
                total = (
                    o.critical_success + o.success + o.failure + o.critical_failure
                )
                assert total == 20, f"bonus={bonus}, dc={dc}: sum={total}"

    def test_rook_vs_ac15(self) -> None:
        """Rook +7 vs AC 15: hit on 8+, crit on 18+."""
        o = enumerate_d20_outcomes(7, 15)
        # Roll 1: total 8, fail (8<15), nat1 → crit fail
        # Rolls 2-7: totals 9-14, fail (6 faces)
        # Rolls 8-17: totals 15-24, success (10 faces)
        # Rolls 18-19: totals 25-26, crit success (2 faces)
        # Roll 20: total 27, crit success, nat20 stays crit (1 face)
        assert o.critical_failure == 1
        assert o.failure == 6
        assert o.success == 10
        assert o.critical_success == 3

    def test_aetregan_vs_ac15(self) -> None:
        """Aetregan +6 vs AC 15: hit on 9+, crit on nat 20 only."""
        o = enumerate_d20_outcomes(6, 15)
        # Roll 1: total 7, fail, nat1 → crit fail
        # Rolls 2-8: totals 8-14, fail (7 faces)
        # Rolls 9-19: totals 15-25. Roll 19: total 25, >= 25 → crit (1 face)
        #   Rolls 9-18: totals 15-24, success (10 faces)
        # Roll 20: total 26, crit. nat20 stays crit (1 face)
        assert o.critical_failure == 1
        assert o.failure == 7
        assert o.success == 10
        assert o.critical_success == 2

    def test_nat20_upgrades_failure_to_success(self) -> None:
        """With a very low bonus, nat 20 should upgrade failure to success."""
        # bonus -10, DC 15: roll 20 → total 10 → failure, nat20 → success
        o = enumerate_d20_outcomes(-10, 15)
        assert o.success >= 1  # at least the nat 20

    def test_nat1_downgrades_success_to_failure(self) -> None:
        """With a very high bonus, nat 1 should downgrade success to failure."""
        # bonus +20, DC 15: roll 1 → total 21 → success, nat1 → failure
        o = enumerate_d20_outcomes(20, 15)
        assert o.failure >= 1  # at least the nat 1


# ---------------------------------------------------------------------------
# attack_ability
# ---------------------------------------------------------------------------

class TestAttackAbility:

    def test_str_melee(self) -> None:
        """Longsword (no finesse) uses Str."""
        assert attack_ability(make_rook(), LONGSWORD) == Ability.STR

    def test_finesse_uses_higher(self) -> None:
        """Whip (finesse): Aetregan has Dex 16 > Str 10, so Dex."""
        assert attack_ability(make_aetregan(), WHIP) == Ability.DEX

    def test_finesse_uses_str_when_higher(self) -> None:
        """Rapier (finesse): Rook has Str 18 > Dex 10, so Str."""
        assert attack_ability(make_rook(), RAPIER) == Ability.STR

    def test_thrown_uses_dex(self) -> None:
        """Dagger (thrown_10): uses Dex for ranged attack when thrown."""
        assert attack_ability(make_erisen(), DAGGER, thrown=True) == Ability.DEX

    def test_dagger_melee_uses_finesse(self) -> None:
        """Dagger in melee mode uses finesse (higher of Str/Dex)."""
        # Erisen: Dex +2, Str +0 → finesse picks Dex
        assert attack_ability(make_erisen(), DAGGER, thrown=False) == Ability.DEX
        # Rook: Str +4, Dex +0 → finesse picks Str
        assert attack_ability(make_rook(), DAGGER, thrown=False) == Ability.STR


# ---------------------------------------------------------------------------
# damage_ability_mod
# ---------------------------------------------------------------------------

class TestDamageAbilityMod:

    def test_melee_uses_str(self) -> None:
        """Melee weapons always use Str for damage."""
        assert damage_ability_mod(make_rook(), LONGSWORD) == 4   # Str 18 → +4
        assert damage_ability_mod(make_aetregan(), WHIP) == 0    # Str 10 → +0

    def test_thrown_uses_str(self) -> None:
        """Thrown weapons use Str for damage when thrown."""
        assert damage_ability_mod(make_erisen(), DAGGER, thrown=True) == 0  # Str 10 → +0

    def test_dagger_melee_uses_str(self) -> None:
        """Dagger in melee mode uses Str for damage (it's melee)."""
        assert damage_ability_mod(make_erisen(), DAGGER, thrown=False) == 0
        assert damage_ability_mod(make_rook(), DAGGER, thrown=False) == 4


# ---------------------------------------------------------------------------
# Class DC — all PCs = 17 at level 1
# ---------------------------------------------------------------------------

class TestClassDC:

    def test_aetregan_dc(self) -> None:
        """10 + Int 4 + trained 3 = 17."""
        assert class_dc(make_aetregan()) == 17

    def test_rook_dc(self) -> None:
        """10 + Str 4 + trained 3 = 17."""
        assert class_dc(make_rook()) == 17

    def test_dalai_dc(self) -> None:
        """10 + Cha 4 + trained 3 = 17."""
        assert class_dc(make_dalai()) == 17

    def test_erisen_dc(self) -> None:
        """10 + Int 4 + trained 3 = 17."""
        assert class_dc(make_erisen()) == 17


# ---------------------------------------------------------------------------
# Siege save DC
# ---------------------------------------------------------------------------

class TestSiegeSaveDC:

    def test_mortar_dc(self) -> None:
        """Erisen mortar DC = class DC = 17."""
        assert siege_save_dc(make_erisen()) == 17


# ---------------------------------------------------------------------------
# AC
# ---------------------------------------------------------------------------

class TestArmorClass:

    def test_aetregan_ac_no_shield(self, aetregan_state: CombatantState) -> None:
        """10 + Dex 3 + trained medium 3 + suit 2 = 18."""
        assert armor_class(aetregan_state) == 18

    def test_aetregan_ac_shield_raised(self, aetregan_state: CombatantState) -> None:
        """18 + shield 2 = 20."""
        aetregan_state.shield_raised = True
        assert armor_class(aetregan_state) == 20

    def test_rook_ac_no_shield(self, rook_state: CombatantState) -> None:
        """10 + Dex 0 (cap 0) + trained heavy 3 + full plate 6 = 19."""
        assert armor_class(rook_state) == 19

    def test_rook_ac_shield_raised(self, rook_state: CombatantState) -> None:
        """19 + shield 2 = 21."""
        rook_state.shield_raised = True
        assert armor_class(rook_state) == 21

    def test_dalai_ac(self, dalai_state: CombatantState) -> None:
        """10 + Dex 2 + trained light 3 + leather 1 = 16."""
        assert armor_class(dalai_state) == 16

    def test_erisen_ac(self, erisen_state: CombatantState) -> None:
        """10 + Dex 2 + trained 3 + leather 1 = 16 (Foundry: Leather Armor)."""
        assert armor_class(erisen_state) == 16


# ---------------------------------------------------------------------------
# Save bonuses
# ---------------------------------------------------------------------------

class TestSaveBonuses:

    def test_aetregan_saves(self) -> None:
        """Aetregan: Fort +4, Ref +8, Will +5.

        Foundry: Wis 10 → mod +0 (was Wis 12 in old factory). JSON authoritative.
        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2110)
        """
        c = make_aetregan()
        assert save_bonus(c, SaveType.FORTITUDE) == 4   # Con +1, trained +3
        assert save_bonus(c, SaveType.REFLEX) == 8      # Dex +3, expert +5
        assert save_bonus(c, SaveType.WILL) == 5        # Wis +0, expert +5

    def test_rook_saves(self) -> None:
        """Rook: Fort +8, Ref +3, Will +6."""
        c = make_rook()
        assert save_bonus(c, SaveType.FORTITUDE) == 8   # Con +3, expert +5
        assert save_bonus(c, SaveType.REFLEX) == 3      # Dex +0, trained +3
        assert save_bonus(c, SaveType.WILL) == 6        # Wis +1, expert +5

    def test_dalai_saves(self) -> None:
        """Dalai: Fort +4, Ref +5, Will +5.

        DISCREPANCY: Brief A.3 says Ref +6 and Will +6. But:
        - Ref: Dex 14 → +2, trained +3 = 5 (not 6).
        - Will: Wis 10 → +0, expert +5 = 5 (not 6).
        Derivation from ability scores is the ground truth.
        """
        c = make_dalai()
        assert save_bonus(c, SaveType.FORTITUDE) == 4   # Con +1, trained +3
        assert save_bonus(c, SaveType.REFLEX) == 5      # Dex +2, trained +3
        assert save_bonus(c, SaveType.WILL) == 5        # Wis +0, expert +5

    def test_erisen_saves(self) -> None:
        """Erisen: Fort +7, Ref +5, Will +5 (Foundry: Ref trained, Will expert)."""
        c = make_erisen()
        assert save_bonus(c, SaveType.FORTITUDE) == 7   # Con +2, expert +5
        assert save_bonus(c, SaveType.REFLEX) == 5      # Dex +2, trained +3
        assert save_bonus(c, SaveType.WILL) == 5        # Wis +0, expert +5


# ---------------------------------------------------------------------------
# Expected Strike Damage — validation targets from A.3
# ---------------------------------------------------------------------------

class TestExpectedStrikeDamage:

    def test_rook_longsword_vs_ac15(self, rook_state: CombatantState) -> None:
        """Rook longsword: +7 vs AC 15, 1d8+4 (8.5 avg), EV = 6.80."""
        eq = EquippedWeapon(LONGSWORD)
        ev = expected_strike_damage(rook_state, eq, target_ac=15)
        assert ev == pytest.approx(6.80, abs=EV_TOLERANCE)

    def test_aetregan_whip_vs_ac15_no_anthem(
        self, aetregan_state: CombatantState,
    ) -> None:
        """Aetregan whip: +6 vs AC 15, 1d4+0 (2.5 avg), EV = 1.75."""
        eq = EquippedWeapon(WHIP)
        ev = expected_strike_damage(aetregan_state, eq, target_ac=15)
        assert ev == pytest.approx(1.75, abs=EV_TOLERANCE)

    def test_aetregan_whip_vs_ac15_with_anthem(
        self, aetregan_anthem_state: CombatantState,
    ) -> None:
        """Aetregan whip + Anthem: +7 vs AC 15, 1d4+0+1 (3.5 avg).

        d20 enumeration with +7 vs AC 15:
        Crits: rolls 18,19,20 → 3/20. Hits: rolls 8-17 → 10/20.
        EV = (10/20)×3.5 + (3/20)×7.0 = 1.75 + 1.05 = 2.80
        """
        eq = EquippedWeapon(WHIP)
        ev = expected_strike_damage(aetregan_anthem_state, eq, target_ac=15)
        assert ev == pytest.approx(2.80, abs=EV_TOLERANCE)

    def test_dalai_rapier_vs_ac15(self, dalai_state: CombatantState) -> None:
        """Dalai rapier: +5 vs AC 15, 1d6+0 (3.5 avg), deadly d8.

        d20 enumeration with +5 vs AC 15:
        Roll 1: total 6, fail → nat1 crit fail.
        Rolls 2-9: totals 7-14, fail (8 faces).
        Rolls 10-19: totals 15-24, success (10 faces).
        Roll 20: total 25 ≥ 25 → crit, nat20 confirms (1 face).
        Crits: 1/20. Hits: 10/20.
        Hit dmg: 3.5. Crit dmg: 3.5×2 + 4.5 (deadly d8) = 11.5.
        EV = (10/20)×3.5 + (1/20)×11.5 = 1.75 + 0.575 = 2.325
        """
        eq = EquippedWeapon(RAPIER)
        ev = expected_strike_damage(dalai_state, eq, target_ac=15)
        assert ev == pytest.approx(2.325, abs=EV_TOLERANCE)

    def test_erisen_dagger_vs_ac15(self, erisen_state: CombatantState) -> None:
        """Erisen dagger (melee finesse): +5 vs AC 15, 1d4+0 (2.5 avg).

        Same d20 distribution as Dalai (+5 vs AC 15) but no deadly die.
        Hits: 10/20. Crits: 1/20.
        Hit dmg: 2.5. Crit dmg: 5.0.
        EV = (10/20)×2.5 + (1/20)×5.0 = 1.25 + 0.25 = 1.50
        """
        eq = EquippedWeapon(DAGGER)
        ev = expected_strike_damage(erisen_state, eq, target_ac=15)
        assert ev == pytest.approx(1.50, abs=EV_TOLERANCE)


# ---------------------------------------------------------------------------
# Off-guard
# ---------------------------------------------------------------------------

class TestOffGuard:

    def test_off_guard_reduces_effective_ac(
        self, rook_state: CombatantState,
    ) -> None:
        """Off-guard = -2 AC → higher EV."""
        eq = EquippedWeapon(LONGSWORD)
        ev_normal = expected_strike_damage(rook_state, eq, target_ac=15)
        ev_offguard = expected_strike_damage(
            rook_state, eq, target_ac=15, off_guard=True,
        )
        assert ev_offguard > ev_normal

    def test_off_guard_exact(self, rook_state: CombatantState) -> None:
        """Off-guard vs AC 15 = effectively vs AC 13.

        +7 vs AC 13: hit on 6+, crit on 16+.
        Roll 1: total 8, fail? 8>=13 → success. Nat1 → failure. Miss.
        Rolls 2-5: totals 9-12, fail? 9>=13? No → fail (4 faces).
        Wait, +7 vs AC 13:
        Roll 1: 1+7=8. 8>=13? No → fail. 8<=3? No → fail. Nat1 → crit fail.
        Rolls 2-5: totals 9-12. All <13 → fail. (4 faces)
        Rolls 6-15: totals 13-22. All >=13, <23 → success. (10 faces)
        Rolls 16-19: totals 23-26. 23>=23? 13+10=23. So >=23 → crit. (4 faces)
        Roll 20: total 27 → crit. Nat20 stays crit. (1 face)

        Hits: 10. Crits: 5.
        EV = (10/20)×8.5 + (5/20)×17.0 = 4.25 + 4.25 = 8.50
        """
        eq = EquippedWeapon(LONGSWORD)
        ev = expected_strike_damage(
            rook_state, eq, target_ac=15, off_guard=True,
        )
        assert ev == pytest.approx(8.50, abs=EV_TOLERANCE)


# ---------------------------------------------------------------------------
# Reaction Strike (MAP 0 regardless of attack_number)
# ---------------------------------------------------------------------------

class TestReactionStrike:

    def test_reaction_ignores_map(self, rook_state: CombatantState) -> None:
        """A reaction Strike is always MAP 0, even if attack_number > 1."""
        eq = EquippedWeapon(LONGSWORD)
        ev_first = expected_strike_damage(rook_state, eq, target_ac=15)
        ev_reaction_4th = expected_strike_damage(
            rook_state, eq, target_ac=15, attack_number=4, is_reaction=True,
        )
        assert ev_reaction_4th == pytest.approx(ev_first, abs=EV_TOLERANCE)

    def test_non_reaction_has_map(self, rook_state: CombatantState) -> None:
        """A normal 3rd attack at -10 MAP should be much lower EV."""
        eq = EquippedWeapon(LONGSWORD)
        ev_first = expected_strike_damage(rook_state, eq, target_ac=15)
        ev_third = expected_strike_damage(
            rook_state, eq, target_ac=15, attack_number=3,
        )
        assert ev_third < ev_first


# ---------------------------------------------------------------------------
# Frightened
# ---------------------------------------------------------------------------

class TestFrightened:

    def test_frightened_reduces_attack(self, rook_state: CombatantState) -> None:
        """Frightened 2 → -2 to attack rolls (checks)."""
        eq = EquippedWeapon(LONGSWORD)
        ev_normal = expected_strike_damage(rook_state, eq, target_ac=15)
        rook_state.frightened = 2
        ev_frightened = expected_strike_damage(rook_state, eq, target_ac=15)
        assert ev_frightened < ev_normal

    def test_frightened_reduces_ac(self, rook_state: CombatantState) -> None:
        """Frightened 2 → -2 to AC (AC is a DC)."""
        ac_normal = armor_class(rook_state)
        rook_state.frightened = 2
        ac_frightened = armor_class(rook_state)
        assert ac_frightened == ac_normal - 2

    def test_frightened_does_not_reduce_damage(
        self, rook_state: CombatantState,
    ) -> None:
        """Frightened does NOT apply to damage rolls (not checks)."""
        eq = EquippedWeapon(LONGSWORD)
        dmg_normal = damage_avg(rook_state, eq)
        rook_state.frightened = 2
        dmg_frightened = damage_avg(rook_state, eq)
        assert dmg_frightened == dmg_normal


# ---------------------------------------------------------------------------
# Mortar AoE — validation targets from A.3
# ---------------------------------------------------------------------------

class TestMortarAoE:

    def test_mortar_ev_single_target(self) -> None:
        """Mortar 2d6 DC 17 vs Reflex +5: EV = 5.95 per target.

        DISCREPANCY from brief's target of 5.60: The brief's hand
        calculation undercounted crit failures. With save +5 vs DC 17:
        - DC - 10 = 7. Rolls 1-2 → totals 6-7 → both ≤ 7 → crit fail.
          Roll 1: nat 1, already crit fail. Roll 2: total 7 ≤ 7, crit fail.
        - Rolls 3-11: totals 8-16, failure (9 faces).
        - Rolls 12-19: totals 17-24, success (8 faces).
        - Roll 20: total 25, success → nat 20 upgrades to crit success (1 face).

        EV = (2/20)×14 + (9/20)×7 + (8/20)×3.5 + (1/20)×0 = 5.95

        The brief incorrectly had only 1 crit failure (roll 1) and 10
        failures. The correct count is 2 crit failures and 9 failures,
        because total 7 = DC-10 satisfies the ≤ DC-10 threshold for
        crit failure.
        """
        erisen = make_erisen()
        target = EnemyTarget(
            name="Minion",
            ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        )
        ev = expected_aoe_damage(erisen, LIGHT_MORTAR, [target])
        assert ev == pytest.approx(5.95, abs=EV_TOLERANCE)

    def test_mortar_ev_two_targets(self) -> None:
        """Mortar 2d6 DC 17 vs 2 targets, each Reflex +5: EV = 11.90.

        See single-target test for derivation. 5.95 × 2 = 11.90.
        """
        erisen = make_erisen()
        target = EnemyTarget(
            name="Minion",
            ac=15,
            saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        )
        ev = expected_aoe_damage(erisen, LIGHT_MORTAR, [target, target])
        assert ev == pytest.approx(11.90, abs=EV_TOLERANCE)


# ---------------------------------------------------------------------------
# Mortar damage scaling by level
# ---------------------------------------------------------------------------

class TestMortarScaling:

    def test_dice_at_level_1(self) -> None:
        assert LIGHT_MORTAR.dice_at_level(1) == 2

    def test_dice_at_level_5(self) -> None:
        assert LIGHT_MORTAR.dice_at_level(5) == 3

    def test_dice_at_level_9(self) -> None:
        assert LIGHT_MORTAR.dice_at_level(9) == 4

    def test_dice_at_level_13(self) -> None:
        assert LIGHT_MORTAR.dice_at_level(13) == 5

    def test_dice_at_level_17(self) -> None:
        assert LIGHT_MORTAR.dice_at_level(17) == 6


# ---------------------------------------------------------------------------
# Perception bonus
# ---------------------------------------------------------------------------

class TestPerception:

    def test_aetregan_perception(self) -> None:
        """Wis 10 → mod +0, expert +5 = +5 (Foundry: Wis 10, JSON authoritative).

        Commander has expert Perception at L1.
        (AoN: https://2e.aonprd.com/Classes.aspx?ID=66)
        """
        assert perception_bonus(make_aetregan()) == 5

    def test_rook_perception(self) -> None:
        """Wis +1, trained +3 = +4 (Foundry: Guardian perception trained)."""
        assert perception_bonus(make_rook()) == 4


# ---------------------------------------------------------------------------
# Effective speed
# ---------------------------------------------------------------------------

class TestEffectiveSpeed:

    def test_default_uses_character_speed(self) -> None:
        """Aetregan (Elf): base speed 30 ft."""
        state = CombatantState.from_character(make_aetregan())
        assert effective_speed(state) == 30

    def test_current_speed_override(self) -> None:
        """Rook in full plate: current_speed=20 overrides base 25."""
        state = CombatantState.from_character(make_rook())
        state.current_speed = 20
        assert effective_speed(state) == 20

    def test_erisen_nimble_elf(self) -> None:
        """Erisen (Elf + Nimble Elf): base 35 ft."""
        state = CombatantState.from_character(make_erisen())
        assert effective_speed(state) == 35

    def test_dalai_human_base(self) -> None:
        """Dalai (Human): base 25 ft."""
        state = CombatantState.from_character(make_dalai())
        assert effective_speed(state) == 25
