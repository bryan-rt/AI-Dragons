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


class SaveType(Enum):
    """The three saving throw types.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2131)
    """
    FORTITUDE = auto()
    REFLEX = auto()
    WILL = auto()
