"""Core enums and value types for PF2e Remaster rules.

No logic, no dependencies — pure type definitions.
"""

from enum import Enum, auto


class Ability(Enum):
    """The six ability scores.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2100)
    """
    STR = auto()
    DEX = auto()
    CON = auto()
    INT = auto()
    WIS = auto()
    CHA = auto()


class ProficiencyRank(Enum):
    """Proficiency rank, with the rank bonus as the value.

    The total proficiency bonus is rank.value + character level
    (except untrained, which is always 0).
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2136)
    """
    UNTRAINED = 0
    TRAINED = 2
    EXPERT = 4
    MASTER = 6
    LEGENDARY = 8


class WeaponCategory(Enum):
    """Weapon proficiency category.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2176)
    """
    UNARMED = auto()
    SIMPLE = auto()
    MARTIAL = auto()
    ADVANCED = auto()


class WeaponGroup(Enum):
    """Weapon group for critical specialization effects.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2191)
    """
    AXE = auto()
    SWORD = auto()
    KNIFE = auto()
    BRAWLING = auto()
    FLAIL = auto()
    FIREARM = auto()
    BOMB = auto()
    POLEARM = auto()
    PICK = auto()
    HAMMER = auto()
    CLUB = auto()
    SPEAR = auto()
    DART = auto()
    BOW = auto()
    SLING = auto()
    SHIELD = auto()


class DamageType(Enum):
    """Damage types relevant to the simulator.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2197)
    """
    BLUDGEONING = auto()
    PIERCING = auto()
    SLASHING = auto()
    FIRE = auto()
    COLD = auto()
    ELECTRICITY = auto()
    ACID = auto()
    FORCE = auto()


class SaveType(Enum):
    """The three saving throw types.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2131)
    """
    FORTITUDE = auto()
    REFLEX = auto()
    WILL = auto()


class Skill(Enum):
    """The sixteen standard skills.

    Lores are tracked separately on Character.lores as a dict since
    they're arbitrary character-specific strings (Warfare Lore, etc.).
    (AoN: https://2e.aonprd.com/Skills.aspx)
    """
    ACROBATICS = auto()
    ARCANA = auto()
    ATHLETICS = auto()
    CRAFTING = auto()
    DECEPTION = auto()
    DIPLOMACY = auto()
    INTIMIDATION = auto()
    MEDICINE = auto()
    NATURE = auto()
    OCCULTISM = auto()
    PERFORMANCE = auto()
    RELIGION = auto()
    SOCIETY = auto()
    STEALTH = auto()
    SURVIVAL = auto()
    THIEVERY = auto()


SKILL_ABILITY: dict[Skill, Ability] = {
    Skill.ACROBATICS: Ability.DEX,
    Skill.ARCANA: Ability.INT,
    Skill.ATHLETICS: Ability.STR,
    Skill.CRAFTING: Ability.INT,
    Skill.DECEPTION: Ability.CHA,
    Skill.DIPLOMACY: Ability.CHA,
    Skill.INTIMIDATION: Ability.CHA,
    Skill.MEDICINE: Ability.WIS,
    Skill.NATURE: Ability.WIS,
    Skill.OCCULTISM: Ability.INT,
    Skill.PERFORMANCE: Ability.CHA,
    Skill.RELIGION: Ability.WIS,
    Skill.SOCIETY: Ability.INT,
    Skill.STEALTH: Ability.DEX,
    Skill.SURVIVAL: Ability.WIS,
    Skill.THIEVERY: Ability.DEX,
}
