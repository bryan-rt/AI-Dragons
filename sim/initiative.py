"""Initiative rolling and ordering.

Seeded RNG for reproducibility. Partial explicit override supported.
Tiebreakers: enemies precede PCs; alphabetical among same-side ties.

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2423 — Step 1: Roll Initiative)
"""

from __future__ import annotations

import logging
import random

from pf2e.combat_math import perception_bonus
from sim.round_state import CombatantSnapshot, EnemySnapshot

logger = logging.getLogger(__name__)


def roll_initiative(
    pcs: list[CombatantSnapshot],
    enemies: list[EnemySnapshot],
    seed: int,
    explicit: dict[str, int] | None = None,
) -> list[str]:
    """Roll initiative and return the turn order, highest first.

    Args:
        pcs: PC snapshots.
        enemies: Enemy snapshots.
        seed: RNG seed for reproducibility.
        explicit: Optional dict mapping name to initiative total;
            combatants listed here skip the roll and use this total.
            Combatants NOT listed roll normally (partial override).

    Returns:
        List of combatant names in initiative order (descending totals).

    Tiebreakers:
        1. Enemies precede PCs (AoN RAW).
        2. Among same-side ties, alphabetical by name (deterministic).

    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2423)
    """
    explicit = explicit or {}
    rng = random.Random(seed)

    scored: list[tuple[str, int, str]] = []

    for pc in pcs:
        if pc.name in explicit:
            total = explicit[pc.name]
        else:
            total = perception_bonus(pc.character) + rng.randint(1, 20)
        scored.append((pc.name, total, "pc"))

    for enemy in enemies:
        if enemy.name in explicit:
            total = explicit[enemy.name]
        else:
            total = enemy.perception_bonus + rng.randint(1, 20)
        scored.append((enemy.name, total, "enemy"))

    def sort_key(entry: tuple[str, int, str]) -> tuple[int, int, str]:
        name, total, side = entry
        side_rank = 0 if side == "enemy" else 1
        return (-total, side_rank, name)

    scored.sort(key=sort_key)
    order = [name for name, _, _ in scored]
    logger.info(f"Initiative order: {order}")
    return order
