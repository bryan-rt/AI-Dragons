"""pf2e/auto_state.py — AutoState Chassis (CP10.4.2)

Deterministic state-change actions: no roll, no target.
Adding a new AutoState action = one registry entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType
from pf2e.combat_math import expected_enemy_turn_damage

if TYPE_CHECKING:
    from pf2e.tactics import SpatialQueries
    from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


@dataclass(frozen=True)
class AutoStateDef:
    traits: frozenset[str]
    action_cost: int
    conditions_applied: tuple[str, ...] = ()
    conditions_removed: tuple[str, ...] = ()
    requires_conditions: tuple[str, ...] = ()
    requires_not_conditions: tuple[str, ...] = ()
    requires_shield_held: bool = False
    ev_formula: str = ""   # "" = 0.0, "shield_danger"
    pc_only: bool = True   # False = enemies also eligible
    aon_url: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AUTO_STATE_REGISTRY: dict[ActionType, AutoStateDef] = {
    ActionType.STAND: AutoStateDef(
        traits=frozenset(),
        action_cost=1,
        requires_conditions=("prone",),
        conditions_removed=("prone",),
        pc_only=False,
        aon_url="https://2e.aonprd.com/Actions.aspx?ID=2314",
    ),
    ActionType.RAISE_SHIELD: AutoStateDef(
        traits=frozenset(),
        action_cost=1,
        requires_shield_held=True,
        requires_not_conditions=("shield_raised",),
        conditions_applied=("shield_raised",),
        ev_formula="shield_danger",
        aon_url="https://2e.aonprd.com/Actions.aspx?ID=2318",
    ),
    ActionType.DROP_PRONE: AutoStateDef(
        traits=frozenset(),
        action_cost=1,
        requires_not_conditions=("prone",),
        conditions_applied=("prone",),
        ev_formula="",
        aon_url="https://2e.aonprd.com/Actions.aspx?ID=2370",
    ),
    ActionType.TAKE_COVER: AutoStateDef(
        traits=frozenset(),
        action_cost=1,
        requires_not_conditions=("cover",),
        conditions_applied=("cover",),
        ev_formula="shield_danger",
        # "cover" condition tag is a placeholder.
        # CP10.6 will refine to CoverLevel enum.
        aon_url="https://2e.aonprd.com/Actions.aspx?ID=2324",
    ),
}


# ---------------------------------------------------------------------------
# EV helpers
# ---------------------------------------------------------------------------

def _compute_ev(
    formula: str,
    actor: CombatantSnapshot,
    state: RoundState,
) -> float:
    """Compute EV for an AutoState action.

    "shield_danger": +2 circ AC reduces incoming damage ~10%.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2318)
    """
    if formula == "shield_danger":
        total = sum(
            expected_enemy_turn_damage(e, actor)
            for e in state.enemies.values()
            if e.current_hp > 0
        )
        return total * 0.10
    return 0.0


# ---------------------------------------------------------------------------
# Eligibility helpers — map condition strings to snapshot fields
# ---------------------------------------------------------------------------
# "prone" and "shield_raised" are bool fields on CombatantSnapshot/
# EnemySnapshot, not strings in the conditions frozenset. This helper
# bridges the registry's string-based requires_conditions to the actual
# snapshot fields.

def _has_condition(actor: CombatantSnapshot | EnemySnapshot, cond: str) -> bool:
    """Check whether actor has a condition (bool field or frozenset member)."""
    if cond == "prone":
        return actor.prone
    if cond == "shield_raised":
        return getattr(actor, "shield_raised", False)
    return cond in actor.conditions


# ---------------------------------------------------------------------------
# Generic evaluator
# ---------------------------------------------------------------------------

def evaluate_auto_state(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    defn = AUTO_STATE_REGISTRY.get(action.type)
    if defn is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="not in registry")
    # Actor lookup (Stand pc_only=False -> check enemies too)
    actor = state.pcs.get(action.actor_name)
    if actor is None and not defn.pc_only:
        actor = state.enemies.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="actor not found")
    if actor.actions_remaining < defn.action_cost:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="insufficient actions")
    for c in defn.requires_conditions:
        if not _has_condition(actor, c):
            return ActionResult(action=action, eligible=False,
                                ineligibility_reason=f"needs {c}")
    for c in defn.requires_not_conditions:
        if _has_condition(actor, c):
            return ActionResult(action=action, eligible=False,
                                ineligibility_reason=f"already has {c}")
    if defn.requires_shield_held:
        sh = actor.character.shield
        if sh is None or sh.name not in actor.held_weapons:
            return ActionResult(action=action, eligible=False,
                                ineligibility_reason="shield not held")
    # Single deterministic outcome
    # _compute_ev only works for PCs (needs CombatantSnapshot)
    score = 0.0
    if defn.ev_formula and action.actor_name in state.pcs:
        score = _compute_ev(defn.ev_formula, state.pcs[action.actor_name], state)
    outcome = ActionOutcome(
        probability=1.0,
        conditions_applied={action.actor_name: defn.conditions_applied},
        conditions_removed={action.actor_name: defn.conditions_removed},
        score_delta=score,
    )
    return ActionResult(action=action, outcomes=(outcome,))
