"""Combat math derivation functions.

Every function in this module computes a combat number from character
data + context. Nothing is pre-baked. This is the core rules engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from pf2e.abilities import AbilityScores
from pf2e.character import Character, CombatantState
from pf2e.equipment import EquippedWeapon, Weapon
from pf2e.proficiency import proficiency_bonus
from pf2e.types import Ability, ProficiencyRank, SaveType


# ---------------------------------------------------------------------------
# Helper: die average
# ---------------------------------------------------------------------------

def die_average(die: str) -> float:
    """Expected value of a single die roll: (sides + 1) / 2.

    >>> die_average("d6")
    3.5
    >>> die_average("d8")
    4.5
    """
    sides = int(die[1:])
    return (sides + 1) / 2


# ---------------------------------------------------------------------------
# Attack ability and bonus
# ---------------------------------------------------------------------------

def attack_ability(
    character: Character, weapon: Weapon, thrown: bool = False,
) -> Ability:
    """Which ability score drives the attack roll for this character + weapon.

    - Pure ranged (not a thrown-melee weapon): Dex
      (AoN: https://2e.aonprd.com/Rules.aspx?ID=2187)
    - Thrown-melee weapon being thrown (thrown=True): Dex
      (AoN: https://2e.aonprd.com/Traits.aspx?ID=195)
    - Thrown-melee weapon used in melee (thrown=False): finesse or Str
    - Finesse melee: higher of Str or Dex
      (AoN: https://2e.aonprd.com/Traits.aspx?ID=548)
    - Other melee: Str

    Args:
        thrown: True if the weapon is being thrown (ranged attack).
            A dagger used in melee should pass thrown=False and use
            finesse rules instead.
    """
    if thrown or (weapon.is_ranged and not weapon.is_thrown):
        return Ability.DEX
    if weapon.is_finesse:
        str_mod = character.abilities.mod(Ability.STR)
        dex_mod = character.abilities.mod(Ability.DEX)
        return Ability.DEX if dex_mod >= str_mod else Ability.STR
    return Ability.STR


def attack_bonus(
    state: CombatantState,
    equipped: EquippedWeapon,
    map_penalty: int = 0,
    thrown: bool = False,
) -> int:
    """Total attack bonus for a Strike.

    ability mod + proficiency + item (potency) + MAP + frightened + status bonus.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2187)
    """
    char = state.character
    weapon = equipped.weapon
    ability = attack_ability(char, weapon, thrown=thrown)
    ability_mod = char.abilities.mod(ability)
    prof = proficiency_bonus(
        char.weapon_proficiencies[weapon.category],
        char.level,
    )
    item_bonus = equipped.potency_bonus
    frightened_penalty = -state.frightened
    status_bonus = state.status_bonus_attack
    return ability_mod + prof + item_bonus + map_penalty + frightened_penalty + status_bonus


# ---------------------------------------------------------------------------
# Damage ability and average
# ---------------------------------------------------------------------------

def damage_ability_mod(
    character: Character, weapon: Weapon, thrown: bool = False,
) -> int:
    """Integer damage bonus from ability scores.

    - Melee (not throwing): full Str mod
    - Thrown (when actually throwing): full Str mod
    - Propulsive: half Str mod (rounded down if positive, full if negative)
    - Pure ranged: 0

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2189)
    """
    str_mod = character.abilities.mod(Ability.STR)
    if not thrown and weapon.is_melee:
        return str_mod
    if thrown:
        return str_mod
    if weapon.is_propulsive:
        return str_mod // 2 if str_mod >= 0 else str_mod
    return 0


def weapon_spec_damage(character: Character) -> int:
    """Flat damage bonus from weapon specialization.

    Returns 0 if the character doesn't have weapon specialization.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2191)

    Weapon specialization (level 7+): +2 per damage die.
    Greater weapon specialization (level 15+): +4 per damage die.
    (UNVERIFIED — please confirm: the actual values depend on
    proficiency rank, not flat per-die. Simplified for now as:
    trained/expert = +2, master = +3, legendary = +4.
    Greater doubles these.)
    """
    if not character.weapon_specialization:
        return 0
    # Simplified: return 2 for normal, 4 for greater.
    # Full implementation would check highest weapon proficiency rank.
    if character.greater_weapon_spec:
        return 4
    return 2


def damage_avg(
    state: CombatantState,
    equipped: EquippedWeapon,
    extra_dice: int = 0,
    extra_flat: int = 0,
    thrown: bool = False,
) -> float:
    """Expected damage ON HIT (before hit probability weighting).

    dice × die_average + ability mod + weapon spec + precision + status + extra.
    Frightened does NOT apply to damage rolls (damage rolls are not checks).
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=42)
    """
    char = state.character
    weapon = equipped.weapon
    total_dice = equipped.total_damage_dice + extra_dice
    dice_damage = total_dice * die_average(weapon.damage_die)
    ability_damage = damage_ability_mod(char, weapon, thrown=thrown)
    spec_damage = weapon_spec_damage(char)
    precision = sum(v for _, v in char.extra_damage_bonuses)
    status_damage = state.status_bonus_damage
    return dice_damage + ability_damage + spec_damage + precision + status_damage + extra_flat


# ---------------------------------------------------------------------------
# AC, saves, class DC, perception
# ---------------------------------------------------------------------------

def armor_class(state: CombatantState) -> int:
    """Compute AC from character build + transient combat state.

    10 + Dex (capped by armor) + prof + item (armor) + shield (if raised)
    - off-guard penalty - frightened penalty.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2140)
    """
    char = state.character
    dex_mod = char.abilities.mod(Ability.DEX)
    if char.armor and char.armor.dex_cap is not None:
        dex_mod = min(dex_mod, char.armor.dex_cap)
    prof = proficiency_bonus(char.armor_proficiency, char.level)
    item_bonus = char.armor.ac_bonus if char.armor else 0
    shield_bonus = (
        char.shield.ac_bonus if (char.shield and state.shield_raised) else 0
    )
    off_guard_penalty = -2 if state.off_guard else 0
    frightened_penalty = -state.frightened  # AC is a DC; frightened applies
    return (
        10 + dex_mod + prof + item_bonus + shield_bonus
        + off_guard_penalty + frightened_penalty
    )


def class_dc(character: Character) -> int:
    """Class DC = 10 + key ability mod + proficiency.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2139)
    """
    ability_mod = character.abilities.mod(character.key_ability)
    prof = proficiency_bonus(character.class_dc_rank, character.level)
    return 10 + ability_mod + prof


def siege_save_dc(operator: Character) -> int:
    """Save DC for an Inventor's siege weapon innovation.

    Equals the operator's class DC, overriding the weapon's base item DC.
    (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4)
    """
    return class_dc(operator)


def save_bonus(character: Character, save: SaveType) -> int:
    """Total saving throw bonus = ability mod + proficiency.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2131)
    """
    ability_map = {
        SaveType.FORTITUDE: Ability.CON,
        SaveType.REFLEX: Ability.DEX,
        SaveType.WILL: Ability.WIS,
    }
    ability_mod = character.abilities.mod(ability_map[save])
    prof = proficiency_bonus(character.save_ranks[save], character.level)
    return ability_mod + prof


def perception_bonus(character: Character) -> int:
    """Perception bonus = Wis mod + proficiency.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2130)
    """
    wis_mod = character.abilities.mod(Ability.WIS)
    prof = proficiency_bonus(character.perception_rank, character.level)
    return wis_mod + prof


# ---------------------------------------------------------------------------
# Multiple Attack Penalty
# ---------------------------------------------------------------------------

def map_penalty(attack_number: int, agile: bool) -> int:
    """Multiple attack penalty for the Nth attack in a turn (1-indexed).

    Standard: 0 / -5 / -10
    Agile:    0 / -4 / -8

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=220)
    """
    if attack_number <= 1:
        return 0
    step = -4 if agile else -5
    return step * min(attack_number - 1, 2)


# ---------------------------------------------------------------------------
# d20 outcome enumeration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class D20Outcomes:
    """Count of d20 faces producing each degree of success.

    Fields sum to 20 (one per d20 face).
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2194)
    """
    critical_success: int
    success: int
    failure: int
    critical_failure: int


def enumerate_d20_outcomes(bonus: int, dc: int) -> D20Outcomes:
    """Count d20 faces producing each degree of success.

    Applies nat 1 downgrade and nat 20 upgrade rules.

    Args:
        bonus: Total modifier added to the d20 roll.
        dc: The target DC (AC for attacks, save DC for saves).

    Returns:
        D20Outcomes with face counts summing to 20.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2194)
    """
    crit_success = 0
    success = 0
    failure = 0
    crit_failure = 0

    for roll in range(1, 21):
        total = roll + bonus

        # Determine base degree of success
        if total >= dc + 10:
            degree = 3  # crit success
        elif total >= dc:
            degree = 2  # success
        elif total <= dc - 10:
            degree = 0  # crit failure
        else:
            degree = 1  # failure

        # Nat 20 upgrades one step (AoN: https://2e.aonprd.com/Rules.aspx?ID=2194)
        if roll == 20:
            degree = min(degree + 1, 3)
        # Nat 1 downgrades one step
        elif roll == 1:
            degree = max(degree - 1, 0)

        if degree == 3:
            crit_success += 1
        elif degree == 2:
            success += 1
        elif degree == 1:
            failure += 1
        else:
            crit_failure += 1

    return D20Outcomes(crit_success, success, failure, crit_failure)


# ---------------------------------------------------------------------------
# Expected Strike damage
# ---------------------------------------------------------------------------

def expected_strike_damage(
    attacker: CombatantState,
    equipped: EquippedWeapon,
    target_ac: int,
    attack_number: int = 1,
    is_reaction: bool = False,
    off_guard: bool = False,
    extra_dice: int = 0,
    extra_flat: int = 0,
    thrown: bool = False,
) -> float:
    """Expected damage of a single Strike, fully weighted by hit probability.

    Reaction Strikes are always at MAP 0 regardless of attack_number.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=220)

    Off-guard reduces effective AC by 2.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=58)

    Args:
        attacker: The attacking combatant's state.
        equipped: The weapon being used.
        target_ac: The target's AC before off-guard.
        attack_number: Which attack this is (1st, 2nd, 3rd) for MAP.
        is_reaction: If True, MAP is forced to 0.
        off_guard: If True, target AC is reduced by 2.
        extra_dice: Additional damage dice (e.g., from tactics).
        extra_flat: Additional flat damage bonus.
        thrown: If True, weapon is being thrown (Dex for attack, Str for damage).
    """
    effective_ac = target_ac - (2 if off_guard else 0)
    effective_map = (
        0 if is_reaction
        else map_penalty(attack_number, equipped.weapon.is_agile)
    )
    bonus = attack_bonus(attacker, equipped, effective_map, thrown=thrown)

    outcomes = enumerate_d20_outcomes(bonus, effective_ac)

    hit_dmg = damage_avg(
        attacker, equipped,
        extra_dice=extra_dice, extra_flat=extra_flat, thrown=thrown,
    )

    # Critical hit damage: double the base damage
    # Plus deadly die if weapon has the deadly trait
    # (AoN: https://2e.aonprd.com/Traits.aspx?ID=424)
    deadly = equipped.weapon.deadly_die
    deadly_extra = die_average(deadly) if deadly else 0.0
    crit_dmg = hit_dmg * 2 + deadly_extra

    return (
        (outcomes.success / 20) * hit_dmg
        + (outcomes.critical_success / 20) * crit_dmg
    )


# ---------------------------------------------------------------------------
# Siege weapon (mortar) AoE expected damage
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SiegeWeapon:
    """A siege weapon innovation (e.g., Inventor's Light Mortar).

    Uses saves instead of attack rolls, targets an area.
    (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4)
    """
    name: str
    damage_die: str
    base_damage_dice: int                 # dice count at level 1
    damage_type: DamageType
    save_type: SaveType
    aoe_shape: str                        # "burst"
    aoe_radius_ft: int                    # 10 at level 1
    range_increment: int                  # 120 ft

    def dice_at_level(self, level: int) -> int:
        """Total damage dice at a given character level.

        +1 die at levels 5, 9, 13, 17.
        (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4)
        """
        extra = max(0, (level - 1) // 4)
        return self.base_damage_dice + extra


@dataclass(frozen=True)
class EnemyTarget:
    """Minimal enemy data needed for EV calculations."""
    name: str
    ac: int
    saves: dict[SaveType, int]


def expected_aoe_damage(
    operator: Character,
    siege: SiegeWeapon,
    targets: list[EnemyTarget],
) -> float:
    """Expected damage from a save-based AoE against multiple targets.

    Uses basic save rules: crit fail = double, fail = full,
    success = half, crit success = 0.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2195)
    """
    dc = siege_save_dc(operator)
    dice = siege.dice_at_level(operator.level)
    base_dmg = dice * die_average(siege.damage_die)

    total = 0.0
    for target in targets:
        save_mod = target.saves[siege.save_type]
        outcomes = enumerate_d20_outcomes(save_mod, dc)

        # For saves, the d20 outcomes are from the DEFENDER's perspective:
        # crit success (for defender) = 0 damage
        # success (for defender) = half damage
        # failure (for defender) = full damage
        # crit failure (for defender) = double damage
        target_ev = (
            (outcomes.critical_failure / 20) * base_dmg * 2
            + (outcomes.failure / 20) * base_dmg
            + (outcomes.success / 20) * base_dmg * 0.5
            + (outcomes.critical_success / 20) * 0
        )
        total += target_ev

    return total
