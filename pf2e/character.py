"""Character and combatant state models.

Character is frozen (immutable) — it represents a character's build.
CombatantState wraps a Character with mutable per-round combat state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pf2e.abilities import AbilityScores
from pf2e.equipment import ArmorData, EquippedWeapon, Shield
from pf2e.types import Ability, ProficiencyRank, SaveType, WeaponCategory


@dataclass(frozen=True)
class Character:
    """A PF2e character's build — all the data needed to derive combat numbers.

    All combat stats (AC, attack bonus, save bonus, class DC, etc.) are
    computed from these fields by functions in combat_math.py, never
    stored as pre-computed values.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2100)
    """
    name: str
    level: int
    abilities: AbilityScores
    key_ability: Ability

    # Proficiency ranks — bonuses are derived via proficiency_bonus()
    weapon_proficiencies: dict[WeaponCategory, ProficiencyRank]
    armor_proficiency: ProficiencyRank
    perception_rank: ProficiencyRank
    save_ranks: dict[SaveType, ProficiencyRank]
    class_dc_rank: ProficiencyRank

    # Equipment
    equipped_weapons: tuple[EquippedWeapon, ...]
    armor: ArmorData | None = None
    shield: Shield | None = None

    # Class features
    weapon_specialization: bool = False
    greater_weapon_spec: bool = False
    has_shield_block: bool = False
    guardian_reactions: int = 0            # 0 for non-guardians

    # Extra damage sources (label, average value), e.g., sneak attack
    extra_damage_bonuses: tuple[tuple[str, float], ...] = ()

    # Base speed in feet, from ancestry + feats (not armor/conditions).
    # Default 25 ft; Elves get 30, Nimble Elf adds +5, etc.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)
    speed: int = 25


@dataclass
class CombatantState:
    """Mutable per-round combat state wrapping an immutable Character.

    Created fresh for each tactic evaluation. The Character underneath
    never changes; only the transient state does.
    """
    character: Character
    position: tuple[int, int] = (0, 0)

    # Reaction tracking
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2432)
    reactions_available: int = 1
    guardian_reactions_available: int = 0
    drilled_reaction_available: bool = False

    # Shield state
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2180)
    shield_raised: bool = False

    # Conditions — flat fields, not a ConditionSet
    # (AoN: https://2e.aonprd.com/Conditions.aspx?ID=58)
    off_guard: bool = False
    # (AoN: https://2e.aonprd.com/Conditions.aspx?ID=42)
    frightened: int = 0
    prone: bool = False

    # Current speed, if modified by armor or conditions.
    # None = use character.speed as-is.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2153)
    current_speed: int | None = None

    # Status bonuses (e.g., Courageous Anthem +1)
    # (AoN: https://2e.aonprd.com/Spells.aspx?ID=1763)
    status_bonus_attack: int = 0
    status_bonus_damage: int = 0

    @classmethod
    def from_character(
        cls,
        char: Character,
        position: tuple[int, int] = (0, 0),
        anthem_active: bool = False,
    ) -> CombatantState:
        """Create a fresh CombatantState from a Character.

        Args:
            char: The immutable character build.
            position: Grid position (row, col).
            anthem_active: If True, apply Courageous Anthem +1 status
                bonus to attack and damage rolls.
                (AoN: https://2e.aonprd.com/Spells.aspx?ID=1763)
        """
        return cls(
            character=char,
            position=position,
            guardian_reactions_available=char.guardian_reactions,
            status_bonus_attack=1 if anthem_active else 0,
            status_bonus_damage=1 if anthem_active else 0,
        )
