"""pf2e/conditions.py — Condition State Machine (CP10.5)

Condition metadata registry and turn-based processing.
The dual tracking system (bool fields + frozenset) is preserved
intentionally — full unification is a post-CP10 cleanup task.

Known tracking model:
  PCs:    frightened -> int field; prone/off_guard/shield_raised -> bool fields
  Enemies: frightened -> frozenset ("frightened_N"); prone/off_guard -> bool fields
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sim.round_state import RoundState


@dataclass(frozen=True)
class ConditionDef:
    name: str
    tracked_as_bool: bool = False
    tracked_as_int: bool = False
    snapshot_field: str = ""
    end_of_turn_decrement: bool = False
    description: str = ""


CONDITION_REGISTRY: dict[str, ConditionDef] = {
    "frightened": ConditionDef(
        name="frightened",
        tracked_as_int=True,
        snapshot_field="frightened",
        end_of_turn_decrement=True,
        description="Penalty to all checks and DCs equal to level.",
    ),
    "prone": ConditionDef(
        name="prone",
        tracked_as_bool=True,
        snapshot_field="prone",
        description="Off-guard; -2 circ attack; only Crawl/Stand to move.",
    ),
    "off_guard": ConditionDef(
        name="off_guard",
        tracked_as_bool=True,
        snapshot_field="off_guard",
        description="-2 circumstance penalty to AC.",
    ),
    "shield_raised": ConditionDef(
        name="shield_raised",
        tracked_as_bool=True,
        snapshot_field="shield_raised",
        description="+2 circumstance bonus to AC until start of next turn.",
    ),
    "hidden": ConditionDef(
        name="hidden",
        description="DC 11 flat check for enemies to target you.",
    ),
    "cover": ConditionDef(
        name="cover",
        description="+2 circ AC vs ranged (CP10.6 wires AC effect).",
    ),
    "demoralize_immune": ConditionDef(
        name="demoralize_immune",
        description="Immune to further Demoralize (encounter duration).",
    ),
    "diversion_immune": ConditionDef(
        name="diversion_immune",
        description="Immune to further Create a Diversion.",
    ),
    "disarmed": ConditionDef(
        name="disarmed",
        description="-2 circumstance to attack rolls.",
    ),
    "fleeing_1": ConditionDef(
        name="fleeing_1",
        description="Must spend actions moving away; cannot attack.",
    ),
    "anthem_active": ConditionDef(
        name="anthem_active",
        description="Round-level flag for Courageous Anthem.",
    ),
}


def process_end_of_turn(state: RoundState, actor_name: str) -> RoundState:
    """Apply end-of-turn condition processing for actor_name.

    Frightened: decrements by 1 at end of creature's own turn.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=42)

    TRACKING NOTE: PCs store frightened as int field; enemies store as
    frozenset tag ("frightened_N"). These are handled separately.
    """
    if actor_name in state.pcs:
        snap = state.pcs[actor_name]
        if snap.frightened > 0:
            new_val = max(0, snap.frightened - 1)
            state = state.with_pc_update(actor_name, frightened=new_val)
        return state

    if actor_name in state.enemies:
        snap = state.enemies[actor_name]
        new_conds = set(snap.conditions)
        changed = False
        for c in list(new_conds):
            if c.startswith("frightened_"):
                try:
                    val = int(c.split("_")[1])
                except (IndexError, ValueError):
                    continue
                new_conds.discard(c)
                if val > 1:
                    new_conds.add(f"frightened_{val - 1}")
                changed = True
        if changed:
            state = state.with_enemy_update(
                actor_name, conditions=frozenset(new_conds))
        return state

    return state
