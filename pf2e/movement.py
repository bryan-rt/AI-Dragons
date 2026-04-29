"""pf2e/movement.py — Movement Chassis (CP10.4.6)

All position-change evaluators. Imported by actions.py via late-binding.
Candidate generation (destination selection) lives in sim/candidates.py.
Evaluators trust candidates.py for reachability — no BFS here.

New: evaluate_crawl (prone-only 5ft movement).
Deferred: Balance (needs difficult terrain), Tumble Through (needs path-blocking).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pf2e.combat_math import skill_bonus
from pf2e.types import Skill

if TYPE_CHECKING:
    from pf2e.actions import Action, ActionOutcome, ActionResult
    from sim.round_state import RoundState


def _d20_success_probability(bonus: int, dc: int) -> float:
    """P(d20 + bonus >= dc), clamped to [0.05, 0.95].
    Duplicated from actions.py to avoid import coupling.
    """
    hits = 20 - max(0, dc - bonus - 1)
    return max(0.05, min(0.95, hits / 20))


def evaluate_stride(
    action: Action, state: RoundState, spatial=None,
) -> ActionResult:
    """Stride up to Speed. Destination validated by candidates.py.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2320)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    if action.target_position is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No target position specified")
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            position_changes={action.actor_name: action.target_position},
            description=f"Stride to {action.target_position}",
        ),),
    )


def evaluate_step(
    action: Action, state: RoundState, spatial=None,
) -> ActionResult:
    """Step exactly 5 ft. Does not trigger reactions.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2321)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    if action.target_position is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No target position specified")
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            position_changes={action.actor_name: action.target_position},
            description=f"Step to {action.target_position}",
        ),),
    )


def evaluate_crawl(
    action: Action, state: RoundState, spatial=None,
) -> ActionResult:
    """Crawl exactly 5 ft while prone. Prone condition remains after.
    Requires Speed >= 10 ft. Candidates.py generates adjacent squares only.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=76)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    actor = (state.pcs.get(action.actor_name)
             or state.enemies.get(action.actor_name))
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Actor not found")
    if not actor.prone:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Must be prone to Crawl")
    if action.target_position is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No target position specified")
    # EnemySnapshot has no current_speed/character — assume speed >= 10
    speed = getattr(actor, 'current_speed', None)
    if speed is None:
        char = getattr(actor, 'character', None)
        speed = char.speed if char is not None else 25  # default for enemies
    if speed < 10:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Speed too low to Crawl")
    return ActionResult(
        action=action,
        outcomes=(ActionOutcome(
            probability=1.0,
            position_changes={action.actor_name: action.target_position},
            description=f"Crawl to {action.target_position}",
        ),),
    )


def evaluate_sneak(
    action: Action, state: RoundState, spatial=None,
) -> ActionResult:
    """Move while Hidden. Half Speed enforced by candidates.py.
    On failure: position changes but Hidden is lost.
    (AoN: https://2e.aonprd.com/Actions.aspx?ID=2317)
    """
    from pf2e.actions import ActionOutcome, ActionResult

    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Actor not a PC")
    if "hidden" not in actor.conditions:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="Must be Hidden to Sneak")
    if action.target_position is None:
        return ActionResult(action=action, eligible=False,
                            ineligibility_reason="No target position")

    stealth = skill_bonus(actor.character, Skill.STEALTH)
    living_enemies = [e for e in state.enemies.values() if e.current_hp > 0]
    avg_perc_dc = (sum(10 + e.perception_bonus for e in living_enemies)
                   / max(1, len(living_enemies)))
    p_success = _d20_success_probability(stealth, int(avg_perc_dc))

    outcomes: list[ActionOutcome] = []
    if p_success > 0:
        outcomes.append(ActionOutcome(
            probability=p_success,
            position_changes={action.actor_name: action.target_position},
            description=f"Sneak to {action.target_position} — remain hidden",
        ))
    if 1 - p_success > 0:
        outcomes.append(ActionOutcome(
            probability=1 - p_success,
            position_changes={action.actor_name: action.target_position},
            conditions_removed={action.actor_name: ("hidden",)},
            description=f"Sneak to {action.target_position} — detected",
        ))
    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))
    return ActionResult(action=action, outcomes=tuple(outcomes))
