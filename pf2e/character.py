"""Character and combatant state models.

Character is frozen (immutable) — it represents a character's build.
CombatantState wraps a Character with mutable per-round combat state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pf2e.abilities import AbilityScores
from pf2e.equipment import ArmorData, EquippedWeapon, Shield
from pf2e.types import Ability, ProficiencyRank, SaveType, Skill, WeaponCategory


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

    # Max HP components — default 0 for backward compatibility.
    # Characters with tracked HP must set both.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2145)
    ancestry_hp: int = 0
    class_hp: int = 0

    # Skill proficiencies — missing keys default to UNTRAINED.
    # (AoN: https://2e.aonprd.com/Skills.aspx)
    skill_proficiencies: dict[Skill, ProficiencyRank] = field(default_factory=dict)

    # Lore proficiencies — arbitrary character-specific strings.
    # (AoN: https://2e.aonprd.com/Skills.aspx?ID=47)
    lores: dict[str, ProficiencyRank] = field(default_factory=dict)

    # Feat-presence flags for feats that affect action evaluator logic.
    has_plant_banner: bool = False
    has_deceptive_tactics: bool = False
    has_lengthy_diversion: bool = False
    # Commander class feature: can carry/plant a war banner and activate tactics.
    # (AoN: https://2e.aonprd.com/Classes.aspx?ID=66)
    has_commander_banner: bool = False
    # CP5.2 class feature flags
    has_courageous_anthem: bool = False  # Bard cantrip (AoN: Spells — Courageous Anthem)
    has_soothe: bool = False             # Occult spell slot (AoN: Spells — Soothe)
    has_light_mortar: bool = False       # Inventor innovation (AoN: Innovations ID=4)
    has_taunt: bool = False              # Guardian class feature (AoN: Actions ID=3304)

    # Known combat spells (slug → rank). Populated by importer from SPELL_REGISTRY.
    # Rank 0 = cantrip (unlimited), rank 1+ = spell slot required.
    known_spells: dict[str, int] = field(default_factory=dict)

    # Hand state at combat start — weapon/shield names currently held.
    # Derived from Foundry handsHeld > 0. Max 2 hands total.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2149)
    initially_held: tuple[str, ...] = ()

    # Starting expendable resources per encounter.
    # Maps resource_key → quantity. E.g. {"spell_slot_1": 2}.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2224 — Spontaneous spells)
    starting_resources: dict[str, int] = field(default_factory=dict)

    # Trait-based immunity tags. Actions whose traits have a matching
    # immunity_tag in TRAIT_REGISTRY are blocked against this character.
    # Empty for most PCs. Automaton Constructed Body waives construct
    # immunities, so Rook has frozenset() — no immunity tags.
    # (AoN: https://2e.aonprd.com/Ancestries.aspx?ID=48)
    immunity_tags: frozenset[str] = field(default_factory=frozenset)


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

    # HP tracking (CP5.1). current_hp=None means "at full HP".
    current_hp: int | None = None
    temp_hp: int = 0

    # Action economy for the current turn (reset per turn by search)
    actions_remaining: int = 3

    @property
    def effective_current_hp(self) -> int:
        """Current HP with None treated as max."""
        from pf2e.combat_math import max_hp
        if self.current_hp is None:
            return max_hp(self.character)
        return self.current_hp

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


@dataclass
class EnemyState:
    """Enemy combatant with position, conditions, and offensive profile.

    Used in tactic evaluation and spatial queries. Offensive stats
    (attack_bonus, damage_dice, etc.) are optional — empty damage_dice
    means the enemy has no modeled offensive capability.
    """
    name: str
    ac: int
    saves: dict[SaveType, int]
    position: tuple[int, int]
    off_guard: bool = False
    prone: bool = False
    # Offensive stats for defensive EV computation (Checkpoint 4)
    attack_bonus: int = 0
    damage_dice: str = ""          # e.g., "1d8"; empty = no modeled offense
    damage_bonus: int = 0
    num_attacks_per_turn: int = 2

    # HP tracking (CP5.1)
    max_hp: int = 20              # plausible L1 bandit default
    current_hp: int | None = None

    # Perception for initiative and skill-check DCs
    perception_bonus: int = 4     # plausible L1 enemy default

    # Action economy
    actions_remaining: int = 3

    # Damage type modifiers (CP5.3). Keys are lowercase damage type names.
    # (AoN: https://2e.aonprd.com/Rules.aspx?ID=2309)
    weaknesses: dict[str, int] = field(default_factory=dict)
    resistances: dict[str, int] = field(default_factory=dict)

    @property
    def perception_dc(self) -> int:
        """DC for Deception/Stealth checks against this enemy."""
        return 10 + self.perception_bonus

    @property
    def effective_current_hp(self) -> int:
        """Current HP with None treated as max."""
        if self.current_hp is None:
            return self.max_hp
        return self.current_hp
