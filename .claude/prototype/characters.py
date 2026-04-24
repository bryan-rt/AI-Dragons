"""
Character definitions and combat math for PF2e tactical simulator.
All damage calcs use expected value (hit% × dmg + crit% × 2*dmg) for "best play" analysis.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Strike:
    """A single attack a character can make."""
    name: str
    attack_bonus: int       # total to-hit modifier
    damage_dice: str        # e.g. "1d8+4"
    damage_avg: float       # pre-computed average damage
    reach: int = 5          # in feet
    is_ranged: bool = False
    range_increment: int = 0  # 0 = melee
    traits: List[str] = field(default_factory=list)  # "agile", "finesse", etc.


@dataclass
class Character:
    name: str
    role: str               # "commander", "ally", "enemy"
    pos: tuple              # (row, col) on grid
    speed: int              # in feet
    ac: int
    hp: int
    max_hp: int
    perception: int
    fort: int
    refl: int
    will: int
    strikes: List[Strike] = field(default_factory=list)
    is_squadmate: bool = False  # responds to commander tactics
    notes: str = ""

    def distance_to(self, other) -> int:
        """Chebyshev distance in feet (PF2e diagonal = 1 square)."""
        dr = abs(self.pos[0] - other.pos[0])
        dc = abs(self.pos[1] - other.pos[1])
        return max(dr, dc) * 5

    def squares_to(self, other) -> int:
        return self.distance_to(other) // 5


def expected_strike_damage(attack_bonus: int, target_ac: int,
                           damage_avg: float, off_guard: bool = False,
                           map_penalty: int = 0) -> float:
    """
    Expected damage from one Strike.
    crit on natural 20 OR beating AC by 10. crit fail on natural 1 OR missing by 10.
    Off-guard = -2 AC. MAP applies to attack roll.
    """
    effective_ac = target_ac - (2 if off_guard else 0)
    needed = effective_ac - attack_bonus + map_penalty  # roll needed to hit

    # Roll on d20: 1 always misses, 20 always hits.
    # Hit probability (success or crit, not crit-fail)
    if needed <= 1:
        # auto-hit on anything except nat 1
        hit_chance = 19 / 20
    elif needed >= 21:
        # only nat 20 hits (and nat 20 = upgrade by 1 step from miss to success)
        hit_chance = 1 / 20
    else:
        hit_chance = (21 - needed) / 20  # rolls of `needed` through 20

    # Crit: beat AC by 10+. Or nat 20 if it would be a hit.
    crit_needed = needed + 10
    if crit_needed <= 1:
        crit_chance = 19 / 20  # virtually always crit
    elif crit_needed >= 21:
        crit_chance = 1 / 20 if needed <= 20 else 0  # nat 20 upgrades hit→crit
    else:
        crit_chance = (21 - crit_needed) / 20

    # nat 20 upgrades: if attack would normally just hit (not crit), nat 20 makes it crit
    # this is already factored: rolling 20 is in both hit_chance and the upgrade is
    # captured by crit_chance representing "this roll value or higher crits"

    regular_hit_chance = max(0, hit_chance - crit_chance)
    return regular_hit_chance * damage_avg + crit_chance * 2 * damage_avg


def expected_aoe_damage(damage_avg: float, save_bonus: int, dc: int) -> float:
    """Basic Reflex save: crit save = 0, save = half, fail = full, crit fail = double."""
    needed = dc - save_bonus
    if needed <= 1:
        save_chance = 19 / 20
    elif needed >= 21:
        save_chance = 1 / 20
    else:
        save_chance = (21 - needed) / 20

    crit_save_needed = needed + 10
    if crit_save_needed <= 1:
        crit_save_chance = 19 / 20
    elif crit_save_needed >= 21:
        crit_save_chance = 1 / 20 if needed <= 20 else 0
    else:
        crit_save_chance = (21 - crit_save_needed) / 20

    fail_needed = needed - 10
    if fail_needed <= 1:
        fail_chance = 0  # can't crit fail unless you roll way under
    elif fail_needed >= 21:
        fail_chance = 19 / 20  # almost always crit fail
    else:
        fail_chance = (fail_needed - 1) / 20

    regular_save = max(0, save_chance - crit_save_chance)
    crit_fail = fail_chance
    fail = max(0, 1 - save_chance - crit_fail)

    return (crit_save_chance * 0
            + regular_save * damage_avg / 2
            + fail * damage_avg
            + crit_fail * 2 * damage_avg)


# --- Default party at level 1 (your campaign) ---

def make_aetregan(pos=(2, 5)) -> Character:
    """Commander, level 1. Whip for reach trip + flank."""
    whip = Strike(name="Whip", attack_bonus=5, damage_dice="1d4",
                  damage_avg=2.5, reach=10,
                  traits=["finesse", "trip", "disarm", "nonlethal"])
    return Character(
        name="Aetregan", role="commander", pos=pos, speed=30,
        ac=18, hp=16, max_hp=16, perception=4,
        fort=4, refl=7, will=5,
        strikes=[whip], is_squadmate=True,
        notes="Banner-bearer. Class DC 17 (10+4 Int+2 trained+1 level)."
    )


def make_rook(pos=(2, 2)) -> Character:
    """Guardian Automaton, level 1. Longsword + steel shield."""
    longsword = Strike(name="Longsword", attack_bonus=7, damage_dice="1d8+4",
                       damage_avg=8.5, reach=5, traits=["versatile P"])
    return Character(
        name="Rook", role="ally", pos=pos, speed=25,
        ac=18, hp=22, max_hp=22, perception=3,
        fort=8, refl=4, will=5,
        strikes=[longsword], is_squadmate=True,
        notes="Heavy armor automaton, frontline tank."
    )


def make_dalai(pos=(5, 4)) -> Character:
    """Bard Warrior Muse, level 1. Rapier + Hymn of Healing focus spell."""
    rapier = Strike(name="Rapier", attack_bonus=5, damage_dice="1d6",
                    damage_avg=3.5, reach=5,
                    traits=["finesse", "deadly d8", "disarm"])
    return Character(
        name="Dalai", role="ally", pos=pos, speed=25,
        ac=16, hp=16, max_hp=16, perception=5,
        fort=3, refl=5, will=7,
        strikes=[rapier], is_squadmate=True,
        notes="Occult caster. Composition cantrips. Hymn of Healing."
    )


def make_erisen(pos=(7, 4)) -> Character:
    """Inventor (Munitions Master), level 1. Light mortar."""
    # Mortar isn't a normal Strike — handled separately as AoE
    # Erisen's personal weapon: maybe a dagger or unarmed
    dagger = Strike(name="Dagger", attack_bonus=5, damage_dice="1d4+0",
                    damage_avg=2.5, reach=5,
                    traits=["finesse", "agile", "thrown 10ft"])
    return Character(
        name="Erisen", role="ally", pos=pos, speed=30,
        ac=17, hp=18, max_hp=18, perception=3,
        fort=6, refl=6, will=3,
        strikes=[dagger], is_squadmate=True,
        notes="Light mortar: 2d6 bludg, 10ft burst, DC 17 basic Reflex. "
              "Needs Deploy + Aim + Load + Launch action sequence."
    )


# --- Generic enemy templates ---

def make_minion(pos, name="Minion") -> Character:
    """Level 0-1 mook. AC 15, HP 12, Reflex +5."""
    club = Strike(name="Club", attack_bonus=5, damage_dice="1d6+2",
                  damage_avg=5.5, reach=5)
    return Character(
        name=name, role="enemy", pos=pos, speed=25,
        ac=15, hp=12, max_hp=12, perception=5,
        fort=5, refl=5, will=3,
        strikes=[club]
    )


def make_brute(pos, name="Brute") -> Character:
    """Level 2-3 tougher enemy. AC 17, HP 28."""
    greatsword = Strike(name="Greatsword", attack_bonus=8, damage_dice="1d12+4",
                        damage_avg=10.5, reach=5)
    return Character(
        name=name, role="enemy", pos=pos, speed=25,
        ac=17, hp=28, max_hp=28, perception=6,
        fort=8, refl=5, will=5,
        strikes=[greatsword]
    )
