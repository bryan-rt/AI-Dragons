"""Weapon, armor, and shield data models.

All dataclasses are frozen — equipment doesn't mutate during play.
Runes and modifications are composed at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pf2e.types import DamageType, WeaponCategory, WeaponGroup


# ---------------------------------------------------------------------------
# Weapons
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Weapon:
    """Intrinsic properties of a weapon type (no runes, no wielder).

    Traits are stored as a frozenset of lowercase strings matching AoN
    trait names: "finesse", "agile", "reach", "trip", "disarm",
    "nonlethal", "thrown_10", "deadly_d8", "propulsive", "versatile_p",
    "versatile_s", etc.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2176)
    """
    name: str
    category: WeaponCategory
    group: WeaponGroup
    damage_die: str                       # "d4", "d6", "d8", etc.
    damage_die_count: int                 # usually 1 (base)
    damage_type: DamageType
    range_increment: int | None           # None = melee only
    traits: frozenset[str]                # {"finesse", "agile", ...}
    hands: int                            # 1 or 2

    @property
    def is_melee(self) -> bool:
        """True if this weapon can be used in melee.

        A weapon is melee if it has no range increment (pure melee) OR
        if it has the thrown trait (thrown weapons are melee weapons that
        can also be thrown — they appear in the Melee Weapons table).

        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2176)
        (AoN: https://2e.aonprd.com/Traits.aspx?ID=195)
        """
        return self.range_increment is None or self.is_thrown

    @property
    def is_ranged(self) -> bool:
        """True if this weapon can attack at range (has a range increment).

        Includes both pure ranged weapons (bows, firearms) and
        thrown-trait melee weapons that have a range increment.

        (AoN: https://2e.aonprd.com/Rules.aspx?ID=2176)
        """
        return self.range_increment is not None

    @property
    def is_finesse(self) -> bool:
        """(AoN: https://2e.aonprd.com/Traits.aspx?ID=548)"""
        return "finesse" in self.traits

    @property
    def is_agile(self) -> bool:
        """(AoN: https://2e.aonprd.com/Traits.aspx?ID=404)"""
        return "agile" in self.traits

    @property
    def is_thrown(self) -> bool:
        """True if the weapon has any thrown_N trait.

        (AoN: https://2e.aonprd.com/Traits.aspx?ID=195)
        """
        return any(t.startswith("thrown") for t in self.traits)

    @property
    def is_propulsive(self) -> bool:
        """(AoN: https://2e.aonprd.com/Traits.aspx?ID=154)"""
        return "propulsive" in self.traits

    @property
    def deadly_die(self) -> str | None:
        """Return the deadly die size (e.g. "d8") or None.

        (AoN: https://2e.aonprd.com/Traits.aspx?ID=424)
        """
        for t in self.traits:
            if t.startswith("deadly_"):
                return t.split("_", 1)[1]
        return None


@dataclass(frozen=True)
class WeaponRunes:
    """Runes applied to a specific weapon instance.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2277)
    """
    potency: int = 0                      # +1/+2/+3 item bonus to attack
    striking: int = 0                     # 0/1/2/3 extra damage dice
    property_runes: tuple[str, ...] = ()  # "flaming", "shock", etc.


@dataclass(frozen=True)
class EquippedWeapon:
    """A specific weapon with runes — what a character holds.

    Combines intrinsic weapon properties with rune enhancements.
    """
    weapon: Weapon
    runes: WeaponRunes = field(default_factory=WeaponRunes)

    @property
    def potency_bonus(self) -> int:
        """Item bonus to attack rolls from potency rune."""
        return self.runes.potency

    @property
    def total_damage_dice(self) -> int:
        """Total number of damage dice (base + striking rune)."""
        return self.weapon.damage_die_count + self.runes.striking


# ---------------------------------------------------------------------------
# Armor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArmorData:
    """Armor properties.

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2168)
    """
    name: str
    ac_bonus: int                         # item bonus to AC
    dex_cap: int | None                   # None = no cap (unarmored)
    check_penalty: int = 0
    speed_penalty: int = 0
    strength_threshold: int = 0           # Str score needed to ignore check penalty


# ---------------------------------------------------------------------------
# Shields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Shield:
    """Shield properties.

    (AoN: https://2e.aonprd.com/Shields.aspx?ID=3)
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2180)
    """
    name: str
    ac_bonus: int                         # +2 for steel shield
    hardness: int                         # damage absorbed by Shield Block
    hp: int                               # total hit points
    bt: int                               # broken threshold
