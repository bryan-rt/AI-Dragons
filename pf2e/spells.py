"""Spell definitions and chassis for parameterized spell evaluation.

Each SpellDefinition describes a spell's mechanical parameters. The
evaluate_spell() dispatcher in pf2e/actions.py uses these to compute
EV without needing a bespoke evaluator per spell.

AoN-verified: all spell data cross-referenced against Archives of Nethys.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from pf2e.types import DamageType, SaveType


class SpellPattern(Enum):
    """Which chassis evaluator handles this spell."""
    SAVE_FOR_DAMAGE = auto()    # Basic save → half/full/double damage
    AUTO_HIT_DAMAGE = auto()    # No roll, flat damage (Force Barrage)
    SAVE_OR_CONDITION = auto()  # Non-basic save → condition per degree
    ATTACK_ROLL = auto()        # Spell attack vs AC (Needle Darts)
    BUFF_AURA = auto()          # Already handled (Anthem pattern)
    HEAL = auto()               # Already handled (Soothe pattern)


@dataclass(frozen=True)
class SpellDefinition:
    """Parameterized description of a combat spell's mechanics.

    Drives the spell chassis evaluator. One instance per spell.
    Complex spells (summons, walls, etc.) get bespoke evaluators instead.
    """
    name: str
    slug: str
    aon_url: str
    action_cost: int             # Base action cost (1-3)
    rank: int                    # Spell rank (0 = cantrip, 1-10)
    pattern: SpellPattern
    traits: frozenset[str]
    range_ft: int                # 0 for touch/self

    # For damage patterns (1, 2, 4):
    damage_dice: int = 0
    damage_die: str = "d4"
    damage_bonus: int = 0
    damage_type: DamageType | None = None
    save_type: SaveType | None = None
    is_basic_save: bool = True

    # For multi-action scaling (Force Barrage):
    scales_with_actions: bool = False
    missiles_per_action: int = 1

    # For condition patterns (Fear):
    # Tuple of (degree_label, condition_name, condition_value)
    condition_by_degree: tuple[tuple[str, str, int], ...] = ()

    # Persistent bleed on critical hit (Needle Darts)
    # (AoN: https://2e.aonprd.com/Spells.aspx?ID=1375)
    crit_persistent_bleed: int = 0

    # Spell slot resource tracking (Phase C stub)
    uses_spell_slot: bool = True   # False for cantrips/focus
    spell_slot_rank: int = 1


# ---------------------------------------------------------------------------
# Spell Registry — AoN-verified definitions
# ---------------------------------------------------------------------------

SPELL_REGISTRY: dict[str, SpellDefinition] = {
    "fear": SpellDefinition(
        name="Fear",
        slug="fear",
        aon_url="https://2e.aonprd.com/Spells.aspx?ID=1524",
        action_cost=2,
        rank=1,
        pattern=SpellPattern.SAVE_OR_CONDITION,
        traits=frozenset({"enchantment", "fear", "mental"}),
        range_ft=30,
        save_type=SaveType.WILL,
        is_basic_save=False,
        condition_by_degree=(
            ("crit_success",         "",           0),
            ("success",              "frightened", 1),
            ("failure",              "frightened", 2),
            ("crit_failure",         "frightened", 3),
            ("crit_failure_fleeing", "fleeing",    1),
        ),
        uses_spell_slot=True,
        spell_slot_rank=1,
    ),
    "force-barrage": SpellDefinition(
        name="Force Barrage",
        slug="force-barrage",
        aon_url="https://2e.aonprd.com/Spells.aspx?ID=1536",
        action_cost=1,
        rank=1,
        pattern=SpellPattern.AUTO_HIT_DAMAGE,
        traits=frozenset({"evocation", "force"}),
        range_ft=120,
        damage_dice=1,
        damage_die="d4",
        damage_bonus=1,
        damage_type=DamageType.FORCE,
        scales_with_actions=True,
        missiles_per_action=1,
        uses_spell_slot=True,
        spell_slot_rank=1,
    ),
    "needle-darts": SpellDefinition(
        name="Needle Darts",
        slug="needle-darts",
        aon_url="https://2e.aonprd.com/Spells.aspx?ID=1375",
        action_cost=2,
        rank=0,  # Cantrip
        pattern=SpellPattern.ATTACK_ROLL,
        traits=frozenset({"attack", "cantrip", "concentrate", "manipulate", "metal"}),
        range_ft=60,
        damage_dice=3,
        damage_die="d4",
        damage_bonus=0,
        damage_type=DamageType.PIERCING,
        save_type=None,
        is_basic_save=False,
        crit_persistent_bleed=1,  # 1 persistent bleed on crit hit
        scales_with_actions=False,
        uses_spell_slot=False,  # Cantrip — unlimited
        spell_slot_rank=0,
    ),
}
