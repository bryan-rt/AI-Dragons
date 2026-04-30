"""NPCData — pre-calculated combat stats for NPC/creature enemies.

Stores Foundry-derived totals and exposes override hooks for combat_math.
Character (PC) never implements these hooks; getattr returns None for PCs,
triggering the standard derivation path unchanged.
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2187)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pf2e.abilities import AbilityScores
from pf2e.detection import VisionType
from pf2e.equipment import ArmorData, EquippedWeapon, Shield
from pf2e.types import (
    Ability, ProficiencyRank, SaveType, Skill, WeaponCategory,
)


@dataclass(frozen=True)
class NPCData:
    """Pre-calculated NPC combat data, duck-type compatible with Character.

    Override hooks (npc_*) are checked via getattr() in combat_math.py.
    PC Character objects lack these methods, so getattr returns None
    and the standard derivation path runs unchanged.
    """
    # Identity
    name: str
    level: int
    speed: int

    # Ability scores — synthetic from modifiers (mod * 2 + 10)
    abilities: AbilityScores

    # Equipment — _extract_weapons() parses same format as PCs
    equipped_weapons: tuple[EquippedWeapon, ...] = ()
    armor: ArmorData | None = None
    shield: Shield | None = None

    # Pre-calculated totals (populated from Foundry NPC JSON)
    _attack_totals: dict[str, int] = field(default_factory=dict)
    _ac_total: int = 10
    _save_totals: dict[SaveType, int] = field(default_factory=dict)
    _perception_total: int = 0
    _skill_totals: dict[Skill, int] = field(default_factory=dict)
    _spell_dc: int = 0
    _spell_attack_total: int = 0
    _max_hp: int = 0

    # Spells and resources
    known_spells: dict[str, int] = field(default_factory=dict)

    # Vision and immunities
    vision_type: VisionType = VisionType.NORMAL
    immunity_tags: frozenset[str] = field(default_factory=frozenset)

    # Feature flags — all False for NPCs
    has_shield_block: bool = False
    has_plant_banner: bool = False
    has_deceptive_tactics: bool = False
    has_lengthy_diversion: bool = False
    has_commander_banner: bool = False
    has_courageous_anthem: bool = False
    has_soothe: bool = False
    has_light_mortar: bool = False
    has_taunt: bool = False
    weapon_specialization: bool = False
    greater_weapon_spec: bool = False
    guardian_reactions: int = 0

    # Proficiency scaffolding — TRAINED defaults satisfy any code
    # that reads proficiency fields without calling override hooks
    key_ability: Ability = Ability.STR
    weapon_proficiencies: dict[WeaponCategory, ProficiencyRank] = field(
        default_factory=lambda: {
            WeaponCategory.SIMPLE: ProficiencyRank.TRAINED,
            WeaponCategory.MARTIAL: ProficiencyRank.TRAINED,
            WeaponCategory.ADVANCED: ProficiencyRank.TRAINED,
            WeaponCategory.UNARMED: ProficiencyRank.TRAINED,
        }
    )
    armor_proficiency: ProficiencyRank = ProficiencyRank.TRAINED
    perception_rank: ProficiencyRank = ProficiencyRank.TRAINED
    save_ranks: dict[SaveType, ProficiencyRank] = field(
        default_factory=lambda: {
            SaveType.FORTITUDE: ProficiencyRank.TRAINED,
            SaveType.REFLEX: ProficiencyRank.TRAINED,
            SaveType.WILL: ProficiencyRank.TRAINED,
        }
    )
    class_dc_rank: ProficiencyRank = ProficiencyRank.TRAINED
    skill_proficiencies: dict[Skill, ProficiencyRank] = field(
        default_factory=dict)

    # Inert PC fields — satisfies field-access patterns
    extra_damage_bonuses: tuple[tuple[str, float], ...] = ()
    lores: dict[str, ProficiencyRank] = field(default_factory=dict)
    initially_held: tuple[str, ...] = ()
    starting_resources: dict[str, int] = field(default_factory=dict)
    ancestry_hp: int = 0
    class_hp: int = 0

    # -------------------------------------------------------------------
    # Override hooks — checked via getattr(char, 'npc_X', None)
    # -------------------------------------------------------------------

    def npc_attack_total(self, weapon_name: str) -> int | None:
        """Pre-calculated attack bonus for weapon by name."""
        return self._attack_totals.get(weapon_name)

    def npc_ac_total(self) -> int | None:
        """Pre-calculated AC total."""
        return self._ac_total

    def npc_save_total(self, save: SaveType) -> int | None:
        """Pre-calculated save bonus."""
        return self._save_totals.get(save)

    def npc_perception_total(self) -> int | None:
        """Pre-calculated perception bonus."""
        return self._perception_total

    def npc_skill_total(self, skill: Skill) -> int | None:
        """Pre-calculated skill bonus."""
        return self._skill_totals.get(skill)

    def npc_class_dc(self) -> int | None:
        """Pre-calculated spell DC (None if non-caster)."""
        return self._spell_dc if self._spell_dc > 0 else None

    def npc_spell_attack(self) -> int | None:
        """Pre-calculated spell attack bonus (None if non-caster)."""
        return self._spell_attack_total if self._spell_attack_total > 0 else None

    def npc_max_hp(self) -> int | None:
        """Pre-calculated max HP."""
        return self._max_hp if self._max_hp > 0 else None
