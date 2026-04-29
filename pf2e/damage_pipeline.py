"""Strict PF2e damage resolution pipeline.

Order: Intercept Attack (redirect) → Shield Block (hardness absorb)
→ Resistance (Guardian's Armor) → Temp HP → Real HP.

This module resolves a specific damage amount through the full pipeline.
EV composition happens at the search level by weighting outcomes.

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2301 — Damage Rolls)
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2309 — Immunities/Weaknesses/Resistances)
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2321 — Temporary Hit Points)
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2180 — Shield Block)
(AoN: https://2e.aonprd.com/Actions.aspx?ID=3305 — Intercept Attack)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pf2e.combat_math import guardians_armor_resistance

if TYPE_CHECKING:
    from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReactionChoices:
    """Which reactions fire on this damage resolution.

    Both fields default to None (no reaction). Set by the search tree
    at reaction decision points; see CP5.1.3b Pass 2 plan section C2.
    """
    intercept_by: str | None = None
    shield_block_by: str | None = None


@dataclass(frozen=True)
class StrikeResolution:
    """Result of resolving one Strike outcome through the damage pipeline.

    target_name is the combatant who ultimately takes the damage
    (different from the original target if intercepted).
    """
    target_name: str
    damage_to_hp: float
    damage_to_temp_hp: float
    shield_damage: float
    shield_hardness_absorbed: float
    resistance_absorbed: float
    intercepted: bool
    interceptor_name: str
    reactions_consumed: dict[str, str] = field(default_factory=dict)


def resolve_strike_outcome(
    damage: float,
    target_name: str,
    state: RoundState,
    reactions: ReactionChoices,
    is_physical: bool = True,
) -> StrikeResolution:
    """Resolve a damage amount through the PF2e pipeline.

    Order: Intercept Attack (redirect) → Shield Block (hardness absorb)
    → Resistance → Temp HP → Real HP.

    Interpretive choice: Shield Block before Resistance. Both reduce
    incoming damage before it hits HP. Shield Block is an active choice
    that reduces raw damage; resistance then operates on the remainder.
    This maximizes Shield Block utility.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2180 — Shield Block)
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2309 — Resistance)

    Args:
        damage: Raw damage amount (non-negative).
        target_name: The original target of the attack.
        state: Current RoundState for looking up combatants.
        reactions: Which reactions the search has chosen to fire.
        is_physical: True for physical damage. Guardian's Armor only
            resists physical damage.
    """
    reactions_consumed: dict[str, str] = {}
    intercepted = False
    interceptor_name = ""
    effective_target = target_name

    # Step 1: Intercept Attack (redirect to interceptor)
    if reactions.intercept_by is not None:
        intercepted = True
        interceptor_name = reactions.intercept_by
        effective_target = reactions.intercept_by
        reactions_consumed[reactions.intercept_by] = "guardian"

    # Resolve which snapshot receives damage
    receiver = state.pcs.get(effective_target) or state.enemies.get(effective_target)
    if receiver is None:
        raise KeyError(f"No combatant named {effective_target!r}")

    remaining = damage
    shield_damage = 0.0
    shield_hardness_absorbed = 0.0
    resistance_absorbed = 0.0

    # Step 2: Shield Block (absorb up to Hardness)
    if reactions.shield_block_by is not None:
        blocker_name = reactions.shield_block_by
        blocker = state.pcs.get(blocker_name)
        if blocker is None or blocker.character.shield is None:
            raise ValueError(
                f"Shield Block by {blocker_name!r} requires a PC with a shield"
            )
        hardness = blocker.character.shield.hardness
        absorbed = min(float(hardness), remaining)
        shield_hardness_absorbed = absorbed
        remaining -= absorbed
        # Shield takes the remaining damage that passed through
        shield_damage = remaining
        reactions_consumed[blocker_name] = "general"

    # Step 3: Resistance (Guardian's Armor — physical only)
    if is_physical and hasattr(receiver, "character"):
        char = receiver.character  # type: ignore[union-attr]
        if (char.guardian_reactions > 0
                and char.armor is not None
                and char.armor.ac_bonus >= 4):
            resistance = guardians_armor_resistance(char.level)
            absorbed = min(float(resistance), remaining)
            resistance_absorbed = absorbed
            remaining -= absorbed

    # Step 4: Temp HP absorbs first
    damage_to_temp_hp = 0.0
    if hasattr(receiver, "temp_hp") and receiver.temp_hp > 0:
        absorbed = min(float(receiver.temp_hp), remaining)
        damage_to_temp_hp = absorbed
        remaining -= absorbed

    # Step 5: Real HP
    damage_to_hp = max(0.0, remaining)

    logger.debug(
        f"resolve_strike_outcome: damage={damage:.1f}, "
        f"target={target_name}->{effective_target}, "
        f"intercepted={intercepted}, shield={shield_hardness_absorbed:.1f}, "
        f"resistance={resistance_absorbed:.1f}, "
        f"temp_hp={damage_to_temp_hp:.1f}, hp={damage_to_hp:.1f}"
    )

    return StrikeResolution(
        target_name=effective_target,
        damage_to_hp=damage_to_hp,
        damage_to_temp_hp=damage_to_temp_hp,
        shield_damage=shield_damage,
        shield_hardness_absorbed=shield_hardness_absorbed,
        resistance_absorbed=resistance_absorbed,
        intercepted=intercepted,
        interceptor_name=interceptor_name,
        reactions_consumed=reactions_consumed,
    )


# ---------------------------------------------------------------------------
# Persistent damage (CP10.8)
# ---------------------------------------------------------------------------


def _parse_persistent_tags(
    conditions: frozenset[str],
) -> list[tuple[str, int]]:
    """Extract (damage_type, amount) from "persistent_TYPE_N" tags.

    Returns sorted by damage_type for deterministic order.
    """
    results = []
    for c in conditions:
        if c.startswith("persistent_"):
            parts = c.split("_", 2)
            if len(parts) == 3:
                try:
                    results.append((parts[1], int(parts[2])))
                except ValueError:
                    continue
    return sorted(results)


def merge_persistent_tag(
    existing: frozenset[str], new_tag: str,
) -> frozenset[str]:
    """Apply 'take higher' stacking rule for persistent damage tags.

    Same-type persistent damage doesn't stack — keep the higher value.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=29)
    """
    if not new_tag.startswith("persistent_"):
        return existing | {new_tag}
    parts = new_tag.split("_", 2)
    if len(parts) != 3:
        return existing | {new_tag}
    damage_type = parts[1]
    try:
        new_amount = int(parts[2])
    except ValueError:
        return existing | {new_tag}
    prefix = f"persistent_{damage_type}_"
    old_amount = 0
    for c in existing:
        if c.startswith(prefix):
            try:
                old_amount = int(c.split("_", 2)[2])
            except (IndexError, ValueError):
                pass
    keep_amount = max(old_amount, new_amount)
    filtered = frozenset(c for c in existing if not c.startswith(prefix))
    return filtered | {f"persistent_{damage_type}_{keep_amount}"}


def apply_persistent_damage(
    state: RoundState, actor_name: str,
) -> tuple[RoundState, float]:
    """Apply all persistent damage tags at end of actor's turn.

    Returns (new_state, total_damage_applied).
    Bypasses the full pipeline — persistent damage is not reduced by
    Shield Block, Intercept Attack, or Guardian's Armor.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=29)
    """
    if actor_name in state.pcs:
        snap = state.pcs[actor_name]
        tags = _parse_persistent_tags(snap.conditions)
        if not tags:
            return state, 0.0
        total = sum(amount for _, amount in tags)
        new_hp = max(0, snap.current_hp - int(total))
        state = state.with_pc_update(actor_name, current_hp=new_hp)
        return state, float(total)
    if actor_name in state.enemies:
        snap = state.enemies[actor_name]
        tags = _parse_persistent_tags(snap.conditions)
        if not tags:
            return state, 0.0
        total = sum(amount for _, amount in tags)
        new_hp = max(0, snap.current_hp - int(total))
        state = state.with_enemy_update(actor_name, current_hp=new_hp)
        return state, float(total)
    return state, 0.0


def attempt_recovery(
    state: RoundState, actor_name: str,
) -> RoundState:
    """DC 15 flat check recovery from persistent damage (EV-folded).

    For single-round beam search: tag persists (recovery is future-turn).
    For multi-round solver: tags removed probabilistically.
    NOTE: Uses random.random() — non-deterministic. Seeded RNG deferred.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=29)
    """
    from pf2e.rolls import flat_check

    recovery_prob = flat_check(15)  # 0.30

    if actor_name in state.pcs:
        snap = state.pcs[actor_name]
        tags = _parse_persistent_tags(snap.conditions)
        if tags and random.random() < recovery_prob:
            damage_type, _ = tags[0]
            prefix = f"persistent_{damage_type}_"
            new_conds = frozenset(
                c for c in snap.conditions if not c.startswith(prefix))
            return state.with_pc_update(actor_name, conditions=new_conds)
    elif actor_name in state.enemies:
        snap = state.enemies[actor_name]
        tags = _parse_persistent_tags(snap.conditions)
        if tags and random.random() < recovery_prob:
            damage_type, _ = tags[0]
            prefix = f"persistent_{damage_type}_"
            new_conds = frozenset(
                c for c in snap.conditions if not c.startswith(prefix))
            return state.with_enemy_update(actor_name, conditions=new_conds)
    return state
