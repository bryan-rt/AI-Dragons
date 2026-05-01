"""Contest roll chassis — declarative evaluator for skill-vs-DC actions.

Consolidates Trip, Disarm, Demoralize, Create a Diversion, and Feint
into a single data-driven evaluator. Each action is a frozen registry
entry (ContestRollDef) that the generic evaluate_contest_roll() interprets.

Old evaluators in actions.py are preserved but no longer dispatched.

(AoN: https://2e.aonprd.com/Rules.aspx?ID=2194 — degrees of success)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pf2e.actions import Action, ActionOutcome, ActionResult, ActionType
from pf2e.combat_math import (
    die_average,
    enumerate_d20_outcomes,
    lore_bonus,
    map_penalty,
    melee_reach_ft,
    skill_bonus,
)
from pf2e.traits import TraitCategory, has_trait
from pf2e.types import SaveType, Skill

if TYPE_CHECKING:
    from pf2e.tactics import SpatialQueries
    from sim.round_state import CombatantSnapshot, EnemySnapshot, RoundState


# ---------------------------------------------------------------------------
# Geometry helpers (pure math, duplicated from actions.py to avoid circular)
# ---------------------------------------------------------------------------

def _grid_distance_ft(a: tuple[int, int], b: tuple[int, int]) -> int:
    """PF2e grid distance with 5/10 diagonal alternation.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2357)
    """
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])
    diag = min(dr, dc)
    straight = abs(dr - dc)
    return (diag // 2) * 10 + ((diag + 1) // 2) * 5 + straight * 5


def _chebyshev_squares(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _is_within_weapon_reach(
    attacker_pos: tuple[int, int],
    target_pos: tuple[int, int],
    reach_ft: int,
) -> bool:
    """Check if target is within weapon reach.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2379)
    """
    if reach_ft == 10:
        return 0 < _chebyshev_squares(attacker_pos, target_pos) <= 2
    return 0 < _grid_distance_ft(attacker_pos, target_pos) <= reach_ft


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DegreeEffect:
    """Effect applied at a single degree of success.

    conditions_on_target: condition strings applied to the target.
    conditions_on_actor: condition strings applied to the actor.
    score_delta: fixed EV contribution (e.g., off_guard benefit estimate).
        Dynamic EV (e.g., frightened) is computed by _condition_ev() at
        evaluation time and added on top of this.
    """
    conditions_on_target: tuple[str, ...] = ()
    conditions_on_actor: tuple[str, ...] = ()
    score_delta: float = 0.0


@dataclass(frozen=True)
class ContestRollDef:
    """Declarative definition for a contest roll action.

    traits: trait slugs for MAP/immunity checks.
    roller_skill: skill used for the check (may be overridden by Deceptive Tactics).
    target_dc_attr: which defense to use as DC ("reflex", "will", "perception").
    range_type: "melee_reach", "ranged_30", or "" for no range check.
    crit_success: effect on critical success; None = merge probability into success.
    success: effect on success.
    failure: effect on failure.
    crit_failure: effect on critical failure; None = merge probability into failure.
    use_deceptive_tactics: if True, Warfare Lore may replace roller_skill.
    failure_immunity_tag: condition applied to target on failure/crit_failure.
    min_actions_remaining: minimum actions required (e.g., 2 for Feint).
    """
    traits: frozenset[str]
    roller_skill: Skill
    target_dc_attr: str
    range_type: str
    crit_success: DegreeEffect | None
    success: DegreeEffect
    failure: DegreeEffect
    crit_failure: DegreeEffect | None
    use_deceptive_tactics: bool = False
    failure_immunity_tag: str = ""
    min_actions_remaining: int = 0


# ---------------------------------------------------------------------------
# Registry — 5 entries for CP10.4.1
# ---------------------------------------------------------------------------

CONTEST_ROLL_REGISTRY: dict[ActionType, ContestRollDef] = {
    ActionType.TRIP: ContestRollDef(
        # (AoN: https://2e.aonprd.com/Actions.aspx?ID=2309)
        traits=frozenset({"attack"}),
        roller_skill=Skill.ATHLETICS,
        target_dc_attr="reflex",
        range_type="melee_reach",
        crit_success=DegreeEffect(conditions_on_target=("prone", "off_guard")),
        success=DegreeEffect(conditions_on_target=("prone", "off_guard")),
        failure=DegreeEffect(),
        crit_failure=DegreeEffect(conditions_on_actor=("prone",)),
    ),
    ActionType.DISARM: ContestRollDef(
        # (AoN: https://2e.aonprd.com/Actions.aspx?ID=2300)
        traits=frozenset({"attack"}),
        roller_skill=Skill.ATHLETICS,
        target_dc_attr="reflex",
        range_type="melee_reach",
        crit_success=DegreeEffect(conditions_on_target=("disarmed",)),
        success=DegreeEffect(conditions_on_target=("disarmed",)),
        failure=DegreeEffect(),
        crit_failure=DegreeEffect(conditions_on_actor=("off_guard",)),
    ),
    ActionType.DEMORALIZE: ContestRollDef(
        # (AoN: https://2e.aonprd.com/Actions.aspx?ID=2304)
        # Deviation from RAW: actor gets frightened_1 on crit failure.
        # RAW Demoralize crit failure only sets immunity, no actor penalty.
        # Preserved from existing evaluate_demoralize() for behavioral parity.
        traits=frozenset({"mental", "emotion", "fear"}),
        roller_skill=Skill.INTIMIDATION,
        target_dc_attr="will",
        range_type="ranged_30",
        crit_success=DegreeEffect(conditions_on_target=("frightened_2",)),
        success=DegreeEffect(conditions_on_target=("frightened_1",)),
        failure=DegreeEffect(),
        crit_failure=DegreeEffect(conditions_on_actor=("frightened_1",)),
        failure_immunity_tag="demoralize_immune",
    ),
    ActionType.CREATE_A_DIVERSION: ContestRollDef(
        # (AoN: https://2e.aonprd.com/Skills.aspx?ID=38)
        # Crit success/failure collapsed: only success/failure degrees.
        traits=frozenset(),
        roller_skill=Skill.DECEPTION,
        target_dc_attr="perception",
        range_type="",
        crit_success=None,
        success=DegreeEffect(conditions_on_target=("off_guard",)),
        failure=DegreeEffect(),
        crit_failure=None,
        use_deceptive_tactics=True,
        failure_immunity_tag="diversion_immune",
    ),
    ActionType.FEINT: ContestRollDef(
        # (AoN: https://2e.aonprd.com/Skills.aspx?ID=38)
        traits=frozenset({"mental"}),
        roller_skill=Skill.DECEPTION,
        target_dc_attr="perception",
        range_type="melee_reach",
        crit_success=DegreeEffect(conditions_on_target=("off_guard",)),
        success=DegreeEffect(conditions_on_target=("off_guard",)),
        failure=DegreeEffect(),
        crit_failure=DegreeEffect(conditions_on_actor=("off_guard",)),
        use_deceptive_tactics=True,
        min_actions_remaining=2,
    ),
}


# ---------------------------------------------------------------------------
# Condition EV helper
# ---------------------------------------------------------------------------

def _condition_ev(
    condition: str,
    target: EnemySnapshot,
    state: RoundState | None = None,
    actor_name: str = "",
) -> float:
    """Estimate EV of applying a named condition to a target.

    Handles frightened_N, prone (Stand cost AED), off_guard (+2 ally hits),
    and disarmed (-2 attack penalty). actor_name determines faction routing
    for AED helpers.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=88 — Prone)
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=58 — Off-Guard)
    """
    if condition.startswith("frightened_"):
        level = int(condition.split("_")[1])
        current = max(
            (int(c.split("_")[1]) for c in target.conditions
             if c.startswith("frightened_")),
            default=0,
        )
        gain = max(0, level - current)
        if gain == 0:
            return 0.0
        # Frightened EV: -N to all enemy checks × hits × avg damage × 0.05
        if target.damage_dice and "d" in target.damage_dice:
            parts = target.damage_dice.split("d", 1)
            avg_dmg = int(parts[0]) * die_average(f"d{parts[1]}") + target.damage_bonus
        else:
            avg_dmg = float(target.damage_bonus)
        per_level_ev = target.num_attacks_per_turn * avg_dmg * 0.05
        return gain * per_level_ev

    if condition == "prone":
        # Target must spend 1 action to Stand next turn instead of attacking.
        # Discounted by 0.7 for P(target survives to act on next turn).
        # (AoN: https://2e.aonprd.com/Actions.aspx?ID=2323 — Stand)
        if state is None:
            return 1.5  # fallback: roughly one weak attack EV
        from pf2e.actions import _avg_opposing_attack_ev
        return _avg_opposing_attack_ev(state, actor_name) * 0.70

    if condition == "off_guard":
        # +2 circumstance to attacker rolls ≈ 10% more hits × avg ally damage.
        # Estimate: 1 remaining ally strike this round on average.
        # (AoN: https://2e.aonprd.com/Conditions.aspx?ID=58)
        if state is None:
            return 0.5  # fallback
        from pf2e.actions import _avg_ally_damage
        return 0.10 * _avg_ally_damage(state, actor_name)

    if condition == "disarmed":
        # -2 attack penalty ≈ 10% fewer hits × avg damage × attacks.
        # (AoN: https://2e.aonprd.com/Actions.aspx?ID=2300)
        # Guard: target may be CombatantSnapshot (no damage_dice) if NPC evaluates
        dice_str = getattr(target, 'damage_dice', '') or ''
        if not dice_str or "d" not in dice_str:
            return 0.0
        parts = dice_str.split("d", 1)
        try:
            count = int(parts[0])
            die_s = f"d{parts[1]}"
        except (ValueError, IndexError):
            return 0.0
        damage_bonus = getattr(target, 'damage_bonus', 0)
        num_attacks = getattr(target, 'num_attacks_per_turn', 1)
        avg_dmg = count * die_average(die_s) + damage_bonus
        return 0.10 * avg_dmg * num_attacks

    return 0.0


# ---------------------------------------------------------------------------
# Main evaluator
# ---------------------------------------------------------------------------

def evaluate_contest_roll(
    action: Action, state: RoundState, spatial: SpatialQueries | None = None,
) -> ActionResult:
    """Generic evaluator for all contest roll actions.

    Looks up the ContestRollDef from the registry, computes d20 outcomes,
    and builds ActionOutcome per degree of success.
    """
    defn = CONTEST_ROLL_REGISTRY.get(action.type)
    if defn is None:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason=f"No contest roll def for {action.type}",
        )

    # --- Eligibility checks ---

    actor = state.pcs.get(action.actor_name)
    if actor is None:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason="Actor not a PC",
        )

    if defn.min_actions_remaining > 0 and actor.actions_remaining < defn.min_actions_remaining:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason=(
                f"{action.type.name} requires at least "
                f"{defn.min_actions_remaining} actions remaining"
            ),
        )

    target = state.enemies.get(action.target_name)
    if target is None or target.current_hp <= 0:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason=f"Target {action.target_name!r} not found or dead",
        )

    if defn.failure_immunity_tag and defn.failure_immunity_tag in target.conditions:
        return ActionResult(
            action=action, eligible=False,
            ineligibility_reason=f"{action.target_name} is immune to {action.type.name}",
        )

    # Range check
    if defn.range_type == "melee_reach":
        reach = melee_reach_ft(actor.character)
        if not _is_within_weapon_reach(actor.position, target.position, reach):
            return ActionResult(
                action=action, eligible=False,
                ineligibility_reason="Target out of melee reach",
            )
    elif defn.range_type == "ranged_30":
        dist = _grid_distance_ft(actor.position, target.position)
        if dist > 30:
            return ActionResult(
                action=action, eligible=False,
                ineligibility_reason="Target beyond 30 ft",
            )

    # --- Compute roller bonus ---

    if defn.use_deceptive_tactics and actor.character.has_deceptive_tactics:
        bonus = lore_bonus(actor.character, "Warfare")
    else:
        bonus = skill_bonus(actor.character, defn.roller_skill)
    bonus -= actor.frightened

    # MAP for attack-trait actions
    if has_trait(defn.traits, TraitCategory.MAP):
        bonus += map_penalty(actor.map_count + 1, agile=False)

    # --- Compute target DC ---

    if defn.target_dc_attr == "reflex":
        dc = 10 + target.saves[SaveType.REFLEX]
    elif defn.target_dc_attr == "will":
        dc = 10 + target.saves[SaveType.WILL]
    elif defn.target_dc_attr == "perception":
        dc = 10 + target.perception_bonus
    else:
        raise ValueError(f"Unknown target_dc_attr: {defn.target_dc_attr!r}")

    # --- Roll d20 outcomes ---

    outcomes_d20 = enumerate_d20_outcomes(bonus, dc)

    # Degree collapse: None = merge into adjacent degree
    crit_s_faces = outcomes_d20.critical_success
    success_faces = outcomes_d20.success
    failure_faces = outcomes_d20.failure
    crit_f_faces = outcomes_d20.critical_failure

    if defn.crit_success is None:
        success_faces += crit_s_faces
        crit_s_faces = 0
    if defn.crit_failure is None:
        failure_faces += crit_f_faces
        crit_f_faces = 0

    # --- Pre-compute per-level EV for actor-frightened penalty ---

    if target.damage_dice and "d" in target.damage_dice:
        parts = target.damage_dice.split("d", 1)
        avg_enemy_dmg = int(parts[0]) * die_average(f"d{parts[1]}") + target.damage_bonus
    else:
        avg_enemy_dmg = float(target.damage_bonus)
    per_level_ev = target.num_attacks_per_turn * avg_enemy_dmg * 0.05

    # --- Build outcomes ---

    outcomes: list[ActionOutcome] = []

    degree_data = [
        (crit_s_faces, defn.crit_success, "Crit success"),
        (success_faces, defn.success, "Success"),
        (failure_faces, defn.failure, "Failure"),
        (crit_f_faces, defn.crit_failure, "Crit failure"),
    ]

    for faces, effect, degree_name in degree_data:
        if faces <= 0 or effect is None:
            continue

        prob = faces / 20

        # Build conditions_applied
        conditions_applied: dict[str, tuple[str, ...]] = {}
        if effect.conditions_on_target:
            conditions_applied[action.target_name] = effect.conditions_on_target
        if effect.conditions_on_actor:
            conditions_applied[action.actor_name] = effect.conditions_on_actor

        # Apply failure immunity tag on failure/crit_failure degrees
        is_fail_degree = degree_name in ("Failure", "Crit failure")
        if is_fail_degree and defn.failure_immunity_tag:
            existing = conditions_applied.get(action.target_name, ())
            conditions_applied[action.target_name] = existing + (defn.failure_immunity_tag,)

        # Compute score_delta
        score = effect.score_delta
        for cond in effect.conditions_on_target:
            score += _condition_ev(cond, target, state, action.actor_name)
        # Actor frightened penalty (Demoralize crit_failure deviation)
        for cond in effect.conditions_on_actor:
            if cond.startswith("frightened_"):
                score -= per_level_ev

        # Description
        desc_parts = []
        if effect.conditions_on_target:
            desc_parts.append(
                f"{action.target_name} {', '.join(effect.conditions_on_target)}"
            )
        if effect.conditions_on_actor:
            desc_parts.append(
                f"{action.actor_name} {', '.join(effect.conditions_on_actor)}"
            )
        if is_fail_degree and defn.failure_immunity_tag and not effect.conditions_on_target:
            desc_parts.append(f"{action.target_name} immune")
        description = (
            f"{degree_name}: {'; '.join(desc_parts)}" if desc_parts
            else f"{degree_name}: no effect"
        )

        outcomes.append(ActionOutcome(
            probability=prob,
            conditions_applied=conditions_applied,
            score_delta=score,
            description=description,
        ))

    if not outcomes:
        outcomes.append(ActionOutcome(probability=1.0))

    return ActionResult(action=action, outcomes=tuple(outcomes))
